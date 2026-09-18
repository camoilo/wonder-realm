const MODES = {
  character_chat: { label: "角色对话", character: true },
  character_scenario: { label: "角色情境", character: true },
  free_scenario: { label: "自由情境", character: false },
};

const SEGMENT_RE = /\[(SCENARIO|DIALOG)\]\s*(.*?)(?=\n?\[(?:SCENARIO|DIALOG)\]|$)/gs;

const emptyCharForm = () => ({
  name: "",
  appearance: "",
  personality: "",
  speech_style: "",
  backstory: "",
});

const app = Vue.createApp({
  data() {
    return {
      MODES,
      mode: "character_chat",
      models: [],
      currentModel: "",
      modelWarning: "",
      characters: [],
      sessions: [],
      expandedChars: {},
      activeSessionId: null,
      activeSession: null,
      messages: [],
      input: "",
      streaming: false,
      streamText: "",
      thinkPhase: false,
      abortCtrl: null,
      stopped: false,
      error: "",
      sideCollapsed: false,
      panelCollapsed: false,
      charForm: emptyCharForm(),
      charModal: { visible: false, editingId: null, form: emptyCharForm() },
      newSessionModal: { visible: false, characterId: null, title: "" },
      renaming: false,
      renameText: "",
      editingId: null,
      editForm: {
        content: "",
        scenario: "",
        hasScenario: false,
        keepScenario: null,
        contentLabel: "消息内容",
        contentPlaceholder: "",
        contentHint: "",
      },
      deleteMenuId: null,
      lastFailedUser: null,
      confirmBox: { visible: false, text: "", resolve: null },
      showArchived: false,
      memoryData: { content: "", message_count: 0, updated_at: null, compress_failed: false },
      memoryText: "",
      genFields: [],
      genDefaults: {},
      genForm: {},
      tagDraft: {},
    };
  },
  computed: {
    isCharacterMode() {
      return MODES[this.mode].character;
    },
    genSectionTitle() {
      // 面板属于当前会话，标题按会话自身的模式取，避免切换 Tab 后标题不符
      const m = this.activeSession ? this.activeSession.mode : this.mode;
      return m === "character_chat" ? "输出倾向" : "生成要求";
    },
    freeSessions() {
      return this.sessions.filter((s) => s.mode === "free_scenario");
    },
    orphanSessions() {
      return this.sessions.filter((s) => s.mode !== "free_scenario" && !s.character_id);
    },
    orphanActive() {
      return (
        !!this.activeSession &&
        this.activeSession.mode !== "free_scenario" &&
        !this.activeSession.character
      );
    },
    memoryScope() {
      if (!this.activeSession) return null;
      if (this.activeSession.mode === "free_scenario") {
        return { type: "session", id: this.activeSession.id, label: "会话记忆" };
      }
      if (this.activeSession.character) {
        return {
          type: "character",
          id: this.activeSession.character.id,
          label: "角色记忆",
        };
      }
      return null;
    },
    archivedCount() {
      return this.messages.filter((m) => m.archived).length;
    },
    displayMessages() {
      return this.showArchived
        ? this.messages
        : this.messages.filter((m) => !m.archived);
    },
  },
  watch: {
    activeSessionId() {
      // 切换会话时右侧面板保持展开，只把内容刷新成新会话的
      this.showArchived = false;
      this.loadMemory();
      this.initGenForm();
    },
    activeSession(s) {
      if (s && s.character) {
        const c = s.character;
        this.charForm = {
          name: c.name,
          appearance: c.appearance,
          personality: c.personality,
          speech_style: c.speech_style,
          backstory: c.backstory,
        };
      } else {
        this.charForm = emptyCharForm();
      }
    },
    panelCollapsed(collapsed) {
      // 展开面板时重新拉一次记忆，避免收起期间的数据过期
      if (!collapsed) this.loadMemory();
    },
  },
  mounted() {
    this.init();
  },
  methods: {
    async api(path, opts = {}) {
      const resp = await fetch(path, opts);
      if (!resp.ok) {
        let msg = `请求失败（${resp.status}）`;
        try {
          const j = await resp.json();
          if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch (e) {}
        throw new Error(msg);
      }
      return resp.json();
    },

    jsonOpts(method, body) {
      return {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
    },

    ask(text) {
      return new Promise((resolve) => {
        this.confirmBox = { visible: true, text, resolve };
      });
    },

    answerConfirm(val) {
      this.confirmBox.visible = false;
      if (this.confirmBox.resolve) this.confirmBox.resolve(val);
    },

    // SSE 用 POST，EventSource 不支持，改用 fetch + ReadableStream 手动解析
    async ssePost(url, body, handlers, signal) {
      const opts = this.jsonOpts("POST", body);
      if (signal) opts.signal = signal;
      const resp = await fetch(url, opts);
      if (!resp.ok) {
        let msg = `请求失败（${resp.status}）`;
        try {
          const j = await resp.json();
          if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
        } catch (e) {}
        throw new Error(msg);
      }
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
      try {
        this.models = await this.api("/api/models");
      } catch (e) {
        ollamaOk = false;
        this.modelWarning = "无法连接 Ollama，请确认服务已启动";
      }
      try {
        const s = await this.api("/api/settings");
        this.currentModel = s.model;
      } catch (e) {
        this.error = e.message;
        return;
      }
      if (ollamaOk) {
        if (this.models.length === 0) {
          this.modelWarning = "Ollama 中还没有可用模型，请先拉取一个";
        } else if (
          this.currentModel &&
          !this.models.some((m) => m.name === this.currentModel)
        ) {
          this.modelWarning = `所选模型 ${this.currentModel} 未安装，请在右侧重新选择`;
        }
      }
      await this.refreshCharacters();
      await this.refreshSessions();
      try {
        const form = await this.api("/api/gen-settings");
        this.genFields = form.fields;
        this.genDefaults = form.defaults;
      } catch (e) {
        /* 表单定义拉取失败时生成要求区留空 */
      }
    },

    async refreshCharacters() {
      this.characters = await this.api("/api/characters");
    },

    async refreshSessions() {
      this.sessions = await this.api("/api/sessions");
    },

    switchMode(key) {
      this.mode = key;
    },

    fieldsOf(mode) {
      return this.genFields[mode] || [];
    },

    initGenForm() {
      const mode = this.activeSession ? this.activeSession.mode : this.mode;
      const merged = { ...(this.genDefaults[mode] || {}) };
      const stored = (this.activeSession && this.activeSession.gen_settings) || {};
      for (const k of Object.keys(stored)) {
        if (stored[k] !== null && stored[k] !== "") merged[k] = stored[k];
      }
      for (const f of this.fieldsOf(mode)) {
        if (f.type === "tags" && !Array.isArray(merged[f.key])) merged[f.key] = [];
        if (f.type === "radio" && !merged[f.key]) {
          merged[f.key] = (f.options && f.options[0] && f.options[0][0]) || "";
        }
      }
      this.genForm = merged;
    },

    toggleTag(key, tag) {
      const list = this.genForm[key] || [];
      const i = list.indexOf(tag);
      if (i >= 0) list.splice(i, 1);
      else list.push(tag);
      this.genForm[key] = [...list];
    },

    addTag(key) {
      const draft = (this.tagDraft[key] || "").trim();
      if (draft && !(this.genForm[key] || []).includes(draft)) {
        this.genForm[key] = [...(this.genForm[key] || []), draft];
      }
      this.tagDraft[key] = "";
    },

    removeTag(key, tag) {
      this.genForm[key] = (this.genForm[key] || []).filter((t) => t !== tag);
    },

    customTags(field) {
      return (this.genForm[field.key] || []).filter(
        (t) => !(field.presets || []).includes(t)
      );
    },

    async saveGenSettings() {
      const payload = {};
      for (const f of this.fieldsOf(this.activeSession.mode)) {
        payload[f.key] = this.genForm[f.key];
      }
      try {
        this.activeSession = await this.api(
          `/api/sessions/${this.activeSessionId}`,
          this.jsonOpts("PATCH", { gen_settings: payload })
        );
        this.initGenForm();
      } catch (e) {
        this.error = e.message;
      }
    },

    segmentsOf(m) {
      const segs = [];
      SEGMENT_RE.lastIndex = 0;
      let match;
      while ((match = SEGMENT_RE.exec(m.content)) !== null) {
        segs.push({
          type: match[1] === "SCENARIO" ? "scenario" : "dialog",
          text: match[2].trim(),
        });
      }
      return segs.length ? segs : [{ type: "dialog", text: m.content }];
    },

    toggleChar(id) {
      this.expandedChars[id] = !this.expandedChars[id];
    },

    sessionsOf(cid) {
      return this.sessions.filter((s) => s.character_id === cid);
    },

    async openSession(id) {
      if (this.streaming) {
        this.error = "正在生成中，请等待完成后再切换会话";
        return;
      }
      try {
        this.activeSession = await this.api(`/api/sessions/${id}`);
        this.activeSessionId = id;
        this.messages = await this.api(`/api/sessions/${id}/messages`);
        if (this.activeSession.character_id) {
          this.expandedChars[this.activeSession.character_id] = true;
        }
        this.error = "";
        this.scrollBottom();
      } catch (e) {
        this.error = e.message;
      }
    },

    async newSession() {
      if (this.mode === "free_scenario") {
        try {
          const s = await this.api(
            "/api/sessions",
            this.jsonOpts("POST", { mode: "free_scenario" })
          );
          await this.refreshSessions();
          await this.openSession(s.id);
        } catch (e) {
          this.error = e.message;
        }
        return;
      }
      if (this.characters.length === 0) {
        this.openCharacterModal();
        return;
      }
      this.newSessionModal = {
        visible: true,
        characterId: this.characters[0].id,
        title: "",
      };
    },

    async confirmNewSession() {
      try {
        const s = await this.api(
          "/api/sessions",
          this.jsonOpts("POST", {
            mode: this.mode,
            character_id: this.newSessionModal.characterId,
            title: this.newSessionModal.title,
          })
        );
        this.newSessionModal.visible = false;
        await this.refreshSessions();
        await this.openSession(s.id);
      } catch (e) {
        this.error = e.message;
      }
    },

    async createSessionForCharacter(cid) {
      try {
        const s = await this.api(
          "/api/sessions",
          this.jsonOpts("POST", { mode: this.mode, character_id: cid })
        );
        await this.refreshSessions();
        await this.openSession(s.id);
      } catch (e) {
        this.error = e.message;
      }
    },

    async removeSession(s) {
      if (this.streaming) {
        this.error = "正在生成中，请等待完成后再删除会话";
        return;
      }
      if (!(await this.ask(`删除会话「${s.title}」？其全部消息将一并删除。`))) return;
      try {
        await this.api(`/api/sessions/${s.id}`, { method: "DELETE" });
        if (this.activeSessionId === s.id) {
          this.activeSessionId = null;
          this.activeSession = null;
          this.messages = [];
        }
        await this.refreshSessions();
      } catch (e) {
        this.error = e.message;
      }
    },

    openCharacterModal(c = null) {
      if (c) {
        this.charModal = {
          visible: true,
          editingId: c.id,
          form: {
            name: c.name,
            appearance: c.appearance,
            personality: c.personality,
            speech_style: c.speech_style,
            backstory: c.backstory,
          },
        };
      } else {
        this.charModal = { visible: false, editingId: null, form: emptyCharForm() };
        this.charModal.visible = true;
      }
    },

    async saveCharacterModal() {
      const f = this.charModal.form;
      try {
        if (this.charModal.editingId) {
          await this.api(
            `/api/characters/${this.charModal.editingId}`,
            this.jsonOpts("PUT", f)
          );
        } else {
          const c = await this.api("/api/characters", this.jsonOpts("POST", f));
          this.expandedChars[c.id] = true;
        }
        this.charModal.visible = false;
        await this.afterCharacterChange();
      } catch (e) {
        this.error = e.message;
      }
    },

    async saveCharacterDrawer() {
      try {
        await this.api(
          `/api/characters/${this.activeSession.character.id}`,
          this.jsonOpts("PUT", this.charForm)
        );
        await this.afterCharacterChange();
      } catch (e) {
        this.error = e.message;
      }
    },

    async removeCharacter() {
      const c = this.activeSession.character;
      if (!(await this.ask(`删除角色「${c.name}」？其记忆将删除，已有会话保留但无法继续生成。`))) return;
      await this.deleteCharacter(c.id);
    },

    async removeCharacterFromModal() {
      const id = this.charModal.editingId;
      const c = this.characters.find((x) => x.id === id);
      if (!c) return;
      if (!(await this.ask(`删除角色「${c.name}」？其记忆将删除，已有会话保留但无法继续生成。`))) return;
      this.charModal.visible = false;
      await this.deleteCharacter(id);
    },

    async deleteCharacter(id) {
      try {
        await this.api(`/api/characters/${id}`, { method: "DELETE" });
        await this.afterCharacterChange();
      } catch (e) {
        this.error = e.message;
      }
    },

    async afterCharacterChange() {
      await this.refreshCharacters();
      await this.refreshSessions();
      if (this.activeSessionId) {
        this.activeSession = await this.api(`/api/sessions/${this.activeSessionId}`);
      }
    },

    startRename() {
      if (!this.activeSession || this.renaming) return;
      this.renameText = this.activeSession.title;
      this.renaming = true;
      this.$nextTick(() => {
        const el = document.querySelector(".title-input");
        if (el) el.focus();
      });
    },

    async saveRename() {
      if (!this.renaming) return;
      this.renaming = false;
      const title = this.renameText.trim();
      if (!title || title === this.activeSession.title) return;
      try {
        this.activeSession = await this.api(
          `/api/sessions/${this.activeSessionId}`,
          this.jsonOpts("PATCH", { title })
        );
        await this.refreshSessions();
      } catch (e) {
        this.error = e.message;
      }
    },

    async switchModel() {
      if (!this.currentModel) return;
      try {
        const s = await this.api(
          "/api/settings",
          this.jsonOpts("PUT", { model: this.currentModel })
        );
        this.currentModel = s.model;
        this.modelWarning = "";
      } catch (e) {
        // 顶栏直接提示并回退：底部错误条只在打开会话时才渲染，不能依赖它
        this.modelWarning = e.message;
        try {
          const s = await this.api("/api/settings");
          this.currentModel = s.model;
        } catch (_) {
          /* 读取失败就保持原选择 */
        }
      }
    },

    async loadMemory() {
      if (!this.memoryScope) return;
      const { type, id } = this.memoryScope;
      try {
        this.memoryData = await this.api(`/api/memories/${type}/${id}`);
        this.memoryText = this.memoryData.content;
      } catch (e) {
        /* scope 不存在等场景：面板留空 */
      }
    },

    async saveMemory() {
      const { type, id } = this.memoryScope;
      try {
        this.memoryData = await this.api(
          `/api/memories/${type}/${id}`,
          this.jsonOpts("PUT", { content: this.memoryText })
        );
        this.memoryText = this.memoryData.content;
      } catch (e) {
        this.error = e.message;
      }
    },

    async refreshMessages() {
      if (!this.activeSessionId || this.streaming) return;
      try {
        this.messages = await this.api(
          `/api/sessions/${this.activeSessionId}/messages`
        );
      } catch (e) {
        /* 会话已删等场景：静默 */
      }
    },

    scheduleMemoryRefresh() {
      // 压缩是后台任务，done 后延迟拉取一次归档状态与记忆
      const sid = this.activeSessionId;
      setTimeout(async () => {
        if (this.activeSessionId !== sid) return;
        await this.refreshMessages();
        if (this.memoryScope) await this.loadMemory();
      }, 12000);
    },

    beginStream() {
      this.stopped = false;
      this.abortCtrl = new AbortController();
      this.streaming = true;
      this.streamText = "";
      this.thinkPhase = false;
    },

    // 收尾流式状态；返回本次是否被用户主动停止
    endStream() {
      const stopped = this.stopped;
      this.streaming = false;
      this.streamText = "";
      this.thinkPhase = false;
      this.abortCtrl = null;
      this.stopped = false;
      this.scheduleMemoryRefresh();
      return stopped;
    },

    stop() {
      if (!this.streaming || !this.abortCtrl) return;
      this.stopped = true;
      this.abortCtrl.abort();
    },

    // 服务端在连接断开后才会把已生成的部分落库，轮询几次等它写进去
    async syncAfterStop() {
      const before = this.messages.length;
      for (let i = 0; i < 8; i++) {
        await new Promise((r) => setTimeout(r, 250));
        await this.refreshMessages();
        if (this.messages.length > before) return;
      }
    },

    async send() {
      const text = this.input.trim();
      if (!text || this.streaming || !this.activeSession || this.orphanActive) return;
      this.input = "";
      this.error = "";
      this.lastFailedUser = null;
      this.beginStream();
      this.messages.push({ id: "tmp-user", role: "user", content: text });
      this.scrollBottom();
      let userId = null;
      try {
        await this.ssePost(
          `/api/sessions/${this.activeSessionId}/chat`,
          { message: text },
          {
            meta: (d) => {
              userId = d.message_id;
              const m = this.messages.find((x) => x.id === "tmp-user");
              if (m) m.id = d.message_id;
            },
            status: (d) => {
              this.thinkPhase = d.phase === "thinking";
            },
            delta: (d) => {
              this.thinkPhase = false;
              this.streamText += d.text;
              this.scrollBottom();
            },
            done: (d) => {
              this.messages.push({
                id: d.message_id,
                role: "assistant",
                content: d.content,
                scenario: d.scenario,
              });
            },
            error: (d) => {
              this.error = d.message;
              if (userId) this.lastFailedUser = { id: userId, text };
            },
          },
          this.abortCtrl.signal
        );
      } catch (e) {
        // 用户点「停止」导致的中断不算错误：部分内容已由服务端落库
        if (!this.stopped) {
          this.error = `连接中断：${e.message}`;
          if (userId) this.lastFailedUser = { id: userId, text };
        }
      }
      if (this.endStream()) await this.syncAfterStop();
      await this.refreshSessions();
      this.scrollBottom();
    },

    async retryFailed() {
      const { id, text } = this.lastFailedUser;
      this.lastFailedUser = null;
      this.error = "";
      try {
        await this.api(`/api/messages/${id}`, { method: "DELETE" });
        this.messages = this.messages.filter((m) => m.id !== id);
      } catch (e) {
        this.error = e.message;
        return;
      }
      this.input = text;
      await this.send();
    },

    async copyText(m) {
      try {
        await navigator.clipboard.writeText(m.content);
      } catch (e) {
        this.error = "复制失败，请手动选择复制";
      }
    },

    startEdit(m) {
      this.deleteMenuId = null;
      this.editingId = m.id;
      const mode = this.activeSession.mode;
      const isMulti = m.scenario === "MULTI";
      // 角色情境模式：无论当前有没有情境都给出情境输入框，方便手动补上
      const hasScenario = mode === "character_scenario";
      this.editForm = {
        content: m.content,
        scenario: m.scenario && !isMulti ? m.scenario : "",
        hasScenario,
        keepScenario: isMulti ? "MULTI" : null,
        contentLabel: hasScenario ? "话语内容" : "消息内容",
        contentPlaceholder: hasScenario ? "这一幕里该角色说出的话" : "消息正文",
        contentHint: isMulti
          ? "自由情境的消息用 [SCENARIO] 标记情境说明、[DIALOG] 标记对话，保留这两个标记即可继续分段显示。"
          : "",
      };
      // 打开后按内容把输入框撑到实际高度，长消息不会被塞进一个小框里
      this.$nextTick(() => {
        document
          .querySelectorAll(".edit-box textarea")
          .forEach((el) => this.autoGrowEl(el));
      });
    },

    autoGrow(e) {
      this.autoGrowEl(e.target);
    },

    autoGrowEl(el) {
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight + 2, 460) + "px";
    },

    async saveEdit(m) {
      const payload = { content: this.editForm.content.trim() };
      if (this.editForm.hasScenario) {
        payload.scenario = this.editForm.scenario.trim() || null; // 清空即不再显示情境块
      } else {
        payload.scenario = this.editForm.keepScenario || null;
      }
      try {
        const updated = await this.api(
          `/api/messages/${m.id}`,
          this.jsonOpts("PUT", payload)
        );
        const idx = this.messages.findIndex((x) => x.id === m.id);
        this.messages.splice(idx, 1, updated);
        this.editingId = null;
        await this.refreshSessions();
      } catch (e) {
        this.error = e.message;
      }
    },

    async removeMessage(m, cascade) {
      this.deleteMenuId = null;
      const tip = cascade
        ? "将删除该消息及其之后的所有消息，继续？"
        : "确认删除这条消息？";
      if (!(await this.ask(tip))) return;
      try {
        await this.api(`/api/messages/${m.id}?cascade=${cascade}`, { method: "DELETE" });
        if (cascade) {
          const idx = this.messages.findIndex((x) => x.id === m.id);
          this.messages = this.messages.slice(0, idx);
        } else {
          this.messages = this.messages.filter((x) => x.id !== m.id);
        }
        await this.refreshSessions();
      } catch (e) {
        this.error = e.message;
      }
    },

    async regenerate(m) {
      if (this.streaming) {
        this.error = "正在生成中，请稍候";
        return;
      }
      if (!(await this.ask("重新生成将删除该消息及其之后的所有消息，继续？"))) return;
      this.deleteMenuId = null;
      this.error = "";
      this.lastFailedUser = null;
      const idx = this.messages.findIndex((x) => x.id === m.id);
      this.messages = this.messages.slice(0, idx);
      this.beginStream();
      this.scrollBottom();
      try {
        await this.ssePost(`/api/messages/${m.id}/regenerate`, {}, {
          status: (d) => {
            this.thinkPhase = d.phase === "thinking";
          },
          delta: (d) => {
            this.thinkPhase = false;
            this.streamText += d.text;
            this.scrollBottom();
          },
          done: (d) => {
            this.messages.push({
              id: d.message_id,
              role: "assistant",
              content: d.content,
              scenario: d.scenario,
            });
          },
          error: (d) => {
            this.error = d.message;
          },
        }, this.abortCtrl.signal);
      } catch (e) {
        if (!this.stopped) this.error = `连接中断：${e.message}`;
      }
      if (this.endStream()) await this.syncAfterStop();
      await this.refreshSessions();
      this.scrollBottom();
    },

    scrollBottom() {
      this.$nextTick(() => {
        const el = this.$refs.chatBox;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },
  },
});
app.mount("#app");
