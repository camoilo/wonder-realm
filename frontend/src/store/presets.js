// "我的设定"与"世界设定"：预设库 + 绑定（角色 / 导演会话）+ "当前那份只读地跟着绑定走"。
//
// 从这一版起的模型（见 DEVELOPMENT §2.3 / §2.4）：
//   · 面板那两页**只读**：显示的就是绑定的那条预设的内容，页面里不提供任何编辑入口
//   · 要改内容 -> 「编辑预设…」弹窗（也能在里面新建；新建的必须命名才保存得下去）
//   · 要启用 / 换一份 -> 「绑定预设…」（写角色的 profile_id / world_id，导演会话写 sessions.world_id）
//   · **没绑定 = 不启用**：当前那份会被清空，提示词里也就不注入
//
// 两种预设仍是同一套实现（配置在 helpers.PRESET_KINDS），组件也共用同一对弹窗；
// 只依赖 state.js，不 import 别的领域模块 —— 跨领域调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { PRESET_KINDS } from "./helpers.js";
import { computed } from "vue";

// "当前生效的那份"存在哪两个字段里（行本身 + 面板表单）
const rowKey = (kind) => (kind === "world" ? "world" : "profile");
const formKey = (kind) => (kind === "world" ? "worldForm" : "profileForm");
const kindOf = (kind) => PRESET_KINDS[kind];

// 这个角色（或这个导演会话）绑的是哪条预设；null = 没绑定 = 不启用
function boundIdOf(kind) {
  if (kind === "profile") return (store.activeChar && store.activeChar.profile_id) || null;
  if (store.activeChar) return store.activeChar.world_id || null;
  const s = store.activeSession;
  return s && s.mode === "director" ? s.world_id || null : null;
}

// 换绑定要用 PUT /api/characters/{id}，而那个接口是"整体提交"（没带的字段会被写成空串），
// 所以这里把角色当前的公开字段原样带上，只改绑定那一项。锁定角色的隐藏字段后端会忽略，
// 不会被写坏；attr_defs 不带上（后端见到 UNSET 就不动）。
function characterPayload(extra) {
  const c = store.activeChar || {};
  return {
    name: c.name || "",
    appearance: c.appearance || "",
    personality: c.personality || "",
    speech_style: c.speech_style || "",
    backstory: c.backstory || "",
    avatar: c.avatar || "",
    ...extra,
  };
}

