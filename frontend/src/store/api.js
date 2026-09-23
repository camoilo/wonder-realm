// 与后端打交道：请求封装、SSE、初始化，以及模型与思考开关。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed, watch } from "vue";
import { emptyCharForm } from "./helpers.js";

Object.assign(store, {
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
    // 有哪几步没加载上。各步独立容错：一步失败只影响它自己，界面照常出来
    // （以前 /api/settings 失败会直接 return，于是顶栏空、模型列表和角色列表都不拉）
    const failed = [];
    // 字数上限以后端为准；拿不到就沿用 data 里的兜底值，不影响使用
    try {
      store.limits = await store.api("/api/limits");
    } catch (e) {
      /* 用兜底值 */
    }
    // "我的设定"是每个主体一份：当前那份 + 预设库，都只在启动时取一次
    try {
      const p = await store.api("/api/profile");
      store.profile = p;
      store.profileForm = store.snapshot(p);
      await store.loadPresets("profile");
    } catch (e) {
      /* 拿不到就用空值，面板里照样能填 */
    }
    // "世界设定"同一套：当前世界 + 世界预设库
    try {
      const w = await store.api("/api/world");
      store.world = w;
      store.worldForm = store.snapshot(w);
      await store.loadPresets("world");
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
      // 局域网开关也在这份设置里（见 §8.3）：桌面端的「配置」面板据此显示当前状态
      store.lanEnabled = !!s.lan_enabled;
    } catch (e) {
      // 设置读不到（例如库文件被删）不该带走整个初始化：下面的角色/会话照常拉
      failed.push({ label: "设置", msg: e.message });
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
    // 角色/会话/生成表单也各自容错：任何一个失败都不再让 init 抛出去
    // （initApp 没有 await 它，抛出来只会变成静默的 unhandledrejection）
    try {
      await store.refreshCharacters();
    } catch (e) {
      failed.push({ label: "角色列表", msg: e.message });
    }
    try {
      await store.refreshSessions();
    } catch (e) {
      failed.push({ label: "会话列表", msg: e.message });
    }
    try {
      const form = await store.api("/api/gen-settings");
      store.genFields = form.fields;
      store.genDefaults = form.defaults;
    } catch (e) {
      failed.push({ label: "生成表单", msg: e.message });
    }
    if (failed.length) {
      // 顶栏的常驻提示只放短句，完整原因（含后端原话）给底部错误条
      store.initError = `初始化未完成：${failed.map((f) => f.label).join("、")}没加载上`;
      store.error = `${store.initError}（${failed.map((f) => `${f.label}：${f.msg}`).join("；")}）`;
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
});

store.currentModelInfo = computed(() => {
      return store.models.find((m) => m.name === store.currentModel) || null;
});

store.currentModelSupportsThinking = computed(() => {
      if (!store.currentModel) return false; // 还没选模型：开关没有对象，置灰
      const info = store.currentModelInfo;
      return info ? !!info.thinking : true; // 模型列表还没到手时不置灰，免得闪一下
});

store.thinkToggleTitle = computed(() => {
      if (!store.currentModel) return "还没有选择模型，先在左边选一个";
      if (!store.currentModelSupportsThinking) return "当前模型不支持思考模式，这个开关对它没有作用";
      return store.disableThinking
        ? "思考模式已关闭，点击开启"
        : "思考模式已开启，点击关闭（能明显加快回复）";
});

const watchDefs = {
    activeSessionId() {
      // 切换会话时右侧面板保持展开，只把内容刷新成新会话的
      store.showArchived = false;
      store.loadMemory();
      store.initGenForm();
    },
    activeSession(s) {
      if (s && s.character) {
        const c = s.character;
        store.charForm = {
          name: c.name,
          appearance: c.appearance,
          // 锁定的角色拿不到这三项（接口就不下发），留空即可：保存时后端也会忽略它们
          personality: c.personality || "",
          speech_style: c.speech_style || "",
          backstory: c.backstory || "",
          // 必须带上：面板是整体提交的，漏了它就会在保存角色设定时把头像一个不剩地清掉
          avatar: c.avatar || "",
          // 附加属性定义同理：漏了它保存一次角色设定就把定义清空了（见 DEVELOPMENT §2.6）
          attr_defs: (c.attr_defs || []).map((d) => ({ ...d })),
          // 背景图不随角色下发，由 loadBackgrounds() 填充
          backgrounds: [],
        };
        store.charLocked = !!c.locked;
      } else {
        store.charForm = emptyCharForm();
        store.charLocked = false;
      }
      store.charSaved = store.snapshot(store.charForm); // 重新载入即视为已保存
      store.fixPanelTab();
    },
    "charModal.gen.mode"() {
      if (store.charModal.gen.draftId) store.resetGeneratedDraft();
    },
    panelCollapsed(collapsed) {      // 展开面板时重新拉一次记忆，避免收起期间的数据过期；
      // 但用户手上有未保存的编辑时不能覆盖掉
      if (!collapsed && !store.memoryDirty) store.loadMemory();
    },
    genDirty(v) {
      if (!v) store.disarmRevert("gen");
    },
    charDirty(v) {
      if (!v) store.disarmRevert("char");
    },
    profileDirty(v) {
      if (!v) store.disarmRevert("profile");
    },
    searchQuery() {
      store.searchIndex = 0;
      store.scrollToHit();
    },
    searchTotal(v) {
      if (store.searchIndex >= v) store.searchIndex = 0;
    },
    memoryDirty(v) {
      if (!v) store.disarmRevert("memory");
    },
};

export { watchDefs };

// App.vue 在 setup 里调一次：键支持点号路径（如 charModal.gen.mode），取值方式与 Vue 的 watch 一致
export function registerWatchers() {
  for (const [path, handler] of Object.entries(watchDefs)) {
    const get = () => path.split(".").reduce((o, k) => (o == null ? o : o[k]), store);
    watch(get, handler);
  }
}

// 生命周期（原 mounted / beforeUnmount）
export async function initApp() {
    // init 内部每步都已各自容错，这里再兜一层：万一还有漏网的异常，也让它显示出来，
    // 而不是静默变成 unhandledrejection（这正是 chatBoxEl 那次的表现形式）
    store.init().catch((e) => {
      store.error = e.message;
      store.initError = `初始化失败：${e.message}`;
    });
    // 点空白处 / 按 Esc 关掉消息删除菜单与编辑弹窗，避免它们只能靠再次点按钮关闭
    document.addEventListener("click", store.onDocumentClick);
    document.addEventListener("keydown", store.onDocumentKeydown);
}

export function disposeApp() {
    document.removeEventListener("click", store.onDocumentClick);
    document.removeEventListener("keydown", store.onDocumentKeydown);
}
