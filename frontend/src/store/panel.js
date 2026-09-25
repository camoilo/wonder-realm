// 右侧面板：标签与脏标记、保存派发与还原、生成要求表单、记忆查看。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed } from "vue";
import { flashHint } from "../composables/hint.js";
import { revertTimers } from "./helpers.js";

Object.assign(store, {
  fixPanelTab() {
    const hasChar = !!(store.activeSession && store.activeSession.character);
    if (store.panelTab === "char" && !hasChar) store.panelTab = "gen";
    if (store.panelTab === "memory" && !store.memoryScope) store.panelTab = "gen";
  },
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
  revertSection(section) {
    store.disarmRevert(section);
    if (section === "gen") store.genForm = store.snapshot(store.genSaved);
    else if (section === "char") store.charForm = store.snapshot(store.charSaved);
    else if (section === "memory") store.memoryText = store.memorySaved;
    // 两个编辑弹窗：「还原」回到**打开弹窗时**那份（不碰数据库，等价于"回到上次保存的"）
    else if (section === "charModal" && store.charModal.saved) {
      store.charModal.form = store.snapshot(store.charModal.saved);
      store.avatarError = "";
    } else if (section === "presetModal" && store.presetModal.saved) {
      store.presetModal.form = store.snapshot(store.presetModal.saved);
      store.avatarError = "";
      store.presetModal.saveError = "";
    }
    // 世界设定 / 我的设定两页**只读**（内容来自选中的预设），没有可还原的东西
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
  saveCurrentTab() {
    // 世界设定 / 我的设定两页不在这里：它们只读，底部也没保存键（见 Panel.vue）
    if (store.panelTab === "char") return store.saveCharacterDrawer();
    if (store.panelTab === "memory") return store.saveMemory();
    return store.saveGenSettings();
  },
  // 右侧竖排图标栏：收起时点任意图标 → 展开并切过去；展开时点当前激活图标 → 收起；
  // 展开时点别的图标 → 只切换内容
  togglePanel(tab) {
    if (store.panelCollapsed) {
      store.panelTab = tab;
      store.panelCollapsed = false;
    } else if (store.panelTab === tab) {
      store.panelCollapsed = true;
    } else {
      store.panelTab = tab;
    }
  },
  // 手机断点下面板是底部弹层，图标栏横排在弹层顶部当标签用：点图标只切页，
  // 收起靠遮罩 / 下滑，不让它像桌面那样"点当前图标收起"把内容缩成 0 宽
  onRailClick(tab) {
    if (window.innerWidth <= 640) store.panelTab = tab;
    else store.togglePanel(tab);
  },
  // 手机端底部弹层的总开关：rail 在弹层内部、弹层没开时点不到，必须有弹层之外的入口。
  // 开关时顺手收起更多菜单，避免两个浮层叠着。没有会话时面板没有内容可开
  // （Panel 按 v-if="activeSession" 渲染），点了只会冒出个空遮罩，所以直接提示、不打开
  toggleMobilePanel() {
    if (!store.activeSession) {
      flashHint("请先选择或创建一个会话");
      return;
    }
    store.mobilePanelOpen = !store.mobilePanelOpen;
    store.mobileMoreOpen = false;
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
  scheduleMemoryRefresh() {
    // 压缩是后台任务，done 后延迟拉取一次归档状态与记忆
    const sid = store.activeSessionId;
    setTimeout(async () => {
      if (store.activeSessionId !== sid) return;
      await store.refreshMessages();
      if (store.memoryScope) await store.loadMemory();
    }, 12000);
  },
});

store.memoryScope = computed(() => {
      if (!store.activeSession) return null;
      if (store.activeSession.mode === "director") {
        return { type: "session", id: store.activeSession.id, label: "会话记忆" };
      }
      if (store.activeSession.character) {
        return {
          type: "character",
          id: store.activeSession.character.id,
          label: "角色记忆",
        };
      }
      return null;
});

store.genDirty = computed(() => {
      return !store.sameSnapshot(store.genForm, store.genSaved);
});

store.memoryDirty = computed(() => {
      return store.memoryText !== store.memorySaved;
});

store.activeTabDirty = computed(() => {
      // 世界设定 / 我的设定两页只读，永远不会"未保存"（保存键也不显示）
      if (store.panelTab === "char") return store.charDirty;
      if (store.panelTab === "memory") return store.memoryDirty;
      return store.genDirty;
});

// 顶栏那个「控制面板」键上的小黄点：面板里**任何一页**有未保存改动就亮。
// 手机端图标列在底部弹层里，收着的时候看不见，所以顶栏这个入口也得能提示（用户要求）
store.panelAnyDirty = computed(() => {
      return !!(store.genDirty || store.charDirty || store.memoryDirty);
});

store.saveDisabled = computed(() => {
      return store.panelTab === "char" && !store.charForm.name.trim();
});