Object.assign(store, {
  // ---- 词库（世界设定里的动态列表）：预设弹窗用，目标表单从外面传进来 ----
  addTerm(form) {
    if (form.terms.length >= store.limits.world_terms_max) return;
    form.terms.push({ term: "", meaning: "" });
  },
  removeTerm(form, index) {
    form.terms.splice(index, 1);
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
      if (store.bindModal.kind === kind && store.bindModal.pick
          && !ids.includes(store.bindModal.pick)) {
        store.bindModal.pick = "";
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
  // 绑定与"改的正好是正在用的那条预设"都走这条同一条路。
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
  // ---- 绑定 / 解除绑定：面板那两页唯一的"启用"入口 ----
  // 绑了 P -> 写绑定的同时把当前那份对齐成 P（立即生效）
  // 传 null -> 解除绑定：当前那份清空（= 不启用），提示词里不再注入
  async bindPreset(kind, id) {
    const k = kindOf(kind);
    const p = id ? store[k.listKey].find((x) => x.id === id) : null;
    if (id && !p) return false;
    store.presetError = "";
    try {
      if (kind === "profile") {
        const c = store.activeChar;
        if (!c) return false;
        await store.api(`/api/characters/${c.id}`,
          store.jsonOpts("PUT", characterPayload({ profile_id: id })));
        await store.afterCharacterChange();   // 刷新后 syncCharacterBindings 会把当前那份对齐过去
      } else if (store.activeChar) {
        await store.api(`/api/characters/${store.activeChar.id}`,
          store.jsonOpts("PUT", characterPayload({ world_id: id })));
        await store.afterCharacterChange();
      } else {
        // 导演模式没有角色：世界挂在会话上
        await store.setSessionWorld(id);
      }
      return true;
    } catch (e) {
      store.presetError = e.message;
      store.error = e.message;
      return false;
    }
  },
  async unbindPreset(kind) {
    const k = kindOf(kind);
    if (!(await store.ask(`解除后不再注入${kind === "world" ? "世界设定" : "你的身份与外观"}，继续？`))) {
      return;
    }
    await store.bindPreset(kind, null);
  },
  // ---- 身份与世界跟着角色走（读法 A，见 DEVELOPMENT §2.3 / §2.4） ----
  //   绑了 P -> 当前不是 P 就用 P 覆盖当前那份；已经是 P 则**什么都不做**
  //   没绑   -> 当前那份只要还有内容就清空（"没绑就是不用预设"）。
  //             这里**不能只看 currentKey**：重启后它是空串，而数据库里可能还留着
  //             上一个角色绑定的内容 —— 那样新角色一开就"默认启用了"（用户报过）
  //   找不到那条预设（没加载出来 / 刚被删）→ 一律不动：宁可少切一次，也不能清错
  async syncBinding(kind, boundId) {
    const k = kindOf(kind);
    const bound = boundId ? store[k.listKey].find((p) => p.id === boundId) : null;
    if (bound) {
      if (store[k.currentKey] === bound.id) return;
      await store.writeCurrent(kind, k.values(bound), bound.id);
    } else {
      const cur = k.values(store[rowKey(kind)]);
      if (store.sameSnapshot(cur, k.empty())) return;   // 已经是空的，不用写
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
  // ---- 绑定预设：弹窗里挑一条、看详情，确认后绑定（原「载入预设」） ----
  openBindModal(kind) {
    const k = kindOf(kind);
    if (!store[k.listKey].length) return;
    store.avatarError = "";
    store.bindModal = {
      visible: true,
      kind,
      // 默认选中"当前绑的那条"；没绑就选第一条，省一次点击
      pick: boundIdOf(kind) || store[k.listKey][0].id,
    };
  },
  closeBindModal() {
    store.bindModal.visible = false;
  },
  pickBindPreset(id) {
    store.bindModal.pick = id;
  },
  async confirmBind() {
    const kind = store.bindModal.kind;
    const k = kindOf(kind);
    const p = store[k.listKey].find((x) => x.id === store.bindModal.pick);
    if (!p) return;
    await store.bindPreset(kind, p.id);
    if (!store.presetError) store.bindModal.visible = false;
  },
  // ---- 编辑预设：选一条来改、或者新建一条；删除也在这里 ----
  openPresetModal(kind) {
    const k = kindOf(kind);
    store.avatarError = "";
    store.presetError = "";
    store.presetModal.visible = true;
    store.presetModal.kind = kind;
    store.presetModal.saveError = "";
    // 一条预设都没有时也要能打开：新建预设的唯一入口就在这里
    const first = boundIdOf(kind) || store[k.currentKey] || (store[k.listKey][0] && store[k.listKey][0].id);
    if (first) store.editPickPreset(first);
    else store.startNewPreset(kind);
  },
  // 「添加预设」：先给一份空白表单（还没落库，id=null），必须命名后才保存得下去
  startNewPreset(kind = store.presetModal.kind) {
    const k = kindOf(kind);
    store.avatarError = "";
    store.presetModal.id = null;
    store.presetModal.form = k.empty();
    store.presetModal.saved = store.snapshot(store.presetModal.form);
    store.presetModal.saveError = "";
  },
  editPickPreset(id) {
    const k = kindOf(store.presetModal.kind);
    const p = store[k.listKey].find((x) => x.id === id);
    if (!p) return;
    store.avatarError = "";
    store.presetModal.id = p.id;
    store.presetModal.form = k.values(p); // 只取表单要的字段（列表项还带 characters 等）
    // 切换/打开时留一份快照：弹窗里的「未保存 / 还原」拿它比（见 presetModalDirty）
    store.presetModal.saved = store.snapshot(store.presetModal.form);
    store.presetModal.saveError = "";
  },
  closePresetModal() {
    store.presetModal.visible = false;
    store.avatarError = "";
  },
  async savePresetModal() {
    // id 有值 = 改这一条；id=null = 新建（POST）
    const kind = store.presetModal.kind;
    const k = kindOf(kind);
    const form = store.presetModal.form;
    store.presetModal.saveError = "";
    if (!form.name.trim()) {
      store.presetModal.saveError = k.nameError;   // 命名是硬门槛
      return;
    }
    try {
      const editing = store.presetModal.id;
      let saved;
      if (editing) {
        saved = await store.api(`${k.presets}/${editing}`, store.jsonOpts("PUT", form));
      } else {
        saved = await store.api(k.presets, store.jsonOpts("POST", form));
      }
      await store.loadPresets(kind);
      if (editing) {
        // 改的正好是"当前生效的那份"的来源那条预设 → 当前那份跟着变，
        // 否则面板那行会挂着旧内容，看起来像没保存成功
        if (store[k.currentKey] === editing) await store.applyPreset(kind, editing);
        store.presetModal.visible = false;
      } else {
        // 新建的留在弹窗里继续编辑（刚建出来通常是空白的），但不自动绑定：
        // "启用"要用户自己走一次「绑定预设…」（用户要求）
        store.editPickPreset(saved.id);
      }
    } catch (e) {
      store.presetModal.saveError = e.message;
    }
  },
  async deletePresetInModal() {
    const kind = store.presetModal.kind;
    const k = kindOf(kind);
    const p = store[k.listKey].find((x) => x.id === store.presetModal.id);
    if (!p) return;   // 还没落库的新预设：没得删
    if (!(await store.ask(k.deleteText(p.name)))) return;
    store.presetModal.saveError = "";
    try {
      await store.api(`${k.presets}/${p.id}`, { method: "DELETE" });
      if (store[k.currentKey] === p.id) store[k.currentKey] = "";
      store.presetModal.id = null;
      await store.loadPresets(kind);
      // 删掉的也许正是当前角色绑的那条：后端已经把绑定置空，这里把当前那份同步清掉
      await store.syncCharacterBindings();
      // 还有别的预设就把编辑对象挪到第一条，没有就切到"新建"状态
      if (store[k.listKey].length) store.editPickPreset(store[k.listKey][0].id);
      else store.startNewPreset(kind);
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

// 预设编辑弹窗里"有没有改动"：当前表单 vs 打开/切到这条时的快照（新建的空白快照也算）
store.presetModalDirty = computed(() => {
      if (!store.presetModal.visible || !store.presetModal.saved) return false;
      return !store.sameSnapshot(store.presetModal.form, store.presetModal.saved);
});

store.worldDirty = computed(() => {
      return !store.sameSnapshot(store.worldForm, store.world);
});

// 当前绑的是哪条（面板两页据此显示名字与"未绑定"）：
//   我的设定 -> 角色的 profile_id；世界 -> 角色的 world_id，导演模式则看会话的 world_id
store.boundProfileId = computed(() => boundIdOf("profile"));
store.boundWorldId = computed(() => boundIdOf("world"));

function boundLabel(kind) {
  const k = kindOf(kind);
  const id = boundIdOf(kind);
  if (!id) return "未选择";
  const p = store[k.listKey].find((x) => x.id === id);
  // 列表还没加载出来时别显示"未选择"，那会让人以为选择丢了
  return p ? p.name : "（载入中…）";
}

store.currentPresetLabel = computed(() => boundLabel("profile"));
store.currentWorldPresetLabel = computed(() => boundLabel("world"));

store.showUserSide = computed(() => {
      return !!store.activeChar && !!(store.profile.avatar || store.profile.name);
});
