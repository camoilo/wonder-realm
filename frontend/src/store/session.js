// 模式与会话：切换模式、角色/会话列表、打开会话、重命名、删除。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed, nextTick } from "vue";
import { MODES } from "./helpers.js";

Object.assign(store, {
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
});

store.usesCharacter = computed(() => {
      return MODES[store.mode].character;
});

store.activeChar = computed(() => {
      return (store.activeSession && store.activeSession.character) || null;
});

store.isDirectorMode = computed(() => {
      return !!store.activeSession && store.activeSession.mode === "director";
});

store.directorSessions = computed(() => {
      return store.sessions.filter((s) => s.mode === "director");
});

store.orphanSessions = computed(() => {
      return store.sessions.filter((s) => s.mode !== "director" && !s.character_id);
});

store.orphanActive = computed(() => {
      return (
        !!store.activeSession &&
        store.activeSession.mode !== "director" &&
        !store.activeSession.character
      );
});
