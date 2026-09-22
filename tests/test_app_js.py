"""前端结构与命名空间检查（不需要浏览器）。

Vue options API 的 data / computed / methods 共用一个实例命名空间，重名会让其中一个
静默失效——之前 bgDragOver 数据字段盖掉同名方法就是这个坑，所以这里盯住它。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.character_gen import HIDDEN_FIELDS  # noqa: E402

frontend = ROOT / "frontend"
# 拆成单文件组件后，源码分散在若干文件里；测试按下面两坨分别拼接：
#   html —— 入口 HTML + 所有 .vue（模板 + 脚本），模板类断言在它上面找
#   js   —— store.js + main.js + 各 .vue 的 script 块，逻辑类断言在它上面找
# 顺序固定为"骨架 → 左栏 → 顶栏 → 对话区 → 输入区 → 面板 → 弹窗"，
# 这样原来那些"A 在 B 之前"的顺序断言仍然成立。
# 组件文件自动发现：App.vue 必须排第一（骨架顺序断言要看它），其余按路径排序（结果稳定）。
# 这样以后继续拆组件（例如把面板里的标签页再拆出去）不用再回来改测试。
VUE_ORDER = ["App.vue"] + sorted(
    str(x.relative_to(frontend / "src")).replace("\\", "/")
    for x in (frontend / "src" / "components").rglob("*.vue")
)
vue_sources = [(frontend / "src" / rel).read_text(encoding="utf-8") for rel in VUE_ORDER]
# store 现在拆成 barrel（src/store.js）+ 领域模块（src/store/*.js）：断言要在整份源码上看，
# 所以拼成一坨（顺序稳定：先 barrel，再按文件名排序的模块）
store_files = [frontend / "src/store.js"] + sorted((frontend / "src/store").glob("*.js"))
store_js = "\\n".join(f.read_text(encoding="utf-8") for f in store_files)
main_js = (frontend / "src/main.js").read_text(encoding="utf-8")
vite_cfg = (frontend / "vite.config.js").read_text(encoding="utf-8")
css = (frontend / "src/style.css").read_text(encoding="utf-8")
html = (frontend / "index.html").read_text(encoding="utf-8") + "\n" + "\n".join(vue_sources)
script_blocks = [re.search(r"<script setup>(.*?)</script>", v, re.S).group(1)
                 for v in vue_sources if "<script setup>" in v]
js = store_js + "\n" + main_js + "\n" + "\n".join(script_blocks)
# store.js 是把选项对象的 this. 机械换成 store. 得来的；下面这行把视图换回 this.，
# 于是针对选项对象写的断言（this.panelTab / this.api(...) 之类）不用改。
# 排除前面带 / 的情况，免得把 "../store.js" 这种路径也改坏。
js = re.sub(r"(?<![\w/])store\.", "this.", js)
# 判断"某条样式是否已清除"时要先去掉注释：注释里解释"这里原来有个 XXX"是正常的，
# 不该被当成样式还在（反过来也避免有人把规则注释掉却骗过检查）
css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


def block(start_pat):
    m = re.search(start_pat, js)
    if not m:
        sys.exit(f"找不到块：{start_pat}")
    i = js.index("{", m.end() - 1)
    depth, j = 0, i
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i + 1:j]
        j += 1
    sys.exit("括号不配对")


def top_keys(text, indent):
    pad = " " * indent
    out = set()
    for line in text.splitlines():
        if not line.startswith(pad):
            continue
        rest = line[indent:]
        if rest[:1] in (" ", "\t") or not rest.strip():
            continue
        m = re.match(r'(?:async\s+)?([A-Za-z_$][\w$]*|"[^"]+")\s*[:(]', rest)
        if m:
            out.add(m.group(1).strip('"'))
    return out


# ---- 构建方式：Vue 3 + Vite（不再走 CDN） ----
check("index.html 不再引用 CDN", "cdn.jsdelivr" in html, False)
check("入口改成 ES 模块", '<script type="module" src="/src/main.js"></script>' in html, True)
check("样式改由入口 import（HTML 里不再有 link）", 'rel="stylesheet"' in html, False)
check("app.js 不在顶层创建应用", "Vue.createApp" in js, False)
check("store 导出 reactive 状态", "export const store = reactive({" in js, True)
check("store 里没有残留的 this.", "this." in store_js, False)
check("入口挂载根组件",
      'import App from "./App.vue";' in main_js
      and 'createApp(App)' in main_js and '.mount("#app")' in main_js, True)
check("入口引入样式", 'import "./style.css";' in main_js, True)
check("Vite 把产物写进后端静态目录", '"../app/static"' in vite_cfg, True)
# 产物守卫：改了源码忘了构建、或产物被删，都在这里拦下（产物是提交进仓库的）
built_html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', built_html)
check("构建产物被引用（一个 js + 一个 css）", len(assets), 2)
check("引用的产物文件都在",
      all((ROOT / "app/static" / a.lstrip("/")).is_file() for a in assets), True)
check("构建产物里没有 CDN 残留", "cdn.jsdelivr" in built_html, False)


_store_methods = r"""Object.assign(store, {
    // 把失败响应统一转成 Error，并带上状态码：
    // 调用方据此区分“服务端明确拒绝（如角色已删除）”与“连接中断”，提示才不会误导
    async httpError(resp) {
      let msg = `请求失败（${resp.status}）`;
      try {
        const j = await resp.json();
        if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (e) {}
      const err = new Error(msg);
      err.httpStatus = resp.status;
      return err;
    },

    async api(path, opts = {}) {
      const resp = await fetch(path, opts);
      if (!resp.ok) throw await store.httpError(resp);
      return resp.json();
    },

    jsonOpts(method, body) {
      return {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
    },

    // 字数提示用的两个小工具：输入框右下角显示 已用/上限，接近上限时变色。
    // 真正的拦截由 maxlength（前端）与 schemas 的 max_length（后端 422）负责，
    // 这里只负责显示
    len(value) {
      return (value || "").length;
    },
    isNear(value, max) {
      return !!max && (value || "").length >= max * 0.9;
    },

    // 消息上方那一行显示的"说话人"：聊天与沉浸两种模式下模型消息用角色名、用户消息用"我的设定"
    // 里的名字；导演模式两边都没有名字（那一行只剩时间）
    msgName(m) {
      if (!store.activeChar) return "";
      return m.role === "assistant" ? store.activeChar.name : store.profile.name || "";
    },

    // 消息的时间。created_at 存的就是本地时间、格式固定为 "2026-09-21T12:34:45"
    // （database.now() 用 isoformat(timespec="seconds")），所以直接切片比 new Date()
    // 再格式化更稳：不走时区解析、不依赖浏览器对 ISO 串的解释，老数据也不会解析失败
    timeOf(m) {
      const s = (m && m.created_at) || "";
      return s.length >= 19 ? s.slice(11, 19) : "";
    },
    fullTimeOf(m) {
      const s = (m && m.created_at) || "";
      return s ? s.replace("T", " ") : "";
    },

    // 标签页兜底：切到没有该标签的会话或模式（导演模式没有角色设定、未选会话没有记忆）
    // 时回到"生成要求"，否则面板会是一片空白
    fixPanelTab() {
      const hasChar = !!(store.activeSession && store.activeSession.character);
      if (store.panelTab === "char" && !hasChar) store.panelTab = "gen";
      if (store.panelTab === "memory" && !store.memoryScope) store.panelTab = "gen";
    },

    // 键顺序无关的快照比对：重建表单后键序可能不同，直接 JSON.stringify 会误判为已修改
    sameSnapshot(a, b) {
      const keys = (o) =>
        Object.keys(o || {})
          .filter((k) => o[k] !== undefined)
          .sort();
      const ka = keys(a);
      const kb = keys(b);
      if (ka.length !== kb.length || ka.some((k, i) => k !== kb[i])) return false;
      return ka.every((k) => JSON.stringify(a[k]) === JSON.stringify(b[k]));
    },

    snapshot(o) {
      return JSON.parse(JSON.stringify(o || {}));
    },

    disarmRevert(section) {
      clearTimeout(revertTimers[section]);
      delete revertTimers[section];
      store.revertArm[section] = false;
    },

    // 还原键：第一次点击只"武装"（按钮变成确认字样），再点一次才真的回退，避免误触丢改动
    armRevert(section) {
      if (store.revertArm[section]) {
        store.revertSection(section);
        return;
      }
      store.revertArm[section] = true;
      clearTimeout(revertTimers[section]);
      // 几秒内没有第二次点击就自动解除，免得一直停在"待确认"状态
      revertTimers[section] = setTimeout(() => store.disarmRevert(section), 5000);
    },

    // 回退到最近一次保存（或载入）时的快照；没保存过的会话即回到默认值
    revertSection(section) {
      store.disarmRevert(section);
      if (section === "gen") store.genForm = store.snapshot(store.genSaved);
      else if (section === "char") store.charForm = store.snapshot(store.charSaved);
      else if (section === "profile") store.profileForm = store.snapshot(store.profile);
      else if (section === "world") store.worldForm = store.snapshot(store.world);
      else if (section === "memory") store.memoryText = store.memorySaved;
    },

    onDocumentClick() {
      // 删除菜单与触发它的按钮都做了 stopPropagation，能走到这里就说明点的是别处
      store.deleteMenuId = null;
    },

    onDocumentKeydown(e) {
      if (e.key !== "Escape") return;
      // 裁剪弹窗叠在最上层，Esc 先关它
      if (store.crop.visible) {
        store.cancelCrop();
        return;
      }
      store.deleteMenuId = null;
      if (store.editingId !== null) store.cancelEdit();
    },

    cancelEdit() {
      store.editingId = null;
    },

    ask(text) {
      return new Promise((resolve) => {
        store.confirmBox = { visible: true, text, resolve };
      });
    },

    answerConfirm(val) {
      store.confirmBox.visible = false;
      if (store.confirmBox.resolve) store.confirmBox.resolve(val);
    },

    // SSE 用 POST，EventSource 不支持，改用 fetch + ReadableStream 手动解析
    async ssePost(url, body, handlers, signal) {
      const opts = store.jsonOpts("POST", body);
      if (signal) opts.signal = signal;
      const resp = await fetch(url, opts);
      if (!resp.ok) throw await store.httpError(resp);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let event = "message";
          let data = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (data && handlers[event]) handlers[event](JSON.parse(data));
        }
      }
    },

    async init() {
      let ollamaOk = true;
      // 字数上限以后端为准；拿不到就沿用 data 里的兜底值，不影响使用
      try {
        store.limits = await store.api("/api/limits");
      } catch (e) {
        /* 用兜底值 */
      }
      // "我的设定"是全局的，只在启动时取一次；保存后由 saveProfile 刷新
      try {
        const p = await store.api("/api/profile");
        store.profile = p;
        store.profileForm = store.snapshot(p);
        await store.loadPresets();
      } catch (e) {
        /* 拿不到就用空值，面板里照样能填 */
      }
      // "世界设定"同样是全局的，也只在启动时取一次；保存后由 saveWorld 刷新
      try {
        const w = await store.api("/api/world");
        store.world = w;
        store.worldForm = store.snapshot(w);
      } catch (e) {
        /* 拿不到就用空值 */
      }
      try {
        store.models = await store.api("/api/models");
      } catch (e) {
        ollamaOk = false;
        store.modelWarning = "无法连接 Ollama，请确认服务已启动";
      }
      try {
        const s = await store.api("/api/settings");
        store.currentModel = s.model;
        store.disableThinking = !!s.disable_thinking;
      } catch (e) {
        store.error = e.message;
        return;
      }
      if (ollamaOk) {
        if (store.models.length === 0) {
          store.modelWarning = "Ollama 中还没有可用模型，请先拉取一个";
        } else if (!store.currentModel) {
          // 首次使用不预选模型：给一句提示，但不拦着用户浏览界面
          store.modelWarning = "还没有选择模型，生成前请先在左边选一个";
        } else if (!store.models.some((m) => m.name === store.currentModel)) {
          store.modelWarning = `所选模型 ${store.currentModel} 未安装，请在右侧重新选择`;
        }
      }
      await store.refreshCharacters();
      await store.refreshSessions();
      try {
        const form = await store.api("/api/gen-settings");
        store.genFields = form.fields;
        store.genDefaults = form.defaults;
      } catch (e) {
        /* 表单定义拉取失败时生成要求区留空 */
      }
    },

    async refreshCharacters() {
      store.characters = await store.api("/api/characters");
    },

    async refreshSessions() {
      // 只拉当前模式的会话：聊天模式与沉浸模式的会话列表相互隔离，互不可见
      store.sessions = await store.api(`/api/sessions?mode=${store.mode}`);
    },

    async switchMode(key) {
      if (key === store.mode) return;
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再切换模式";
        return;
      }
      store.activeByMode[store.mode] = store.activeSessionId; // 记住本模式正看哪条
      store.mode = key;
      store.error = "";
      try {
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
        return;
      }
      const remembered = store.activeByMode[key];
      if (remembered && store.sessions.some((s) => s.id === remembered)) {
        await store.openSession(remembered); // 切回来仍停在原来那条会话
        return;
      }
      // 该模式没有可恢复的会话：清空对话区，另一模式的会话不残留
      store.activeSessionId = null;
      store.activeSession = null;
      store.messages = [];
      store.showArchived = false;
      store.resetBackgrounds();
      store.initGenForm();
    },

    fieldsOf(mode) {
      return store.genFields[mode] || [];
    },

    initGenForm() {
      const mode = store.activeSession ? store.activeSession.mode : store.mode;
      const merged = { ...(store.genDefaults[mode] || {}) };
      const stored = (store.activeSession && store.activeSession.gen_settings) || {};
      for (const k of Object.keys(stored)) {
        if (stored[k] !== null && stored[k] !== "") merged[k] = stored[k];
      }
      for (const f of store.fieldsOf(mode)) {
        if (f.type === "tags" && !Array.isArray(merged[f.key])) merged[f.key] = [];
        if (f.type === "radio" && !merged[f.key]) {
          merged[f.key] = (f.options && f.options[0] && f.options[0][0]) || "";
        }
      }
      store.genForm = merged;
      store.genSaved = store.snapshot(merged);
    },

    toggleTag(key, tag) {
      const list = store.genForm[key] || [];
      const i = list.indexOf(tag);
      if (i >= 0) list.splice(i, 1);
      else list.push(tag);
      store.genForm[key] = [...list];
    },

    addTag(key) {
      const draft = (store.tagDraft[key] || "").trim();
      if (draft && !(store.genForm[key] || []).includes(draft)) {
        store.genForm[key] = [...(store.genForm[key] || []), draft];
      }
      store.tagDraft[key] = "";
    },

    removeTag(key, tag) {
      store.genForm[key] = (store.genForm[key] || []).filter((t) => t !== tag);
    },

    customTags(field) {
      return (store.genForm[field.key] || []).filter(
        (t) => !(field.presets || []).includes(t)
      );
    },

    async saveGenSettings() {
      const payload = {};
      for (const f of store.fieldsOf(store.activeSession.mode)) {
        payload[f.key] = store.genForm[f.key];
      }
      try {
        store.activeSession = await store.api(
          `/api/sessions/${store.activeSessionId}`,
          store.jsonOpts("PATCH", { gen_settings: payload })
        );
        store.initGenForm();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 把带标记的全文切成 [{type, text}]。标记之外的裸文本按话语算——模型常把台词
    // 写在第一个标记之前，丢掉它就等于把角色说的话吞了（与 parser.py 的容错一致）
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

    // 一条消息要渲染（也参与搜索）的文本块。MULTI 走分段，其余是"情境 + 正文"。
    // 渲染与搜索共用它，两边的切法才不会不一致（否则命中数会对不上看到的字）
    textParts(m) {
      if (m.scenario === "MULTI") {
        return store.segmentsOf(m).map((s) => ({ kind: s.type, text: s.text }));
      }
      const out = [];
      if (m.scenario) out.push({ kind: "scenario", text: m.scenario });
      out.push({ kind: "text", text: m.content || "" });
      return out;
    },

    // 模板用的分块：有搜索计划就取它（带命中标记），否则退回纯文本块
    partsOf(m) {
      const planned = store.searchPlan.parts[m.id];
      if (planned) return planned;
      return store.textParts(m).map((p) => ({
        kind: p.kind,
        pieces: [{ text: p.text, hit: false }],
      }));
    },

    // 关键词按字面搜，正则元字符要转义，否则搜 "a.b" 会命中 "axb"
    escapeRegExp(s) {
      return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    },

    // ---- 会话内搜索 ----
    searchNext() {
      store.searchStep(1);
    },
    searchPrev() {
      store.searchStep(-1);
    },
    searchStep(step) {
      const total = store.searchTotal;
      if (!total) return;
      // 环形移动：走到头再点就绕回另一端
      store.searchIndex = ((store.searchIndex + step) % total + total) % total;
      store.scrollToHit();
    },
    clearSearch() {
      store.searchQuery = "";
      store.searchIndex = 0;
    },
    // 把当前命中滚到视野中间。等 Vue 把 .current 类挂上去之后再找元素
    scrollToHit() {
      nextTick(() => {
        const el = document.querySelector(".search-hit.current");
        if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
      });
    },

    toggleChar(id) {
      store.expandedChars[id] = !store.expandedChars[id];
    },

    sessionsOf(cid) {
      return store.sessions.filter((s) => s.character_id === cid);
    },

    async openSession(id) {
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再切换会话";
        return;
      }
      try {
        const session = await store.api(`/api/sessions/${id}`);
        if (session.mode !== store.mode) {
          // 列表已按模式过滤，正常点不到这里；防御性拦截，避免跨模式查看
          store.error = `该会话属于「${MODES[session.mode].label}」模式，请切换模式后再打开`;
          return;
        }
        store.activeSession = session;
        store.activeSessionId = id;
        store.activeByMode[session.mode] = id;
        store.messages = await store.api(`/api/sessions/${id}/messages`);
        // 背景图单独取（只有聊天与沉浸两种模式有）
        if (session.character_id) await store.loadBackgrounds(session.character_id);
        else store.resetBackgrounds();
        if (session.character_id) {
          store.expandedChars[session.character_id] = true;
        }
        store.error = "";
        store.scrollBottom();
      } catch (e) {
        store.error = e.message;
      }
    },

    async newSession() {
      if (store.mode === "director") {
        try {
          const s = await store.api(
            "/api/sessions",
            store.jsonOpts("POST", { mode: "director" })
          );
          await store.refreshSessions();
          await store.openSession(s.id);
        } catch (e) {
          store.error = e.message;
        }
        return;
      }
      if (store.characters.length === 0) {
        store.openCharacterModal();
        return;
      }
      store.newSessionModal = {
        visible: true,
        characterId: store.characters[0].id,
        title: "",
      };
    },

    async confirmNewSession() {
      try {
        const s = await store.api(
          "/api/sessions",
          store.jsonOpts("POST", {
            mode: store.mode,
            character_id: store.newSessionModal.characterId,
            title: store.newSessionModal.title,
          })
        );
        store.newSessionModal.visible = false;
        await store.refreshSessions();
        await store.openSession(s.id);
      } catch (e) {
        store.error = e.message;
      }
    },

    async createSessionForCharacter(cid) {
      try {
        const s = await store.api(
          "/api/sessions",
          store.jsonOpts("POST", { mode: store.mode, character_id: cid })
        );
        await store.refreshSessions();
        await store.openSession(s.id);
      } catch (e) {
        store.error = e.message;
      }
    },

    async removeSession(s) {
      if (store.streaming) {
        store.error = "正在生成中，请等待完成后再删除会话";
        return;
      }
      if (!(await store.ask(`删除会话「${s.title}」？其全部消息将一并删除。`))) return;
      try {
        await store.api(`/api/sessions/${s.id}`, { method: "DELETE" });
        if (store.activeSessionId === s.id) {
          store.activeSessionId = null;
          store.activeSession = null;
          store.messages = [];
          store.resetBackgrounds();
        }
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 选文件后先校验，通过就进裁剪；任何一步不过都在头像处就地提示
    // （不用底部错误条：它在没打开会话时不渲染，用户会看不到原因）
    // target: "modal"（新建/编辑角色弹窗）或 "panel"（右侧面板角色设定）
    async pickAvatar(e, target) {
      const file = e.target.files && e.target.files[0];
      e.target.value = ""; // 清掉，才能连续两次选同一个文件
      if (!file) return;
      store.avatarError = "";
      const early = avatarFileError(file.type, file.size);
      if (early) {
        store.avatarError = early;
        return;
      }
      let src;
      try {
        src = await readAsDataURL(file);
      } catch (err) {
        store.avatarError = "读取文件失败，请重试";
        return;
      }
      let img;
      try {
        img = await loadImage(src);
      } catch (err) {
        store.avatarError = "这个文件不是能识别的图片";
        return;
      }
      const later = avatarImageError(img.naturalWidth, img.naturalHeight);
      if (later) {
        store.avatarError = later;
        return;
      }
      cropImage = img;
      const natW = img.naturalWidth;
      const natH = img.naturalHeight;
      const s = coverScale(natW, natH, CROP_VIEW_PX);
      store.crop = {
        visible: true,
        target,
        src,
        view: CROP_VIEW_PX,
        natW,
        natH,
        zoom: 1,
        maxZoom: CROP_MAX_ZOOM,
        // 初始居中
        x: (CROP_VIEW_PX - natW * s) / 2,
        y: (CROP_VIEW_PX - natH * s) / 2,
        dragging: false,
      };
    },

    // 拖动：记录按下时的指针位置与图片偏移，移动时按位移换算新偏移并夹住边界
    cropDown(e) {
      const c = store.crop;
      if (!c.visible) return;
      c.dragging = true;
      store._drag = { px: e.clientX, py: e.clientY, x0: c.x, y0: c.y };
      e.currentTarget.setPointerCapture?.(e.pointerId);
    },

    cropMove(e) {
      const c = store.crop;
      if (!c.dragging || !store._drag) return;
      const d = store._drag;
      const s = coverScale(c.natW, c.natH, c.view) * c.zoom;
      c.x = clampOffset(d.x0 + (e.clientX - d.px), c.natW * s, c.view);
      c.y = clampOffset(d.y0 + (e.clientY - d.py), c.natH * s, c.view);
    },

    cropUp(e) {
      store.crop.dragging = false;
      store._drag = null;
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    },

    // 缩放时以取景框中心为锚点，图片不会突然跳走
    setCropZoom(z) {
      const c = store.crop;
      if (!c.visible) return;
      const to = Math.min(c.maxZoom, Math.max(1, Number(z) || 1));
      const next = zoomAroundCenter(c.natW, c.natH, c.view, c.zoom, to, c.x, c.y);
      c.zoom = to;
      c.x = next.x;
      c.y = next.y;
    },

    cancelCrop() {
      store.crop.visible = false;
      cropImage = null;
    },

    confirmCrop() {
      const c = store.crop;
      if (!cropImage) {
        store.cancelCrop();
        return;
      }
      const { sx, sy, side } = cropSourceRect(c.natW, c.natH, c.view, c.zoom, c.x, c.y);
      const canvas = document.createElement("canvas");
      canvas.width = AVATAR_OUT_PX;
      canvas.height = AVATAR_OUT_PX;
      const ctx = canvas.getContext("2d");
      // 先铺白底：带透明通道的 PNG/WebP 转 JPEG 时，透明处会变黑块
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
      try {
        ctx.drawImage(cropImage, sx, sy, side, side, 0, 0, AVATAR_OUT_PX, AVATAR_OUT_PX);
        const dataUrl = canvas.toDataURL("image/jpeg", AVATAR_QUALITY);
        store.avatarForm(c.target).avatar = dataUrl;
        store.avatarError = "";
        store.cancelCrop();
      } catch (err) {
        // 引用了外部资源（或跨域）的图片会污染画布，toDataURL 会抛 SecurityError
        store.avatarError = "这张图片无法处理（可能引用了外部资源），请换一张";
      }
    },

    // 头像归属的表单对象：角色弹窗 / 右侧面板角色设定 / 我的设定（用户资料）。
    // 裁剪与移除都通过它写回，不必在每处再写一遍 target 判断
    avatarForm(target) {
      if (target === "profile") return store.profileForm;
      return target === "modal" ? store.charModal.form : store.charForm;
    },

    clearAvatar(target) {
      store.avatarError = "";
      store.avatarForm(target).avatar = "";
    },

    // ---------- 对话区背景图 ----------
    resetBackgrounds() {
      store.bgImages = [];
      store.bgIndex = 0;
      // "关闭背景"是临时的：换会话/角色就恢复显示
      store.bgHidden = false;
      store.bgError = "";
    },

    // 载入当前会话角色的背景图。syncForm=true 时同步写进右侧面板的 charForm——
    // 否则在面板里一按保存就会把这组图整体提交成空。
    async loadBackgrounds(cid, syncForm = true) {
      try {
        const resp = await store.api(`/api/characters/${cid}/backgrounds`);
        store.bgImages = resp.images || [];
        store.bgMax = resp.max || BG_MAX_COUNT;
        if (store.bgIndex >= store.bgImages.length) store.bgIndex = 0;
        if (syncForm && store.activeChar && store.activeChar.id === cid) {
          store.charForm.backgrounds = [...store.bgImages];
          // 只同步基线里的 backgrounds，不要整体重拍快照：
          // 那会把面板里其它尚未保存的改动一并标记成"已保存"
          if (store.charSaved) store.charSaved.backgrounds = [...store.bgImages];
        }
      } catch (e) {
        store.bgImages = [];
      }
    },

    // 角色弹窗里可能要编辑的不是当前会话的角色，所以单独取
    async loadModalBackgrounds(cid) {
      try {
        const resp = await store.api(`/api/characters/${cid}/backgrounds`);
        if (store.charModal.editingId === cid) {
          store.charModal.form.backgrounds = resp.images || [];
          store.bgMax = resp.max || BG_MAX_COUNT;
        }
      } catch (e) {
        /* 取不到就按空处理，保存时以表单为准 */
      }
    },

    prevBg() {
      const n = store.bgImages.length;
      if (n > 1) store.bgIndex = (store.bgIndex - 1 + n) % n;
    },

    nextBg() {
      const n = store.bgImages.length;
      if (n > 1) store.bgIndex = (store.bgIndex + 1) % n;
    },

    bgList(target) {
      return (target === "modal" ? store.charModal.form.backgrounds : store.charForm.backgrounds) || [];
    },

    setBgList(target, list) {
      if (target === "modal") store.charModal.form.backgrounds = list;
      else store.charForm.backgrounds = list;
    },

    // target: "modal"（角色弹窗）或 "panel"（右侧面板角色设定）
    async addBackgrounds(e, target) {
      const files = Array.from(e.target.files || []);
      e.target.value = ""; // 清掉，才能连续两次选同一个文件
      if (!files.length) return;
      const list = store.bgList(target);
      const room = store.bgMax - list.length;
      store.bgError = "";
      if (room <= 0) {
        store.bgError = `最多只能放 ${store.bgMax} 张背景图`;
        return;
      }
      // 一次性可能选好几张大图，逐张缩放编码会占用一段时间，
      // 期间给个"处理中"状态并把按钮禁掉，避免重复点击
      store.bgBusy = true;
      const added = [];
      let problem = "";
      try {
        for (const file of files.slice(0, room)) {
          const early = backgroundFileError(file.type, file.size);
          if (early) {
            problem = early;
            continue;
          }
          let img;
          try {
            img = await loadImage(await readAsDataURL(file));
          } catch (err) {
            problem = "有文件不是能识别的图片，已跳过";
            continue;
          }
          const later = backgroundImageError(img.naturalWidth, img.naturalHeight);
          if (later) {
            problem = later;
            continue;
          }
          const { w, h } = fitSize(img.naturalWidth, img.naturalHeight, BG_MAX_PX);
          try {
            added.push(encodeJpeg(img, w, h, BG_QUALITY));
          } catch (err) {
            problem = "有图片无法处理（可能引用了外部资源），已跳过";
          }
          await new Promise((r) => setTimeout(r, 0)); // 让出主线程，界面不至于卡住
        }
      } finally {
        store.bgBusy = false;
      }
      if (added.length) store.setBgList(target, [...list, ...added]);
      if (files.length > room) problem = `最多 ${store.bgMax} 张，多选的已忽略`;
      store.bgError = problem;
    },

    removeBackground(target, i) {
      const list = [...store.bgList(target)];
      list.splice(i, 1);
      store.setBgList(target, list);
      store.bgError = "";
    },

    // 背景排序：把第 from 张移到第 to 张的位置。顺序就是对话里上一张/下一张的顺序，
    // 第一张是打开会话时默认显示的那张
    moveBackground(target, from, to) {
      const list = [...store.bgList(target)];
      if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
      const [item] = list.splice(from, 1);
      list.splice(to, 0, item);
      store.setBgList(target, list);
      store.bgError = "";
    },

    bgDragStart(e, target, i) {
      store.bgDrag = { target, index: i };
      store.bgHover = { target: null, index: null };
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        // Firefox 不设数据就不启动拖拽
        try {
          e.dataTransfer.setData("text/plain", String(i));
        } catch (err) {
          /* 忽略：设不上也不影响其它浏览器 */
        }
      }
    },

    bgDragOver(e, target, i) {
      if (store.bgDrag.index === null || store.bgDrag.target !== target) return;
      store.bgHover = { target, index: i };
    },

    bgDrop(e, target, i) {
      // 先把状态取出来再清空：moveBackground 里要用
      const drag = store.bgDrag;
      store.bgDragEnd();
      if (!drag.target || drag.target !== target || drag.index === null) return;
      store.moveBackground(target, drag.index, i);
    },

    bgDragEnd() {
      store.bgDrag = { target: null, index: null };
      store.bgHover = { target: null, index: null };
    },

    bgDragging(target, i) {
      return store.bgDrag.target === target && store.bgDrag.index === i;
    },

    bgDropTarget(target, i) {
      return store.bgHover.target === target && store.bgHover.index === i;
    },

    openCharacterModal(c = null) {
      store.avatarError = ""; // 换一个角色就清掉上一次的提示
      store.bgError = "";
      if (c) {
        store.charModal = {
          ...emptyCharModal(),
          visible: true,
          editingId: c.id,
          form: {
            name: c.name,
            appearance: c.appearance,
            personality: c.personality || "",
            speech_style: c.speech_style || "",
            backstory: c.backstory || "",
            avatar: c.avatar || "",
            backgrounds: [], // 背景图不随角色列表下发，下面单独取
          },
          locked: !!c.locked,
        };
        store.loadModalBackgrounds(c.id);
      } else {
        store.charModal = { ...emptyCharModal(), visible: true };
      }
    },

    // 让模型生成一份角色设定。开放模式把结果填进表单；探索模式只有姓名与外观，
    // 另外三项留在服务端草稿里（前端拿不到），保存时以草稿为准
    async generateCharacter() {
      const gen = store.charModal.gen;
      if (gen.busy) return;
      gen.busy = true;
      gen.error = "";
      try {
        const r = await store.api(
          "/api/characters/generate",
          store.jsonOpts("POST", { hint: gen.hint, mode: gen.mode })
        );
        store.avatarError = "";
        store.charModal.form.name = r.name || "";
        store.charModal.form.appearance = r.appearance || "";
        for (const k of LOCKED_FIELDS) {
          store.charModal.form[k] = r[k] || "";
        }
        store.charModal.locked = !!r.locked;
        gen.draftId = r.draft_id;
      } catch (e) {
        gen.error = e.message;
      } finally {
        gen.busy = false;
      }
    },

    // 换一个 / 换模式：清掉草稿与那三个字段，回到"重新生成"的状态
    resetGeneratedDraft() {
      const gen = store.charModal.gen;
      gen.draftId = null;
      gen.error = "";
      store.charModal.locked = false;
      for (const k of LOCKED_FIELDS) store.charModal.form[k] = "";
    },

    // 公开角色设定：单向、永久。确认后本地同步这三个字段，避免出现假的"未保存"
    async unlockCharacter(target) {
      const cid = target === "panel"
        ? (store.activeChar && store.activeChar.id)
        : store.charModal.editingId;
      if (!cid) return;
      const ok = await store.ask(
        "公开后将永久取消锁定，性格 / 语言风格 / 背景故事会显示出来并可以修改，且无法再锁回去。确定要公开吗？"
      );
      if (!ok) return;
      try {
        const c = await store.api(`/api/characters/${cid}/unlock`, { method: "POST" });
        const i = store.characters.findIndex((x) => x.id === cid);
        if (i >= 0) store.characters[i] = { ...store.characters[i], ...c };
        if (target === "panel") {
          for (const k of LOCKED_FIELDS) {
            store.charForm[k] = c[k] || "";
            // 快照一起写：这两处都是刚拿到的原值，不该被判成"未保存"
            store.charSaved[k] = c[k] || "";
          }
          store.charLocked = false;
          if (store.activeSession && store.activeSession.character) {
            Object.assign(store.activeSession.character, c);
          }
        } else {
          for (const k of LOCKED_FIELDS) store.charModal.form[k] = c[k] || "";
          store.charModal.locked = false;
        }
      } catch (e) {
        store.error = e.message;
      }
    },

    async saveCharacterModal() {
      // 背景图不属于角色接口的字段，单独整体提交，所以先从角色载荷里摘出去
      const { backgrounds, ...charPayload } = store.charModal.form;
      store.charModal.saveError = "";
      if (store.charModal.gen.draftId) charPayload.draft_id = store.charModal.gen.draftId;
      try {
        let cid = store.charModal.editingId;
        if (cid) {
          delete charPayload.draft_id; // 编辑已有角色时不该带草稿
          await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
        } else {
          const c = await store.api("/api/characters", store.jsonOpts("POST", charPayload));
          cid = c.id;
          store.expandedChars[c.id] = true;
        }
        await store.api(
          `/api/characters/${cid}/backgrounds`,
          store.jsonOpts("PUT", { images: backgrounds || [] })
        );
        store.charModal.visible = false;
        await store.afterCharacterChange();
      } catch (e) {
        // 弹窗里就地提示：例如应用重启导致探索模式的草稿失效，用户需要知道要重新生成
        store.charModal.saveError = e.message;
        store.error = e.message;
      }
    },

    async saveCharacterDrawer() {
      const { backgrounds, ...charPayload } = store.charForm;
      try {
        const cid = store.activeSession.character.id;
        await store.api(`/api/characters/${cid}`, store.jsonOpts("PUT", charPayload));
        await store.api(
          `/api/characters/${cid}/backgrounds`,
          store.jsonOpts("PUT", { images: backgrounds || [] })
        );
        await store.afterCharacterChange();
      } catch (e) {
        store.error = e.message;
      }
    },

    // 面板底部那个"保存当前配置"：几个标签各管各的数据，按钮只按当前标签转发。
    // 这样底部只要一个常驻按钮，不必在每个标签内容里各放一个
    saveCurrentTab() {
      if (store.panelTab === "world") return store.saveWorld();
      if (store.panelTab === "char") return store.saveCharacterDrawer();
      if (store.panelTab === "profile") return store.saveProfile();
      if (store.panelTab === "memory") return store.saveMemory();
      return store.saveGenSettings();
    },

    // ---- 世界设定（全局一份，三种模式都注入） ----
    // 加一条空词条：界面上先出现输入框，名词留空的行保存时由后端丢弃
    addTerm() {
      if (store.worldForm.terms.length >= store.limits.world_terms_max) return;
      store.worldForm.terms.push({ term: "", meaning: "" });
    },

    removeTerm(index) {
      store.worldForm.terms.splice(index, 1);
    },

    // 我的设定：整体覆盖式保存；成功后以服务端返回为准刷新基线与显示用的 profile
    async saveProfile() {
      try {
        const p = await store.api("/api/profile", store.jsonOpts("PUT", store.profileForm));
        store.profile = p;
        store.profileForm = store.snapshot(p);
      } catch (e) {
        store.error = e.message;
      }
    },

    // 世界设定：整体覆盖式保存。服务端会把"名词为空的行"丢掉、把文本 strip 掉，
    // 所以用返回结果刷新表单——用户会看到那行空词条自己消失了
    async saveWorld() {
      try {
        const w = await store.api("/api/world", store.jsonOpts("PUT", store.worldForm));
        store.world = w;
        store.worldForm = store.snapshot(w);
      } catch (e) {
        store.error = e.message;
      }
    },

    // ---- 我的设定的预设库 ----
    async loadPresets() {
      try {
        store.profilePresets = await store.api("/api/profile/presets");
        // 选中的那条可能已被删掉（比如另开一个标签页删的），清掉选择
        if (store.presetPick && !store.profilePresets.some((p) => p.id === store.presetPick)) {
          store.presetPick = "";
        }
      } catch (e) {
        store.presetError = e.message;
      }
    },

    // 载入预设：只把这四项填进表单。用户确认无误后再点底部保存——
    // 直接覆盖当前设定会让"选错了"变成不可撤销
    loadPreset() {
      store.presetError = "";
      if (!store.presetPick) return;
      const p = store.profilePresets.find((x) => x.id === store.presetPick);
      if (!p) return;
      store.profileForm = {
        name: p.name || "",
        identity: p.identity || "",
        appearance: p.appearance || "",
        avatar: p.avatar || "",
      };
    },

    async savePreset() {
      store.presetError = "";
      try {
        const p = await store.api(
          "/api/profile/presets",
          store.jsonOpts("POST", store.profileForm)
        );
        await store.loadPresets();
        store.presetPick = p.id; // 存完直接选中它，方便继续改或删
      } catch (e) {
        store.presetError = e.message;
      }
    },

    async removePreset() {
      const p = store.profilePresets.find((x) => x.id === store.presetPick);
      if (!p) return;
      if (!(await store.ask(`删除预设「${p.name}」？当前使用的设定不受影响。`))) return;
      store.presetError = "";
      try {
        await store.api(`/api/profile/presets/${p.id}`, { method: "DELETE" });
        store.presetPick = "";
        await store.loadPresets();
      } catch (e) {
        store.presetError = e.message;
      }
    },

    async removeCharacterFromModal() {
      const id = store.charModal.editingId;
      const c = store.characters.find((x) => x.id === id);
      if (!c) return;
      if (!(await store.ask(`删除角色「${c.name}」？其记忆将删除，已有会话保留但无法继续生成。`))) return;
      store.charModal.visible = false;
      await store.deleteCharacter(id);
    },

    async deleteCharacter(id) {
      try {
        await store.api(`/api/characters/${id}`, { method: "DELETE" });
        await store.afterCharacterChange();
      } catch (e) {
        store.error = e.message;
      }
    },

    async afterCharacterChange() {
      await store.refreshCharacters();
      await store.refreshSessions();
      if (store.activeSessionId) {
        store.activeSession = await store.api(`/api/sessions/${store.activeSessionId}`);
      }
      // 角色可能刚被保存或删除，背景图跟着刷新（没有角色就清空）
      if (store.activeChar) await store.loadBackgrounds(store.activeChar.id);
      else store.resetBackgrounds();
    },

    startRename() {
      if (!store.activeSession || store.renaming) return;
      store.renameText = store.activeSession.title;
      store.renaming = true;
      nextTick(() => {
        const el = document.querySelector(".title-input");
        if (el) el.focus();
      });
    },

    async saveRename() {
      if (!store.renaming) return;
      store.renaming = false;
      const title = store.renameText.trim();
      if (!title || title === store.activeSession.title) return;
      try {
        store.activeSession = await store.api(
          `/api/sessions/${store.activeSessionId}`,
          store.jsonOpts("PATCH", { title })
        );
        await store.refreshSessions();
      } catch (e) {
        store.error = e.message;
      }
    },

    async switchModel() {
      if (!store.currentModel) return;
      try {
        const s = await store.api(
          "/api/settings",
          store.jsonOpts("PUT", { model: store.currentModel })
        );
        store.currentModel = s.model;
        store.modelWarning = "";
      } catch (e) {
        // 顶栏直接提示并回退：底部错误条只在打开会话时才渲染，不能依赖它
        store.modelWarning = e.message;
        try {
          const s = await store.api("/api/settings");
          store.currentModel = s.model;
        } catch (_) {
          /* 读取失败就保持原选择 */
        }
      }
    },

    // 顶栏的思考模式开关。失败时同样在顶栏提示并回退，理由同 switchModel
    async toggleThinking() {
      try {
        const s = await store.api(
          "/api/settings",
          store.jsonOpts("PUT", { disable_thinking: !store.disableThinking })
        );
        store.disableThinking = !!s.disable_thinking;
        store.modelWarning = "";
      } catch (e) {
        store.modelWarning = e.message;
        try {
          const s = await store.api("/api/settings");
          store.disableThinking = !!s.disable_thinking;
        } catch (_) {
          /* 保持原状态 */
        }
      }
    },

    async loadMemory() {
      if (!store.memoryScope) return;
      const { type, id } = store.memoryScope;
      try {
        store.memoryData = await store.api(`/api/memories/${type}/${id}`);
        store.memoryText = store.memoryData.content;
        store.memorySaved = store.memoryText;
      } catch (e) {
        /* scope 不存在等场景：面板留空 */
      }
    },

    async saveMemory() {
      const { type, id } = store.memoryScope;
      try {
        store.memoryData = await store.api(
          `/api/memories/${type}/${id}`,
          store.jsonOpts("PUT", { content: store.memoryText })
        );
        store.memoryText = store.memoryData.content;
        store.memorySaved = store.memoryText; // 保存成功后"未保存"标识随之消失
      } catch (e) {
        store.error = e.message;
      }
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

    scheduleMemoryRefresh() {
      // 压缩是后台任务，done 后延迟拉取一次归档状态与记忆
      const sid = store.activeSessionId;
      setTimeout(async () => {
        if (store.activeSessionId !== sid) return;
        await store.refreshMessages();
        if (store.memoryScope) await store.loadMemory();
      }, 12000);
    },

    beginStream() {
      store.stopped = false;
      store.abortCtrl = new AbortController();
      store.streaming = true;
      store.streamText = "";
      store.thinkPhase = false;
    },

    // 收尾流式状态；返回本次是否被用户主动停止
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

    // 服务端在连接断开后才会把已生成的部分落库，轮询几次等它写进去
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
      if (!store.canSendText(text)) return;
      store.input = ""; // 通过校验后才清空，发不出去时不会把草稿弄丢
      await store.runSend(text);
    },

    // 导演模式的"继续"：等价于自动发一条"继续"，让模型接着上一条回复往下写。
    // 不动输入框——里面可能是用户正在写的草稿，不能被这个按钮吞掉。
    async continueGeneration() {
      if (!store.canContinue) return;
      await store.runSend(CONTINUE_PROMPT);
    },

    // 发消息与"继续"共用的发送路径，避免两处各写一遍流式处理而走偏
    async runSend(text) {
      store.error = "";
      store.lastFailedUser = null;
      store.beginStream();
      store.messages.push({ id: "tmp-user", role: "user", content: text });
      store.scrollBottom();
      let userId = null;
      let failed = false;
      try {
        await store.ssePost(
          `/api/sessions/${store.activeSessionId}/chat`,
          { message: text },
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
              });
            },
            error: (d) => {
              store.error = d.message;
              if (userId) store.lastFailedUser = { id: userId, text };
            },
          },
          store.abortCtrl.signal
        );
      } catch (e) {
        // 用户点「停止」导致的中断不算错误：部分内容已由服务端落库
        if (!store.stopped) {
          store.error = e.httpStatus ? e.message : `连接中断：${e.message}`;
          if (userId) store.lastFailedUser = { id: userId, text };
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
      const { id, text } = store.lastFailedUser;
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
      await store.send();
    },

    async copyText(m) {
      try {
        await navigator.clipboard.writeText(m.content);
      } catch (e) {
        store.error = "复制失败，请手动选择复制";
      }
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
      };
      // 打开后按内容把输入框撑到实际高度，长消息不会被塞进一个小框里
      nextTick(() => {
        document
          .querySelectorAll(".edit-modal textarea")
          .forEach((el) => store.autoGrowEl(el));
      });
    },

    autoGrow(e) {
      store.autoGrowEl(e.target);
    },

    autoGrowEl(el) {
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight + 2, 460) + "px";
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
            });
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

    // 发送键右侧的"↓"键：平滑滚到最新消息。与 scrollBottom() 分开是有意的——
    // 那个是流式输出时"跟着新内容即时贴底"，每来一小段就调用一次，必须瞬时、
    // 不能有动画，否则会一直追着一段没走完的平滑滚动跑。
    jumpToBottom() {
      const el = chatBoxEl;
      if (!el) return;
      if (typeof el.scrollTo === "function") {
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      } else {
        el.scrollTop = el.scrollHeight; // 兜底：极老的浏览器不支持带 options 的 scrollTo
      }
    },"""


# ---- 拆组件后的守卫：模板里用到的 store 成员必须在该文件声明过 ----
# 漏声明时 Vue 只在开发构建里 warning，生产构建下就是"看起来正常但点了没反应"，很难查。
STORE_KEYS = (
    set(re.findall(r"^      ([A-Za-z_$][\w$]*)[,:]", store_js, re.M))          # data 字段
    | set(re.findall(r"^store\.([A-Za-z_$][\w$]*) = computed", store_js, re.M))  # 计算属性
    | set(re.findall(r"^    (?:async )?([A-Za-z_$][\w$]*)\(", _store_methods, re.M))  # 方法
)
_SKIP = {
    "true", "false", "null", "undefined", "typeof", "instanceof", "in", "of", "new",
    "Math", "JSON", "Object", "Array", "String", "Number", "Boolean", "Date", "RegExp",
    "Error", "Promise", "Map", "Set", "Number", "parseInt", "parseFloat", "isNaN",
    "window", "document", "console", "setTimeout", "clearTimeout", "$event",
    # 注意：MODES 这类"从 store.js 具名导入的模块级常量"**不放进白名单** ——
    # 放进来等于"组件用了却不导入也算过"，而它同样是漏导入就会 ReferenceError 的名字。
    # 组件自己 import 了，就会出现在下面 _declared 里，不会误报。
}


def _ids(text: str) -> set:
    """把模板表达式里的标识符抠出来（去掉字符串字面量，且不取属性访问的后半截）。"""
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    text = re.sub(r"`(?:[^`\\]|\\.)*`", "``", text)
    return {m.group(1) for m in re.finditer(r"(?<![\w$.])([A-Za-z_][\w$]*)", text)}


for _rel, _src in zip(VUE_ORDER, vue_sources):
    _tpl = re.search(r"<template>(.*?)</template>", _src, re.S).group(1)
    _script = re.search(r"<script setup>(.*?)</script>", _src, re.S).group(1)
    _locals = set(re.findall(r'v-for="\(?([^")]*)\)?\s+in\s', _tpl))
    _locals = {x.strip().strip("{}").split(":")[-1].strip() for part in _locals for x in part.split(",")}
    if "defineProps" in _script:
        _locals |= set(re.findall(r"defineProps\(\{\s*([\w$]+):", _script))
    _declared = set(re.findall(r"^  ([A-Za-z_$][\w$]*),$", _script, re.M))
    for _chunk in re.findall(r"import \{([^}]*)\}", _script):
        _declared |= {x.strip() for x in _chunk.split(",") if x.strip()}
    _exprs = list(re.findall(r"\{\{(.*?)\}\}", _tpl, re.S))
    _exprs += re.findall(r'(?:\s(?:v-[a-z-]+|[:@][\w.-]+))="([^"]*)"', _tpl, re.S)
    _used = set()
    for _e in _exprs:
        _used |= _ids(_e)
    _missing = sorted(_used & STORE_KEYS - _declared - _locals - _SKIP)
    check(f"{_rel} 模板用到的 store 成员都已声明", _missing, [])


# ---- 消息列表只能在一处遍历（DEVELOPMENT §9.7 前端工程约定） ----
# MessageItem 是"一条消息"的组件（ChatArea 里 `v-for … :m="m"` 传进去）。它的模板里
# 如果还留着外层 v-for="m in displayMessages"，就变成 n 个组件 × 每个渲染 n 条 = n² 条
# 气泡——两条消息看着"双倍"，四条就是"8 组"。这类结构错误静态检查一点都看不见：prop
# 传了、绑定也都声明齐了，模板标识符守卫照样全绿。所以专门钉住"谁负责遍历这个列表"。
_LIST_LOOPS = [rel for rel, src in zip(VUE_ORDER, vue_sources)
               if re.search(r'v-for="[^"]*\bin\s+displayMessages\b', src)]
check("消息列表只由一个组件遍历", _LIST_LOOPS, ["components/ChatArea.vue"])
# 收单条消息的组件（定义了 m 这个 prop）不许再自己遍历整份列表
_ITEM_LOOPS = [rel for rel, src in zip(VUE_ORDER, vue_sources)
               if "defineProps" in src and re.search(r'v-for="[^"]*\bin\s+displayMessages\b', src)]
check("只收一条消息的组件不再遍历列表", _ITEM_LOOPS, [])
# 而且它必须真的用 prop（模板里读 m.xxx），否则分组渲染就成了空壳
_MI = dict(zip(VUE_ORDER, vue_sources))["components/MessageItem.vue"]
check("MessageItem 渲染的是传进来的那条消息",
      bool(re.search(r"\{\{\s*m\.|\bm\.role\b", _MI)), True)


# ---- HTML 标签配对 ----
# 先剥掉注释：注释里可以出现 <mark> 这类字面标签（说明文字里就会写），
# 浏览器会忽略注释内容，解析器也必须照做，否则会数出多余的"开标签"
VOID_TAGS = {"input", "br", "img", "hr", "meta", "link", "source", "textarea"}
markup = re.sub(r"<!--.*?-->", "", html, flags=re.S)
stack, bad = [], []
for close, name, attrs, selfc in re.findall(r"<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", markup):
    n = name.lower()
    if n in VOID_TAGS or selfc:
        continue
    if close:
        if stack and stack[-1] == n:
            stack.pop()
        else:
            bad.append((n, stack[-3:]))
    else:
        stack.append(n)
check("HTML 标签配对", (stack[-5:], bad[:2]), ([], []))

# store.js 里的三组名字：状态（reactive 的键）/ 计算属性（store.X = computed）/ 方法
# （Object.assign(store, {...}) 里的条目）。合并到一个 reactive 对象后，重名会**静默覆盖**，
# 比选项对象时代更隐蔽，所以要在这里盯住。
data = set(re.findall(r"^      ([A-Za-z_$][\w$]*)[,:]", store_js, re.M))
computed = set(re.findall(r"^store\.([A-Za-z_$][\w$]*) = computed", store_js, re.M))
methods = set(re.findall(r"^    (?:async )?([A-Za-z_$][\w$]*)\(", _store_methods, re.M))
_watch_src = re.search(r"const watchDefs = \{(.*?)\n\};", store_js, re.S).group(1)
watch = set(re.findall(r'^    "?([A-Za-z_$][\w$."]*)"?\(', _watch_src, re.M))
check("三组键名无重名", sorted((data & computed) | (data & methods) | (computed & methods)), [])
check("methods 数量合理（提取器没漏）", len(methods) > 60, True)
check("状态字段数量合理", len(data) > 50, True)
check("watch 有内容", len(watch) > 3, True)

# 模板里引用的方法与数据必须存在（写错名字 Vue 只会静默不生效/告警）
refs = set(re.findall(r'@click="([A-Za-z_$][\w$]*)\s*\(', html))
missing = sorted(refs - methods)
check("模板调用的方法都存在", missing, [])

# 探索模式：前端常量必须与后端一致，否则锁定的字段名对不上，界面会"漏"出来
check("前端锁定字段与后端 HIDDEN_FIELDS 一致",
      f'const LOCKED_FIELDS = {list(HIDDEN_FIELDS)!r};'.replace("'", '"') in js, True)

# 关键结构都在
check("弹窗有生成区", 'class="gen-box"' in html, True)
check("有开放/探索模式选择", ('value="open"' in html) and ('value="explore"' in html), True)
check("两处锁定占位（面板 + 弹窗）", html.count('class="locked-box"'), 2)
check("两个公开角色设定按钮", html.count(">公开角色设定</button>"), 2)
check("解锁有确认弹窗文案", "永久取消锁定" in js, True)
check("保存带 draft_id", "charPayload.draft_id = this.charModal.gen.draftId" in js, True)
check("保存失败在弹窗内提示", "charModal.saveError" in js and "charModal.saveError" in html, True)
check("样式含 gen-box / locked-box", (".gen-box" in css) and (".locked-box" in css), True)

# 发送键旁的"回到最新"键（DEVELOPMENT §9.6 界面约定 顺带加的）
check("有 ↓ 键", 'class="jump-btn"' in html, True)
check("↓ 在发送行内", html.index('class="send-row"') < html.index('class="jump-btn"'), True)
check("有 jumpToBottom 方法", "jumpToBottom" in methods, True)

# 弹窗变体宽度必须压得住基础 .modal（DEVELOPMENT §9.6 界面约定 的坑）
check("编辑弹窗宽度用复合选择器", ".modal.edit-modal { width: 780px; }" in css, True)
check("裁剪弹窗宽度用复合选择器", ".modal.crop-modal { width: 380px;" in css, True)
check("角色弹窗宽度用复合选择器并与编辑弹窗同宽",
      ".modal.char-modal { width: 780px; }" in css, True)
check("操作行按键不被压缩", ".edit-btns { display: flex; flex: none; gap: 8px; }" in css, True)

# 角色弹窗里的填写框默认高度（不能只靠 rows，样式里也要有下限）
check("角色弹窗文本框有最小高度", "min-height: 118px;" in css, True)
check("背景故事框更高", ".modal.char-modal .field textarea.grow-lg" in css, True)
check("背景故事框用了 grow-lg 类", 'class="grow-lg"' in html, True)
check("宽度规则不作用于右侧面板",
      ".modal.char-modal .field textarea {" in css and css.count(".modal.char-modal .field") >= 2, True)

# ---- 右侧面板改成标签页 ----
check("有标签栏", html.count('class="panel-tabs"'), 1)
check("标签按钮（模板里五个，导演模式少两个）", html.count('class="panel-tab"'), 5)
check("内容面板（模板里五个）", html.count("panel-tab-pane"), 5)
check("旧的折叠结构已清除",
      [w for w in ("panel-section", "panelFold", "togglePanelFold") if (w in html or w in js)], [])
check("CSS 里的折叠样式已清除", ".panel-section" in css_code, False)
check("未保存圆点样式在", ".tab-dot" in css, True)
check("当前标签的未保存状态有计算属性", "activeTabDirty" in js and "activeTabDirty" in html, True)
# ---- "配置"开关：常驻 + 改名 + 位置固定（面板开合都不动）（DEVELOPMENT §9.6 界面约定） ----
check("面板里没有标题行（开关不搬进面板）", 'class="panel-head"' not in html, True)
check("面板里没有第二个开关", 'class="panel-title"' not in html, True)
check("顶栏那一份没有 v-if（常驻，不随会话/面板出现消失）",
      re.search(r'<button v-if="[^"]*" class="ghost-btn panel-toggle"', html), None)
check("无会话时禁用", ':disabled="!activeSession"' in html, True)
check("禁用样式有定义（否则看起来仍可点）", ".ghost-btn:disabled {" in css, True)
check("开关在顶栏里（位置固定在工具栏最右）",
      html.index('class="toolbar"') < html.index("panel-toggle") < html.index("</header>"), True)
# 顶栏必须横跨"对话区 + 面板"：面板是 .main 的兄弟列时，面板一开顶栏就窄 330px，
# 按钮会左移并落到面板标签上（DEVELOPMENT §9.6 界面约定 第二版的真实事故）。这条断言把结构钉住
_app_tpl = re.search(r"<template>(.*?)</template>", vue_sources[0], re.S).group(1)
check("App 骨架里 TopBar 在 .work 之前（宽度不受面板影响）",
      _app_tpl.index("<TopBar />") < _app_tpl.index('class="work"'), True)
check("TopBar 组件的根节点是 header.topbar",
      '<header class="topbar"' in vue_sources[VUE_ORDER.index("components/TopBar.vue")], True)
check("对话区与面板在同一行里并排（对话区在 .work-main 内）",
      html.index('class="work"') < html.index('class="work-main"') < html.index('class="chat-area"')
      and html.index('class="chat-area"') < html.index('class="panel"'), True)
check("这两层容器的样式都在", ".work {" in css and ".work-main {" in css, True)
# 文案只换箭头、字数不变，所以按钮宽度不随状态变化（"不挪鼠标点开、看一眼、再点关"）
check("文案按状态只换箭头",
      'activeSession && !panelCollapsed ? "配置 ‹" : "配置 ›"' in html, True)
check("旧文案'面板'已清除",
      any(w in html for w in ("面板 ‹", "面板 ›", ">面板</h2>", "收起面板")), False)
check("标题提示随状态变化",
      "(panelCollapsed ? '展开配置面板' : '收起配置面板')" in html, True)

# ---- 分隔线：左右两侧同一条（DEVELOPMENT §9.6 界面约定） ----
check("分隔线定义成变量", "--divider: 2px solid #d7dae1;" in css, True)
check("三处分区线都用它（面板标签栏 / 左侧标题 / 左侧模式按钮）",
      css.count("border-bottom: var(--divider);"), 3)
check("标签边框常驻（不再只给选中项画边）",
      bool(re.search(r"\.panel-tab \{[^}]*\}", css))
      and "border: 1px solid var(--border);" in re.search(r"\.panel-tab \{[^}]*\}", css).group(0)
      and "border: 1px solid transparent;" not in re.search(r"\.panel-tab \{[^}]*\}", css).group(0),
      True)
on_tab_css = re.search(r"\.panel-tab\.on \{[^}]*\}", css)
check("选中标签用强调色边框区分",
      bool(on_tab_css) and "border-color: var(--accent);" in on_tab_css.group(0), True)

# ---- 字数上限与右下角实时提示 ----
counters = html.count('class="char-count')
check("计数提示数量（含底部输入区情境/话语两栏、我的设定三项、世界设定三项与词条两项）",
      counters, 27)
check("每个计数器都有 .counted 定位父层", html.count('class="counted') >= counters, True)
check("计数方法在", "isNear(value, max)" in js and "len(value)" in js, True)
# 所有自由文本输入都要有 maxlength（文件选择、单选、滑杆除外）；会话内搜索框是
# 界面过滤器、不落库，也不该占一个上限，所以单独放行
free_boxes = []
for tag, attrs in re.findall(r"<(input|textarea)([^>]*)>", html, flags=re.S):
    if tag == "input" and any(k in attrs for k in ('type="file"', 'type="radio"', 'type="range"')):
        continue
    if "search-input" in attrs:
        continue
    if ":maxlength" not in attrs:
        free_boxes.append(attrs.strip().splitlines()[0][:60])
check("没有漏掉 maxlength 的文本输入", free_boxes, [])
check("上限从后端取", 'this.limits = await this.api("/api/limits")' in js, True)
# 前端兜底值与后端必须一致，否则接口拿不到时两边限制不同
from app.limits import LIMITS  # noqa: E402

for key, value in LIMITS.items():
    if f"{key}: {value}" not in js:
        free_boxes.append(f"{key}={value}")
check("前端兜底上限与后端一致", free_boxes, [])
# 单行框的提示要垂直居中（否则贴底边很挤），且注释说明了为什么
check("单行提示有 inline 变体", ".char-count.inline" in css and "char-count inline" in html, True)
check("接近上限时变色", ".char-count.near" in css, True)

# ---- 关闭背景（放在翻页键旁边） ----
check("背景条用 showBgBar",
      html.count('v-if="showBgBar"'), 1)
check("有关闭背景键", 'class="bg-close"' in html, True)
check("关闭/显示两种文案", ("关闭背景" in html) and ("显示背景" in html), True)
check("关闭后背景条仍在（不依赖 chatBgUrl）",
      "!!this.activeChar && this.bgImages.length > 0" in js, True)
check("关掉背景时回落到空白", "|| this.bgHidden" in js, True)
check("切会话或角色时恢复显示", "this.bgHidden = false;" in js, True)
check("单张背景时翻页键置灰", ':disabled="bgImages.length < 2"' in html, True)
check("关闭键要压得住 .bg-switch button 的 28px",
      ".bg-switch button.bg-close {" in css, True)

# ---- 标签栏必须在滚动容器外面（否则内容一长就被滚轮带走） ----
check("标签栏排在滚动容器之前", html.index('class="panel-tabs"') < html.index('class="panel-body"'), True)
check("标签内容面板在滚动容器之内",
      html.index('class="panel-body"') < html.index("panel-tab-pane"), True)
check("标签栏与还原行都不参与伸缩", css.count(".panel-tabs {") == 1 and "flex: none;" in css, True)
check("滚动容器仍是 panel-body", "overflow-y: auto;" in css and ".panel-body {" in css, True)

# ---- 消息上方那一行：说话人 + 发送时间 ----
check("有名字与时间的那一行", 'class="msg-head"' in html, True)
check("时间只在消息行里出现一次（流式占位没有）", html.count('class="msg-time"'), 1)
check("时间在气泡之前（上方那一行）",
      html.index('class="msg-time"') < html.index('class="msg-actions"'), True)
check("时间在 msg-head 行里", html.index('class="msg-head"') < html.index('class="msg-time"'), True)
check("名字与时间同一行", 'class="msg-head"' in html and 'class="msg-name"' in html, True)
check("时间样式在", ".msg-time {" in css, True)
check("user 侧那一行仍靠右（由 bubble-wrap 的 align-items 决定）",
      ".msg.user .bubble-wrap { align-items: flex-end; }" in css, True)
check("有时间格式化方法", "timeOf(m)" in js and "fullTimeOf(m)" in js, True)
check("时间取 created_at 的时分秒", 's.slice(11, 19)' in js, True)

# ---- 我的设定（用户资料） ----
check("有我的设定标签", ">我的设定<span" in html, True)
check("我的设定面板在", 'panelTab === \'profile\'' in html, True)
check("面板顶部的输出倾向已改名", "输出倾向" in html or "genSectionTitle" in js, False)
check("生成要求标签写死文案", '>生成要求<span' in html, True)
check("用户头像有第三个 target", "pickAvatar($event, 'profile')" in html, True)
check("头像归属有统一入口", "avatarForm(target)" in js, True)
check("我的设定有独立的脏标记与还原", "profileDirty" in js and 'section === "profile"' in js, True)
check("保存派发包含我的设定", 'if (this.panelTab === "profile") return this.saveProfile();' in js, True)
check("启动时加载我的设定", 'await this.api("/api/profile")' in js, True)

# ---- 世界设定（全局一份，三种模式都用得上） ----
check("有世界设定标签", ">世界设定<span" in html, True)
check("世界设定面板在", "panelTab === 'world'" in html, True)
check("世界设定标签不判模式（导演模式也显示）",
      "v-if" not in re.search(r"<button([^>]*)panelTab = 'world'", html).group(1), True)
check("世界设定有独立的脏标记与还原", "worldDirty" in js and 'section === "world"' in js, True)
check("保存派发包含世界设定", 'if (this.panelTab === "world") return this.saveWorld();' in js, True)
check("启动时加载世界设定", 'await this.api("/api/world")' in js, True)
check("词条可增可删", "addTerm()" in js and "removeTerm(index)" in js, True)
check("到上限后不能再加词条",
      ':disabled="worldForm.terms.length >= limits.world_terms_max"' in html, True)
check("名称注明不发给模型", "只用于自己辨认，不发给模型" in html, True)
check("词库说明写清空行会被丢弃", "名词留空的行在保存时自动丢弃" in html, True)
# 5 个标签在 330px 面板里等分只有约 56px，四字标签需要约 68px：必须能换行
tabs_css = re.search(r"\.panel-tabs \{[^}]*\}", css)
check("标签栏可换行", bool(tabs_css) and "flex-wrap: wrap;" in tabs_css.group(0), True)
check("标签栏仍不参与伸缩", bool(tabs_css) and "flex: none;" in tabs_css.group(0), True)
# 实测：基准 56px 时 5 个标签挤在一行、每格 56px，四个汉字要 56px 以上 → 被截成"生成要…"；
# 30% 时排成 3+2、每格 97px，不截断。改这个数字前请重新量一遍
tab_css = re.search(r"\.panel-tab \{[^}]*\}", css)
check("标签基准宽度能排下三个（30%）", bool(tab_css) and "flex: 1 1 30%;" in tab_css.group(0), True)
check("消息按模式取名字", "msgName(m)" in js and "msgName(m)" in html, True)
check("用户头像列有显示条件", "showUserSide" in js and "showUserSide" in html, True)
check("导演模式不显示用户头像列", "return !!this.activeChar && !!(this.profile.avatar || this.profile.name);" in js, True)
check("用户头像列排在气泡之后（渲染到右侧）",
      html.rindex('class="msg-side"') > html.index('class="bubble-wrap"'), True)
check("那一行排在气泡之前（显示在上方）",
      html.index('class="msg-head"') < html.index('class="bubble"'), True)
# 两侧气泡到头像的间距要一致（user 那侧的头像是后加的，漏了 gap 就会紧贴）
check("两侧消息用同一份间距",
      ".msg.user,\n.msg.assistant { align-items: flex-start; gap: 12px; }" in css, True)
# user 侧与模型侧镜像：时间在名字左边
check("user 侧时间换到名字左边", ".msg.user .msg-head { flex-direction: row-reverse; }" in css, True)
# "已编辑"标记不渲染（数据字段仍在，只是不显示）
check("页面里没有「已编辑」标记", ("已编辑" in html) or ("edited-flag" in css), False)

# ---- 弹窗底部的操作行钉底 ----
check("两个弹窗各有字段滚动区", html.count('class="modal-body"'), 2)
check("弹窗外层保留滚动兜底", ".modal {" in css and "overflow-y: auto;" in css, True)
check("字段区是弹窗里唯一滚动区",
      ".modal-body {" in css and "flex: 1 1 auto;" in css and "min-height: 0;" in css, True)
check("角色弹窗的操作行在字段区之外",
      html.rindex('class="modal-actions"') > html.rindex('class="modal-body"'), True)
check("编辑弹窗的操作行在字段区之外",
      html.rindex('class="edit-actions"') > html.index('class="modal-body"'), True)
check("保存失败提示也在字段区之外（与按钮一起常驻）",
      html.index('charModal.saveError') > html.index('class="modal-body"'), True)

# ---- 会话内搜索 ----
check("顶栏有搜索框", 'class="search-box"' in html and 'class="search-input"' in html, True)
check("搜索框在工具栏里（配置开关之前）",
      html.index('class="search-box"') < html.index("panel-toggle"), True)
check("搜索框只在有会话时出现", 'v-if="activeSession" class="search-box"' in html, True)
check("Enter / Shift+Enter / Esc 都接上了",
      ('@keydown.enter.exact.prevent="searchNext"' in html)
      and ('@keydown.shift.enter.prevent="searchPrev"' in html)
      and ('@keydown.esc="clearSearch"' in html), True)
check("有命中计数与上一个/下一个（清空走 Esc）",
      ('class="search-count"' in html) and ('@click="searchPrev"' in html)
      and ('@click="searchNext"' in html) and ('@keydown.esc="clearSearch"' in html), True)
check("命中处标黄且区分当前项",
      ("mark.search-hit {" in css) and ("mark.search-hit.current {" in css), True)
check("消息正文走分块渲染（便于标黄）", "partsOf(m)" in html and "partsOf(m)" in js, True)
check("搜索与渲染共用切块", "textParts(m)" in js and "this.textParts(m)" in js, True)
check("关键词按字面转义（元字符不当正则用）", "escapeRegExp(s)" in js, True)
check("只搜显示中的消息", "for (const m of this.displayMessages)" in js, True)
check("跳转是环形的", "((this.searchIndex + step) % total + total) % total" in js, True)
check("换关键词后回到第一处并滚动", "searchQuery() {" in js and "scrollToHit()" in js, True)
# 尺寸稳定：计数与按键始终占位（曾经按有无关键词显示/隐藏，输入前后整框会变宽变窄）
check("计数与按键不按关键词显隐", 'v-if="searchQuery"' in html, False)
check("搜索框里只有上一个/下一个两个键",
      len(re.findall(r'class="icon-btn"[^>]*@click="search(?:Prev|Next)"', html)), 2)
check("清空靠 Esc（不再多放一个清空键占宽度）", "清空搜索" in html, False)
check("搜索框与计数都不伸缩",
      ".search-box {\n  flex: none;" in css and "min-width: 42px;" in css, True)
# 按钮必须显式 opacity: 1——.icon-btn 默认是"悬停才显形"（给侧栏用的），
# 照搬过来会让按钮可点却看不见
check("搜索框按键可见", ".search-box .icon-btn {\n  flex: none;\n  opacity: 1;" in css, True)
check("搜索框在模型选择左边",
      html.index('class="search-box"') < html.index('class="model-select"'), True)
check("顶栏放不下时换行而不是溢出", "flex-wrap: wrap;" in css, True)

# ---- "面板"按钮上的小点不能改变按钮尺寸 ----
check("面板按钮可作定位父层", ".panel-toggle { position: relative; }" in css, True)
check("小点是绝对定位且不吃外边距",
      ".panel-toggle .dirty-dot {" in css and "position: absolute;" in css
      and "margin: 0;" in css, True)

# ---- 左侧栏的"模式选择" ----
check("左侧栏有模式选择标题", '<div class="side-label">模式选择</div>' in html, True)
check("标题在模式按钮之前",
      html.index('class="side-label"') < html.index('class="mode-tabs"'), True)
check("标题样式在", ".side-label {" in css, True)


def css_block(sel):
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def css_rule(sel):
    """选择器**完全等于** sel 的那条规则。

    css_block 是"按前缀找"，遇到共用规则（`.mode-tip, .hint-tip { … }`）会先撞上它，
    所以这种场景要按整条选择器精确匹配。
    """
    for _s, _b in re.findall(r"([^{}]+)\{([^{}]*)\}", css_code):
        if _s.strip() == sel:
            return _b
    return ""


def css_font_size(sel):
    m = re.search(r"font-size:\s*(\d+)px", css_block(sel))
    return int(m.group(1)) if m else 0


# 用户要求：标题居中加粗、字号调大，并在与模式按钮之间加一条分隔线
sl = css_block(".side-label")
check("标题居中", "text-align: center;" in sl, True)
check("标题加粗", "font-weight: 700;" in sl, True)
check("标题字号比模式按钮大", css_font_size(".side-label") > css_font_size(".mode-tab"), True)
check("标题底部有分隔线（与右侧面板同一条）", "border-bottom: var(--divider);" in sl, True)

# ---- 模式按钮的介绍浮层（鼠标移上去/键盘聚焦时显示这个模式是干什么的） ----
_helpers_src = (frontend / "src/store/helpers.js").read_text(encoding="utf-8")
_modes_src = _helpers_src[_helpers_src.index("export const MODES"):]
_modes_src = _modes_src[:_modes_src.index("\n};")]
check("三种模式的介绍都写在 MODES 里（单一数据源）",
      [m for m in ("chat", "immersive", "director")
       if not re.search(rf"{m}: \{{[^}}]*hint:", _modes_src, re.S)], [])
_side_src = dict(zip(VUE_ORDER, vue_sources))["components/SideBar.vue"]
check("侧栏渲染介绍浮层", 'class="mode-tip"' in _side_src and "MODES[hoveredMode].hint" in _side_src, True)
check("鼠标移入与键盘聚焦都显示",
      all(k in _side_src for k in ('@mouseenter="hoveredMode = key"', "@mouseleave=\"hoveredMode = ''\"",
                                   '@focus="hoveredMode = key"', "@blur=\"hoveredMode = ''\"")), True)
_tip = css_block(".mode-tip")
# 两种浮层共用一条规则（.mode-tip, .hint-tip { ... }），css_block 会先撞上它，
# 所以这里单独取：共用块 + .hint-tip 自己的定位块
_shared_m = re.search(r"\.mode-tip,\s*\.hint-tip\s*\{([^}]*)\}", css)
_shared_tip = _shared_m.group(1) if _shared_m else ""
_hint_css = css_rule(".hint-tip")
check("介绍浮层绝对定位（不改变布局）", "position: absolute;" in _tip, True)
check("介绍浮层不吃鼠标（否则自己把自己关掉）", "pointer-events: none;" in _shared_tip, True)
check("浮层的父层可作定位参照", "position: relative;" in css_block(".mode-tabs"), True)

# ---- 面板底部常驻的保存区 ----
check("只有一个保存键且改名为「保存当前配置」", html.count(">保存当前配置</button>"), 1)
check("面板里旧的保存文案已清除",
      [w for w in ("保存生成要求", "保存记忆") if w in html], [])
check("保存区在滚动容器之外",
      html.index('class="panel-footer"') > html.index('class="panel-body"'), True)
check("保存区不参与伸缩", ".panel-footer {" in css and "flex: none;" in css, True)
check("未保存 / 还原移到了保存区",
      html.index('class="dirty-flag"') > html.index('class="panel-footer"'), True)
check("保存按当前标签派发",
      'if (this.panelTab === "char") return this.saveCharacterDrawer();' in js
      and "return this.saveMemory();" in js and "return this.saveGenSettings();" in js, True)
check("姓名为空时不能保存",
      "store.saveDisabled = computed(" in store_js
      and ':disabled="saveDisabled"' in html, True)
check("面板里不再有删除角色", html.count(">删除角色</button>"), 1)  # 只剩角色弹窗里那个
check("面板用的删除方法已删除", "async removeCharacter()" in js, False)
check("弹窗用的删除方法还在", "removeCharacterFromModal" in js, True)

# 生成区说明里要交代模型与思考开关（用户问过生成是否跟随它们）
check("生成区说明提到当前模型", "用当前选中的模型" in html, True)
check("生成区说明提到思考开关", "跟着顶栏的思考开关走" in html, True)

# 头像入口：面板与弹窗的按钮文案必须一致（曾经一个写"选择图片"、一个写"选择头像"）
picker = re.findall(r'class="ghost-btn file-btn">\{\{([^}]*)\}\}', html)
normalized = sorted(re.sub(r"(?:char(?:Modal\.form|Form)|profileForm)\.avatar", "AV", p).strip() for p in picker)
check("三处头像按钮都在（面板 / 弹窗 / 我的设定）", len(picker), 3)
check("三处头像按钮同文案（无头像=上传头像 / 有头像=更换头像）",
      normalized, ['AV ? "更换头像" : "上传头像"'] * 3)
check("没有遗留的旧文案", [w for w in ("选择头像", "选择图片") if w in html], [])

# ---- 我的设定的预设 ----
check("有预设下拉", 'class="preset-select"' in html and '@change="loadPreset"' in html, True)
check("下拉列出预设（名字 + 身份）",
      'v-for="p in profilePresets"' in html and "p.identity" in html, True)
check("有存为预设与删除预设", (">存为预设</button>" in html) and (">删除预设</button>" in html), True)
check("没有预设时给出提示", "还没有预设" in html, True)
check("预设方法齐全",
      all(k in js for k in ("async loadPresets()", "loadPreset() {", "async savePreset()",
                            "async removePreset()")), True)
# 载入预设只填表单、不直接落库（否则"选错了"就不可撤销），仍走底部保存
_load = js[js.index("loadPreset() {"):js.index("async savePreset()")]
check("载入预设不写库", "this.api(" in _load, False)
check("载入预设填的是这四项",
      all(f"{k}: p.{k}" in _load for k in ("name", "identity", "appearance", "avatar")), True)
check("启动时拉预设列表", "await this.loadPresets();" in js, True)
check("删除预设要确认", "删除预设「" in js, True)
check("预设样式在", ".preset-row {" in css and ".preset-select {" in css, True)

# ---- 没选模型时的提示 ----
check("启动时若没选模型会提示", "还没有选择模型，生成前请先在左边选一个" in js, True)
check("没选模型时思考开关置灰",
      "if (!this.currentModel) return false;" in js and "还没有选择模型，先在左边选一个" in js, True)

# ---- 拆 store 后的守卫：模块里用到的"模块级名字"必须导入或就地声明（DEVELOPMENT §9.7 前端工程约定） ----
# 星形依赖的代价是每个模块都得自己 import 用到的 helper。漏一个，打包器不会吭声
# （ESM 是静态的，缺的标识符只在真的执行到那一行才 ReferenceError），于是
# "点开角色弹窗就崩"这种问题只能靠人拿浏览器点出来。这里把它变成静态检查。
_LIT = re.compile(
    r'"(?:\\.|[^"\\])*"' r"|'(?:\\.|[^'\\])*'" r"|`(?:\\.|[^`\\])*`"
    r"|//[^\n]*" r"|/\*.*?\*/", re.S)
_VUE_APIS = ("computed", "watch", "watchEffect", "nextTick", "reactive", "ref", "toRefs",
             "onMounted", "onBeforeUnmount", "shallowRef")


def _declared_names(src: str) -> set:
    """顶层声明（含 export）与顶层解构出来的名字。"""
    out = set(re.findall(
        r"^(?:export\s+)?(?:const|let|var|function|async\s+function|class)\s+([A-Za-z_$][\w$]*)",
        src, re.M))
    for _m in re.finditer(r"^(?:export\s+)?(?:const|let|var)\s*\{([^}]*)\}", src, re.M):
        for _part in _m.group(1).split(","):
            _n = _part.split(":")[-1].strip().split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                out.add(_n)
    return out


def _local_names(src: str) -> set:
    """模块里本地可用的名字：import 进来的（含 as 重命名）+ 顶层声明的。"""
    out = _declared_names(src)
    for _re_m in re.finditer(r"^export\s*\{([^}]*)\}\s*from\s*[\"'][^\"']+[\"'];", src, re.M):
        for _p in _re_m.group(1).split(","):  # barrel 的转发导出
            _n = _p.split(" as ")[-1].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                out.add(_n)
    for _im in re.finditer(r"^import\s+(.+?)\s+from\s+[\"'][^\"']+[\"'];", src, re.M):
        _clause = _im.group(1)
        _dm = re.match(r"([A-Za-z_$][\w$]*)", _clause)
        if _dm:
            out.add(_dm.group(1))
        _br = re.search(r"\{([^}]*)\}", _clause, re.S)
        if _br:
            for _p in _br.group(1).split(","):
                _n = _p.strip().split(" as ")[-1].strip()
                if re.fullmatch(r"[A-Za-z_$][\w$]*", _n):
                    out.add(_n)
    return out


def _uses(code: str, name: str) -> bool:
    # 先把展开/剩余运算符 ...x 抹平：否则 "..." 会被误当成属性访问而漏判
    # （第一版生成器就是这样漏掉 ...emptyCharModal() 的）
    return re.search(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])",
                     code.replace("...", " ")) is not None


# 待查的"外部名字"= 所有 store 模块顶层声明的名字（helpers 的常量/纯函数、state 里的
# 私有量与导出……凡是在别处顶层声明过的都算）+ 会用到的 vue 具名导出。
# 注意别只取 helpers.js 的导出：chat.js 用了 state.js 的 chatBoxEl、character.js 用了
# helpers 的 emptyCharModal，两次都漏在同一类地方。
_MOD_NAMES = set()
for _f in store_files:
    _MOD_NAMES |= _declared_names(_f.read_text(encoding="utf-8"))
for _f in store_files:
    _rel = str(_f.relative_to(frontend / "src")).replace("\\", "/")
    if _f.name == "helpers.js":
        continue
    _raw = _f.read_text(encoding="utf-8")
    _code = _LIT.sub(" ", _raw)
    _have = _local_names(_raw)
    _miss = [n for n in sorted(_MOD_NAMES) + list(_VUE_APIS) if _uses(_code, n) and n not in _have]
    check(f"{_rel} 用到的模块级名字都有来源", _miss, [])
    _dead = [n for n in sorted(_local_names(_raw) - _declared_names(_raw)) if not _uses(_code, n)]
    check(f"{_rel} 没有导入了却没用到的名字", _dead, [])

# ---- 弹窗怎么关：只有"按下"就落在遮罩上，才算点了窗口外（11 处回归） ----# 用 @click.self 的坑：click 的目标是 mousedown 与 mouseup 的**共同祖先**。在弹窗里按住
# 鼠标选文字、拖到遮罩上（或拖出窗口）再松开时，click 会落到遮罩上，于是"点窗口外关闭"
# 被误触发——用户选个文字窗口就没了。判据必须是"按下"的位置。
check("弹窗不再用 @click.self 关闭", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      if "modal-mask" in src and "@click.self" in src], [])
_mask_modals = [rel for rel, src in zip(VUE_ORDER, vue_sources) if "modal-mask" in src]
check("五个弹窗都在", len(_mask_modals), 5)
check("每个弹窗走同一套关闭判定", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      if "modal-mask" in src and not all(k in src for k in (
          "useMaskClose(", '@mousedown="onMaskDown"', '@mouseup="onMaskUp"', '@click="onMaskClick"'))], [])

# ---- 沉浸模式的输入区是两栏：情境（可选）+ 话语（必选） ----
# "话语必填、情境可空"这件事靠"发送键还是绑 store.input"来保证：只填情境时发送键必须是禁用的，
# 所以这里同时钉住两件事——两栏各自绑对字段、发送键不允许换成看情境。
_input_bar = dict(zip(VUE_ORDER, vue_sources))["components/InputBar.vue"]
check("情境栏绑 inputScenario", 'v-model="inputScenario"' in _input_bar, True)
check("话语栏仍绑 input", 'v-model="input"' in _input_bar, True)
check("情境栏只在沉浸模式出现", 'v-if="isImmersiveMode" class="input-field scenario-field"' in _input_bar, True)
check("两栏各有自己的上限（情境 scenario / 话语 message）",
      ":maxlength=\"limits.scenario\"" in _input_bar and ":maxlength=\"limits.message\"" in _input_bar, True)
check("话语必填：发送键仍看 input",
      ':disabled="!input.trim() || orphanActive"' in _input_bar, True)
check("两栏都支持 Enter 发送", _input_bar.count('@keydown.enter.exact.prevent="send"') == 2, True)
check("store 里有 inputScenario", "inputScenario: \"\"" in store_js, True)
# 注意：js 这一坨把 store. 换成了 this.（为了让老的选项对象断言能复用），所以这里不写前缀
check("沉浸模式的模式判定在", "isImmersiveMode = computed" in js, True)
check("发送时把情境一起带上（SSE 请求体）", "{ message: text, scenario: scenario || null }" in js, True)
check("乐观插入的 user 消息带情境", 'role: "user", content: text, scenario: scenario || null' in js, True)
check("失败重试也恢复情境", "inputScenario = scenario" in js, True)
_ib_css = css_block(".input-field")
check("两栏用标签区分（两个并排的框没标签会分不清）",
      ".input-field-label {" in css and ".input-field.scenario-field { flex: 0 0 36%; }" in css
      and "flex-direction: column;" in _ib_css, True)

# ---- 悬停提示统一走 v-hint（不用原生 title） ----
# 原生 title 延迟约一秒、样式跟浏览器走、不能换行；统一用自研浮层（composables/hint.js +
# App.vue 里的单例 .hint-tip），视觉与模式介绍浮层共用一套 CSS。
_all_vue = "\n".join(vue_sources)
check("组件里不再有原生 title",
      [rel for rel, src in zip(VUE_ORDER, vue_sources) if re.search(r'(?<![\w-])title\s*=', src)], [])
check("悬停提示都用 v-hint", len(re.findall(r'v-hint="', _all_vue)) >= 30, True)
check("指令在入口注册", 'directive("hint", hintDirective)' in main_js, True)
check("浮层挂在根组件", 'class="hint-tip"' in _all_vue and "hintText" in _all_vue, True)
check("指令模块在", (frontend / "src/composables/hint.js").exists(), True)
# 两种浮层共用一套视觉；.hint-tip 是 fixed 定位、不吃鼠标、层级高于弹窗遮罩（1200）
check("两种浮层共用一套样式",
      "pointer-events: none;" in _shared_tip and "background: #2f3441;" in _shared_tip, True)
check("v-hint 浮层定位与层级",
      "position: fixed;" in _hint_css and "z-index: 1300;" in _hint_css, True)
check("浮层层级高于弹窗遮罩", "z-index: 1200" in css and "z-index: 1300;" in _hint_css, True)
# 纯图标按钮（可见内容是个符号）去掉 title 后必须能读出来
check("图标按钮都有 aria-label", [rel for rel, src in zip(VUE_ORDER, vue_sources)
      for _l in src.splitlines()
      if "v-hint=" in _l and re.search(r">\s*(✎|✕|‹|›|×|↑|↓|☰)\s*<", _l) and "aria-label" not in _l], [])

# ---- 双击编辑已去掉；自带文字的按钮不加悬停提示 ----
# 双击是"看不见的入口"（用户得先知道有这回事），与旁边的「编辑」按钮重复；
# 而「复制 / 编辑 / 删除 / 重新生成」四个键自己就写着字，再弹一张卡片纯属噪音。
_mi = dict(zip(VUE_ORDER, vue_sources))["components/MessageItem.vue"]
check("气泡不再双击进编辑", "@dblclick" in _mi, False)
check("气泡上没有悬停提示", 'class="bubble"' in _mi and 'class="bubble" v-hint' in _mi, False)
_actions_from = _mi.index('class="msg-actions"')
_actions = _mi[_actions_from:_mi.index("</div>", _actions_from)]
check("操作条按钮（自带文字）不加提示", "v-hint" in _actions, False)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("前端结构与命名用例全部通过")
