// "我的设定"与"世界设定"：当前生效的那份 + 各自的预设库，以及"身份 / 世界跟着角色走"的校准。
//
// 两种预设是同一套东西（挑一条、看详情、立即生效；另存、覆盖、删除），差别只在字段与接口，
// 所以这里**一份实现按 kind 派发**（配置在 helpers.PRESET_KINDS），组件那边也共用同一对弹窗：
// 两边的行为永远一致，加一种预设只要动配置（见 DEVELOPMENT §2.3 / §2.4 / §7.1）。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { PRESET_KINDS } from "./helpers.js";
import { computed } from "vue";

// "当前生效的那份"存在哪两个字段里（行本身 + 面板表单）
const rowKey = (kind) => (kind === "world" ? "world" : "profile");
const formKey = (kind) => (kind === "world" ? "worldForm" : "profileForm");
const dirtyOf = (kind) => (kind === "world" ? store.worldDirty : store.profileDirty);
const kindOf = (kind) => PRESET_KINDS[kind];

Object.assign(store, {
  // ---- 词库（世界设定里的动态列表）：面板与预设弹窗共用，目标表单从外面传进来 ----
  addTerm(form) {
    if (form.terms.length >= store.limits.world_terms_max) return;
    form.terms.push({ term: "", meaning: "" });
  },
  removeTerm(form, index) {
    form.terms.splice(index, 1);
  },
  async saveProfile() {
    try {
      const p = await store.api("/api/profile", store.jsonOpts("PUT", store.profileForm));
      store.profile = p;
      store.profileForm = store.snapshot(p);
    } catch (e) {
      store.error = e.message;
    }
  },
  async saveWorld() {
    try {
      const w = await store.api("/api/world", store.jsonOpts("PUT", store.worldForm));
      store.world = w;
      store.worldForm = store.snapshot(w);
    } catch (e) {
      store.error = e.message;
    }
  },
  // ---- 预设列表（两种 kind 共用） ----
  async loadPresets(kind = "profile") {
    const k = kindOf(kind);
    try {
      store[k.listKey] = await store.api(k.presets);
      const ids = store[k.listKey].map((p) => p.id);
      // 选中的那条可能已经被删掉（比如另一个标签页删的）：把悬空的选择清掉
      if (store[k.currentKey] && !ids.includes(store[k.currentKey])) {
        store[k.currentKey] = "";
      }
      if (store.loadPresetModal.kind === kind && store.loadPresetModal.pick
          && !ids.includes(store.loadPresetModal.pick)) {
        store.loadPresetModal.pick = "";
      }
      if (store.presetModal.kind === kind && store.presetModal.id
          && !ids.includes(store.presetModal.id)) {
        store.presetModal.id = null;
      }
    } catch (e) {
      store.presetError = e.message;
    }
  },
  // 把"当前生效的那份"写成给定内容，并记住它来自哪条预设（空串 = 不是任何预设）。
  // 载入预设、改完正在用的那条预设、以及按角色校准，都走这同一条路。
  async writeCurrent(kind, values, presetId) {
    const k = kindOf(kind);
    const saved = await store.api(k.base, store.jsonOpts("PUT", values));
    store[rowKey(kind)] = saved;
    store[formKey(kind)] = store.snapshot(saved);
    store[k.currentKey] = presetId;
    return saved;
  },
  async applyPreset(kind, id) {
    const k = kindOf(kind);
    const p = store[k.listKey].find((x) => x.id === id);
    if (!p) return false;
    await store.writeCurrent(kind, k.values(p), p.id);
    return true;
  },
  // ---- 身份与世界跟着角色走（读法 A，见 DEVELOPMENT §2.3 / §2.4） ----
  //   绑了 P → 当前不是 P 就用 P 覆盖当前那份；已经是 P 则**什么都不做**
  //            （面板上临时手改过的内容在同角色内保留，不被反复冲掉）
  //   没绑   → 当前正用着某条预设就清空（"没绑就是不用预设"）；本来就没用预设则不动
  //   找不到那条预设（没加载出来 / 刚被删）→ 一律不动：宁可少切一次，也不能清错
  // 另外：**面板上有没保存的改动时一律不动** —— 那是用户正在编辑的内容。
  async syncBinding(kind, boundId) {
    const k = kindOf(kind);
    if (dirtyOf(kind)) return;
    const bound = boundId ? store[k.listKey].find((p) => p.id === boundId) : null;
    if (bound) {
      if (store[k.currentKey] === bound.id) return;
      await store.writeCurrent(kind, k.values(bound), bound.id);
    } else {
      if (!store[k.currentKey]) return;
      await store.writeCurrent(kind, k.empty(), "");
    }
  },
  async syncCharacterBindings() {
    try {
      const c = store.activeChar;
      if (c) {
        // 聊天与沉浸：身份与世界都跟着**角色**走
        await store.syncBinding("profile", c.profile_id);
        await store.syncBinding("world", c.world_id);
        return;
      }
      // 导演模式没有角色：世界挂在**会话**上，各会话一份（见 §2.4 世界设定）
      const s = store.activeSession;
      if (s && s.mode === "director") await store.syncBinding("world", s.world_id);
    } catch (e) {
      store.error = e.message;
    }
  },
  // 导演会话换世界：改会话的绑定，再把当前世界对齐过去。
  // 面板上有没保存的改动时不覆盖表单（syncBinding 里那条守卫），但绑定照改——
  // 用户的编辑留着，下次打开这个会话再校准。
  async setSessionWorld(worldId) {
    const s = store.activeSession;
    if (!s || s.mode !== "director") return;
    try {
      const saved = await store.api(
        `/api/sessions/${s.id}`,
        store.jsonOpts("PATCH", { world_id: worldId })
      );
      Object.assign(store.activeSession, saved);
      await store.syncBinding("world", saved.world_id);
    } catch (e) {
      store.error = e.message;
    }
  },
  // ---- 载入预设：弹窗里挑一条、看详情，确认后**立即生效** ----
  openLoadModal(kind) {
    const k = kindOf(kind);
    if (!store[k.listKey].length) return;
    store.avatarError = "";
    store.loadPresetModal = {
      visible: true,
      kind,
      // 默认选中"当前用的那条"；没有就选第一条，省一次点击
      pick: store[k.currentKey] || store[k.listKey][0].id,
    };
  },
  closeLoadModal() {
    store.loadPresetModal.visible = false;
  },
  pickLoadPreset(id) {
    store.loadPresetModal.pick = id;
  },
  async confirmLoadPreset() {
    const kind = store.loadPresetModal.kind;
    const k = kindOf(kind);
    const p = store[k.listKey].find((x) => x.id === store.loadPresetModal.pick);
    if (!p) return;
    // 载入会覆盖当前那份：面板里还有没保存的改动时先问一声（表单里的东西别白丢）
    if (dirtyOf(kind)
        && !(await store.ask(`面板里还有没保存的${k.label}改动，载入预设会用它覆盖，继续？`))) {
      return;
    }
    try {
      await store.applyPreset(kind, p.id);
      store.loadPresetModal.visible = false;
    } catch (e) {
      store.error = e.message;
    }
  },
  async savePreset(kind) {
    // 「存为预设」= 把面板里当前这份另存成一条新预设（不碰已有预设）
    const k = kindOf(kind);
    store.presetError = "";
    try {
      const p = await store.api(k.presets, store.jsonOpts("POST", store[formKey(kind)]));
      await store.loadPresets(kind);
      // 新建的这条内容就等于当前那份，所以直接认作"当前预设"
      store[k.currentKey] = p.id;
    } catch (e) {
      store.presetError = e.message;
    }
  },
  // ---- 编辑预设：弹窗里先选哪条，再改字段；删除也在这里 ----
  openPresetModal(kind) {
    const k = kindOf(kind);
    if (!store[k.listKey].length) return;
    store.avatarError = "";
    store.presetModal.visible = true;
    store.presetModal.kind = kind;
    store.editPickPreset(store.presetModal.id || store[k.currentKey] || store[k.listKey][0].id);
  },
  editPickPreset(id) {
    const k = kindOf(store.presetModal.kind);
    const p = store[k.listKey].find((x) => x.id === id);
    if (!p) return;
    store.avatarError = "";
    store.presetModal.id = p.id;
    store.presetModal.form = k.values(p); // 只取表单要的字段（列表项还带 characters 等）
    store.presetModal.saveError = "";
  },
  closePresetModal() {
    store.presetModal.visible = false;
    store.avatarError = "";
  },
  async savePresetModal() {
    // 只写这一条预设（PUT .../presets/{id}）：当前生效的那份不受影响
    const kind = store.presetModal.kind;
    const k = kindOf(kind);
    const form = store.presetModal.form;
    store.presetModal.saveError = "";
    if (!form.name.trim()) {
      store.presetModal.saveError = k.nameError;
      return;
    }
    try {
      await store.api(
        `${k.presets}/${store.presetModal.id}`,
        store.jsonOpts("PUT", form)
      );
      const edited = store.presetModal.id;
      await store.loadPresets(kind);
      // 改的正好是"当前生效的那份"的来源那条预设 → 当前那份跟着变，
      // 否则面板那行会挂着"（已修改）"，看起来像用户自己改坏了
      if (store[k.currentKey] === edited) await store.applyPreset(kind, edited);
      store.presetModal.visible = false;
    } catch (e) {
      store.presetModal.saveError = e.message;
    }
  },
  async deletePresetInModal() {
    const kind = store.presetModal.kind;
    const k = kindOf(kind);
    const p = store[k.listKey].find((x) => x.id === store.presetModal.id);
    if (!p) return;
    if (!(await store.ask(k.deleteText(p.name)))) return;
    store.presetModal.saveError = "";
    try {
      await store.api(`${k.presets}/${p.id}`, { method: "DELETE" });
      if (store[k.currentKey] === p.id) store[k.currentKey] = "";
      store.presetModal.id = null;
      await store.loadPresets(kind);
      // 还有别的预设就把编辑对象挪到第一条，没有就关掉弹窗
      if (store[k.listKey].length) store.editPickPreset(store[k.listKey][0].id);
      else store.presetModal.visible = false;
    } catch (e) {
      store.presetModal.saveError = e.message;
    }
  },
  // 弹窗里那一行"这条预设绑定了哪些角色"
  presetBindLabel(p) {
    const names = (p && p.characters ? p.characters : []).map((c) => c.name);
    return names.length ? names.join("、") : "未绑定";
  },
});

store.profileDirty = computed(() => {
      return !store.sameSnapshot(store.profileForm, store.profile);
});

store.worldDirty = computed(() => {
      return !store.sameSnapshot(store.worldForm, store.world);
});

// 面板上那一行"当前预设"：载入过预设就显示它的名字；如果之后手改过表单（当前那份已经
// 不等于那条预设了），加一个"（已修改）"——一眼就能看出当下的内容还是不是那条预设原样。
// 两种 kind 共用这一个函数，只是看的状态字段不同。
function currentLabel(kind) {
  const k = kindOf(kind);
  const p = store[k.listKey].find((x) => x.id === store[k.currentKey]);
  if (!p) return "未选择预设";
  const same = store.sameSnapshot(store[rowKey(kind)], k.values(p));
  return same ? p.name : `${p.name}（已修改）`;
}

store.currentPresetLabel = computed(() => currentLabel("profile"));
store.currentWorldPresetLabel = computed(() => currentLabel("world"));

store.showUserSide = computed(() => {
      return !!store.activeChar && !!(store.profile.avatar || store.profile.name);
});
