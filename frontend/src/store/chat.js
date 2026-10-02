// 消息与生成：发送与流式、停止与重试、编辑删除重生成、消息分块渲染。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { chatBoxEl, store } from "./state.js";
import { computed, nextTick } from "vue";
import { CONTINUE_PROMPT, SEGMENT_RE, isScenarioTag } from "./helpers.js";

Object.assign(store, {
  cancelEdit() {
    store.editingId = null;
  },
  segmentsOf(m) {
    const text = m.content || "";
    const segs = [];
    SEGMENT_RE.lastIndex = 0;
    let last = 0;
    let match;
    let sawTag = false;
    while ((match = SEGMENT_RE.exec(text)) !== null) {
      sawTag = true;
      const head = text.slice(last, match.index).trim();
      if (head) segs.push({ type: "dialog", text: head });
      const body = match[2].trim();
      if (body) {
        segs.push({ type: isScenarioTag(match[1]) ? "scenario" : "dialog", text: body });
      }
      last = SEGMENT_RE.lastIndex;
    }
    const tail = text.slice(last).trim();
    if (tail) segs.push({ type: "dialog", text: tail });
    if (segs.length) return segs;
    // 只有空标记：没有可渲染的内容，别把裸标记当正文显示
    return sawTag ? [] : [{ type: "dialog", text }];
  },
  textParts(m) {
    if (m.scenario === "MULTI") {
      return store.segmentsOf(m).map((s) => ({ kind: s.type, text: s.text }));
    }
    const out = [];
    if (m.scenario) out.push({ kind: "scenario", text: m.scenario });
    out.push({ kind: "text", text: m.content || "" });
    return out;
  },
  partsOf(m) {
    const planned = store.searchPlan.parts[m.id];
    if (planned) return planned;
    return store.textParts(m).map((p) => ({
      kind: p.kind,
      pieces: [{ text: p.text, hit: false }],
    }));
  },
  async refreshMessages() {
    if (!store.activeSessionId || store.streaming) return;
    try {
      store.messages = await store.api(
        `/api/sessions/${store.activeSessionId}/messages`
      );
    } catch (e) {
      /* 会话已删等场景：静默 */
    }
  },
  beginStream() {
    store.stopped = false;
    store.abortCtrl = new AbortController();
    store.streaming = true;
    store.streamText = "";
    store.thinkPhase = false;
  },
  endStream() {
    const stopped = store.stopped;
    store.streaming = false;
    store.streamText = "";
    store.thinkPhase = false;
    store.abortCtrl = null;
    store.stopped = false;
    store.scheduleMemoryRefresh();
    return stopped;
  },
  stop() {
    if (!store.streaming || !store.abortCtrl) return;
    store.stopped = true;
    store.abortCtrl.abort();
  },
  async syncAfterStop() {
    const before = store.messages.length;
    for (let i = 0; i < 8; i++) {
      await new Promise((r) => setTimeout(r, 250));
      await store.refreshMessages();
      if (store.messages.length > before) return;
    }
  },
  canSendText(text) {
    return !!text && !store.streaming && !!store.activeSession && !store.orphanActive;
  },
  async send() {
    const text = store.input.trim();
    if (!store.canSend) return;
    // 情境只有沉浸模式有；**两个框至少有一个要有内容**（沉浸模式允许只写情境）
    const scenario = store.isImmersiveMode ? store.inputScenario.trim() : "";
    // 通过校验后才清空，发不出去时不会把草稿弄丢
    store.input = "";
    store.inputScenario = "";
    await store.runSend(text, scenario);
  },
  async continueGeneration() {
    if (!store.canContinue) return;
    await store.runSend(CONTINUE_PROMPT);
  },
  async runSend(text, scenario = "") {
    store.error = "";
    store.lastFailedUser = null;
    store.beginStream();
    store.messages.push({
      id: "tmp-user", role: "user", content: text, scenario: scenario || null, attrs: [],
    });
    store.scrollBottom();
    let userId = null;
    let failed = false;
    try {
      await store.ssePost(
        `/api/sessions/${store.activeSessionId}/chat`,
        { message: text, scenario: scenario || null },
        {
          meta: (d) => {
            userId = d.message_id;
            const m = store.messages.find((x) => x.id === "tmp-user");
            if (m) m.id = d.message_id;
          },
          status: (d) => {
            store.thinkPhase = d.phase === "thinking";
          },
          delta: (d) => {
            store.thinkPhase = false;
            store.streamText += d.text;
            store.scrollBottom();
          },
          done: (d) => {
            store.messages.push({
              id: d.message_id,
              role: "assistant",
              content: d.content,
              scenario: d.scenario,
              // 属性一起带回来（后端解析好了）：不用为它再拉一次消息列表
              attrs: d.attrs || [],
            });
            // 生成完自动把属性面板展开（有属性时），不用再手动点一下
            store.revealAttrs(d.attrs);
          },
          error: (d) => {
            store.error = d.message;
            if (userId) store.lastFailedUser = { id: userId, text, scenario };
          },
        },
        store.abortCtrl.signal
      );
    } catch (e) {
      // 用户点「停止」导致的中断不算错误：部分内容已由服务端落库
      if (!store.stopped) {
        store.error = e.httpStatus ? e.message : `连接中断：${e.message}`;
        if (userId) store.lastFailedUser = { id: userId, text, scenario };
        // user 消息压根没落库（如角色已删除被拒），界面上那条是乐观渲染的，需要撤掉
        else failed = true;
      }
    }
    const stopped = store.endStream();
    if (stopped) await store.syncAfterStop();
    else if (failed) await store.refreshMessages();
    await store.refreshSessions();
    store.scrollBottom();
  },
  async retryFailed() {
    const { id, text, scenario } = store.lastFailedUser;
    store.lastFailedUser = null;
    store.error = "";
    try {
      await store.api(`/api/messages/${id}`, { method: "DELETE" });
      store.messages = store.messages.filter((m) => m.id !== id);
    } catch (e) {
      store.error = e.message;
      return;
    }
    store.input = text;
    store.inputScenario = scenario || ""; // 情境一起恢复，重试发的才是同一条消息
    await store.send();
  },
  startEdit(m) {
    store.deleteMenuId = null;
    store.editingId = m.id;
    const mode = store.activeSession.mode;
    const isMulti = m.scenario === "MULTI";
    // 沉浸模式：无论当前有没有情境都给出情境输入框，方便手动补上
    const hasScenario = mode === "immersive";
    store.editForm = {
      content: m.content,
      scenario: m.scenario && !isMulti ? m.scenario : "",
      hasScenario,
      keepScenario: isMulti ? "MULTI" : null,
      contentLabel: hasScenario ? "话语内容" : "消息内容",
      contentPlaceholder: hasScenario ? "这一幕里该角色说出的话" : "消息正文",
      contentHint: isMulti
        ? "导演模式的消息用 [SCENARIO] 标记情境说明、[DIALOG] 标记对话，保留这两个标记即可继续分段显示。"
        : "",
      // 附加属性：按角色的定义铺开，已有值填上（导演模式没有这一节，保持空数组）
      attrs: store.showAttrInEditor ? store.attrRowsFor(m) : [],
    };
    // 打开后按内容把输入框撑到实际高度，长消息不会被塞进一个小框里
    nextTick(() => {
      document
        .querySelectorAll(".edit-modal textarea")
        .forEach((el) => store.autoGrowEl(el));
    });
  },
  async saveEdit() {
    // 编辑弹窗在消息列表之外，靠 editingId 找回目标消息
    const m = store.messages.find((x) => x.id === store.editingId);
    if (!m) {
      store.editingId = null;
      return;
    }
    const payload = { content: store.editForm.content.trim() };
    if (store.editForm.hasScenario) {
      payload.scenario = store.editForm.scenario.trim() || null; // 清空即不再显示情境块
    } else {
      payload.scenario = store.editForm.keepScenario || null;
    }
    // 附加属性只在聊天与沉浸模式出现；有这一节就整体提交（空值后端会丢掉）
    if (store.showAttrInEditor) {
      payload.attrs = store.editForm.attrs
        .filter((a) => String(a.value).trim() !== "")
        .map((a) => ({
          name: a.name,
          type: a.type,
          value: a.type === "percent" ? Number(a.value) : String(a.value),
        }));
    }
    try {
      const updated = await store.api(
        `/api/messages/${m.id}`,
        store.jsonOpts("PUT", payload)
      );
      const idx = store.messages.findIndex((x) => x.id === m.id);
      if (idx >= 0) store.messages.splice(idx, 1, updated);
      store.editingId = null;
      await store.refreshSessions();
    } catch (e) {
      store.error = e.message;
    }
  },
  async removeMessage(m, cascade) {
    store.deleteMenuId = null;
    const tip = cascade
      ? "将删除该消息及其之后的所有消息，继续？"
      : "确认删除这条消息？";
    if (!(await store.ask(tip))) return;
    try {
      await store.api(`/api/messages/${m.id}?cascade=${cascade}`, { method: "DELETE" });
      if (cascade) {
        const idx = store.messages.findIndex((x) => x.id === m.id);
        store.messages = store.messages.slice(0, idx);
      } else {
        store.messages = store.messages.filter((x) => x.id !== m.id);
      }
      await store.refreshSessions();
    } catch (e) {
      store.error = e.message;
    }
  },
  async regenerate(m) {
    if (store.streaming) {
      store.error = "正在生成中，请稍候";
      return;
    }
    // 用户消息本身是这一轮的输入，必须保留，只删它之后的；assistant 消息则连它一起替换
    const isUser = m.role === "user";
    const tip = isUser
      ? "将为这条消息重新生成回复，其后的消息会被删除，继续？"
      : "重新生成将删除该消息及其之后的所有消息，继续？";
    if (!(await store.ask(tip))) return;
    store.deleteMenuId = null;
    store.error = "";
    store.lastFailedUser = null;
    const idx = store.messages.findIndex((x) => x.id === m.id);
    store.messages = store.messages.slice(0, isUser ? idx + 1 : idx);
    store.beginStream();
    store.scrollBottom();
    let failed = false;
    try {
      await store.ssePost(`/api/messages/${m.id}/regenerate`, {}, {
        status: (d) => {
          store.thinkPhase = d.phase === "thinking";
        },
        delta: (d) => {
          store.thinkPhase = false;
          store.streamText += d.text;
          store.scrollBottom();
        },
        done: (d) => {
          store.messages.push({
            id: d.message_id,
            role: "assistant",
            content: d.content,
            scenario: d.scenario,
            attrs: d.attrs || [],
          });
          // 与首次生成同一条约定：生成完自动展开属性面板（有属性时）
          store.revealAttrs(d.attrs);
        },
        error: (d) => {
          store.error = d.message;
        },
      }, store.abortCtrl.signal);
    } catch (e) {
      if (!store.stopped) {
        failed = true;
        store.error = e.httpStatus ? e.message : `连接中断：${e.message}`;
      }
    }
    const stopped = store.endStream();
    if (stopped) await store.syncAfterStop();
    // 服务端校验不过时不会删消息，这里拉一次把上面乐观截断的界面还原回来
    else if (failed) await store.refreshMessages();
    await store.refreshSessions();
    store.scrollBottom();
  },
  scrollBottom() {
    nextTick(() => {
      const el = chatBoxEl;
      if (el) el.scrollTop = el.scrollHeight;
    });
  },
  jumpToBottom() {
    const el = chatBoxEl;
    if (!el) return;
    if (typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } else {
      el.scrollTop = el.scrollHeight; // 兜底：极老的浏览器不支持带 options 的 scrollTo
    }
  },
});

store.canSend = computed(() => {
      // 话语与情境**至少有一个有内容**：沉浸模式允许只写情境，
      // 其它模式仍然要求话语（那时根本没有情境框）
      if (store.canSendText(store.input)) return true;
      return !!store.isImmersiveMode && store.canSendText(store.inputScenario);
});

store.canContinue = computed(() => {
      return (
        store.isDirectorMode &&
        !store.streaming &&
        !store.orphanActive &&
        store.messages.some((m) => m.role === "assistant")
      );
});

store.archivedCount = computed(() => {
      return store.messages.filter((m) => m.archived).length;
});

store.displayMessages = computed(() => {
      return store.showArchived
        ? store.messages
        : store.messages.filter((m) => !m.archived);
});
