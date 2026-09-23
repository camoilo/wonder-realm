// 我的设定与预设，以及全局的世界设定（含词库）。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed } from "vue";

Object.assign(store, {
  addTerm() {
    if (store.worldForm.terms.length >= store.limits.world_terms_max) return;
    store.worldForm.terms.push({ term: "", meaning: "" });
  },
  removeTerm(index) {
    store.worldForm.terms.splice(index, 1);
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
  async loadPresets() {
    try {
      store.profilePresets = await store.api("/api/profile/presets");
      const ids = store.profilePresets.map((p) => p.id);
      // 选中的那条可能已经被删掉（比如另一个标签页删的）：把悬空的选择清掉
      if (store.currentPresetId && !ids.includes(store.currentPresetId)) {
        store.currentPresetId = "";
      }
      if (store.loadPresetModal.pick && !ids.includes(store.loadPresetModal.pick)) {
        store.loadPresetModal.pick = "";
      }
      if (store.presetModal.id && !ids.includes(store.presetModal.id)) {
        store.presetModal.id = null;
      }
    } catch (e) {
      store.presetError = e.message;
    }
  },
  // ---- 载入预设：弹窗里挑一条、看详情，确认后**立即生效** ----
  openLoadModal() {
    if (!store.profilePresets.length) return;
    store.avatarError = "";
    store.loadPresetModal = {
      visible: true,
      // 默认选中"当前用的那条"；没有就选第一条，省一次点击
      pick: store.currentPresetId || store.profilePresets[0].id,
    };
  },
  closeLoadModal() {
    store.loadPresetModal.visible = false;
  },
  pickLoadPreset(id) {
    store.loadPresetModal.pick = id;
  },
  // 把某条预设写成"当前使用的设定"（立即生效）。载入预设、以及改完正在用的那条预设都走它
  async applyPreset(id) {
    const p = store.profilePresets.find((x) => x.id === id);
    if (!p) return false;
    const saved = await store.api(
      "/api/profile",
      store.jsonOpts("PUT", {
        name: p.name || "",
        identity: p.identity || "",
        appearance: p.appearance || "",
        avatar: p.avatar || "",
      })
    );
    store.profile = saved;
    store.profileForm = store.snapshot(saved);
    store.currentPresetId = p.id; // 面板那行据此显示"当前预设：…"
    return true;
  },
  async confirmLoadPreset() {
    const p = store.profilePresets.find((x) => x.id === store.loadPresetModal.pick);
    if (!p) return;
    // 载入会覆盖当前配置：面板里还有没保存的改动时先问一声（面板表单里的东西别白丢）
    if (store.profileDirty
        && !(await store.ask("面板里还有没保存的改动，载入预设会用它覆盖，继续？"))) {
      return;
    }
    try {
      await store.applyPreset(p.id);
      store.loadPresetModal.visible = false;
    } catch (e) {
      store.error = e.message;
    }
  },
  // ---- 身份跟着角色走：打开会话（或改了绑定）时把"当前使用的设定"对齐到角色 ----
  // 规则（见 DEVELOPMENT §2.3 我的设定）：
  //   角色绑了预设 P → 当前不是 P 就用 P 覆盖当前设定；已经就是 P 则**什么都不做**
  //                    （面板上临时手改过的内容在同角色内保留，不会被反复冲掉）
  //   角色没绑预设   → 当前正用着某条预设就清空（"没绑就是不用预设"），
  //                    本来就没用预设则不动（用户自己手填的身份留着）
  // 找不到那条预设（没加载出来/刚被删）时一律不动：宁可少切一次，也不能把身份清错
  async syncCharacterProfile() {
    const c = store.activeChar;
    if (!c) return; // 导演模式没有角色，此时本来也不注入"我的设定"
    const bound = c.profile_id
      ? store.profilePresets.find((p) => p.id === c.profile_id)
      : null;
    let values = null;
    if (bound) {
      if (store.currentPresetId === bound.id) return;
      values = {
        name: bound.name || "",
        identity: bound.identity || "",
        appearance: bound.appearance || "",
        avatar: bound.avatar || "",
      };
    } else {
      if (!store.currentPresetId) return;
      values = { name: "", identity: "", appearance: "", avatar: "" };
    }
    try {
      const saved = await store.api("/api/profile", store.jsonOpts("PUT", values));
      store.profile = saved;
      store.profileForm = store.snapshot(saved);
      store.currentPresetId = bound ? bound.id : "";
    } catch (e) {
      store.error = e.message;
    }
  },
  // 弹窗里那一行"这条预设绑定了哪些角色"
  presetBindLabel(p) {
    const names = (p && p.characters ? p.characters : []).map((c) => c.name);
    return names.length ? names.join("、") : "未绑定";
  },
  async savePreset() {
    // 「存为预设」= 用面板里当前的这份设定新建一条预设（不碰已有预设）
    store.presetError = "";
    try {
      const p = await store.api(
        "/api/profile/presets",
        store.jsonOpts("POST", store.profileForm)
      );
      await store.loadPresets();
      // 新建的这条内容就等于当前配置，所以直接认作"当前预设"
      store.currentPresetId = p.id;
    } catch (e) {
      store.presetError = e.message;
    }
  },
  // ---- 编辑预设：弹窗里先选哪条，再改字段；删除也在这里 ----
  openPresetModal() {
    if (!store.profilePresets.length) return;
    const id = store.presetModal.id
      || store.currentPresetId
      || store.profilePresets[0].id;
    store.avatarError = "";
    store.presetModal.visible = true;
    store.editPickPreset(id);
  },
  editPickPreset(id) {
    const p = store.profilePresets.find((x) => x.id === id);
    if (!p) return;
    store.avatarError = "";
    store.presetModal.id = p.id;
    store.presetModal.form = {
      name: p.name || "",
      identity: p.identity || "",
      appearance: p.appearance || "",
      avatar: p.avatar || "",
    };
    store.presetModal.saveError = "";
  },
  closePresetModal() {
    store.presetModal.visible = false;
    store.avatarError = "";
  },
  async savePresetModal() {
    // 只写这一条预设（PUT /api/profile/presets/{id}）：当前使用的设定不受影响
    const form = store.presetModal.form;
    store.presetModal.saveError = "";
    if (!form.name.trim()) {
      store.presetModal.saveError = "先给这条预设填个名字";
      return;
    }
    try {
      await store.api(
        `/api/profile/presets/${store.presetModal.id}`,
        store.jsonOpts("PUT", form)
      );
      const edited = store.presetModal.id;
      await store.loadPresets();
      // 改的正好是"当前使用的设定"的来源那条预设 → 当前设定跟着变，
      // 否则面板那行会挂着"（已修改）"，看起来像用户自己改坏了
      if (store.currentPresetId === edited) await store.applyPreset(edited);
      store.presetModal.visible = false;
    } catch (e) {
      store.presetModal.saveError = e.message;
    }
  },
  async deletePresetInModal() {
    const p = store.profilePresets.find((x) => x.id === store.presetModal.id);
    if (!p) return;
    if (!(await store.ask(`删除预设「${p.name}」？当前使用的设定不受影响。`))) return;
    store.presetModal.saveError = "";
    try {
      await store.api(`/api/profile/presets/${p.id}`, { method: "DELETE" });
      if (store.currentPresetId === p.id) store.currentPresetId = "";
      store.presetModal.id = null;
      await store.loadPresets();
      // 还有别的预设就把编辑对象挪到第一条，没有就关掉弹窗
      if (store.profilePresets.length) store.editPickPreset(store.profilePresets[0].id);
      else store.presetModal.visible = false;
    } catch (e) {
      store.presetModal.saveError = e.message;
    }
  },
});

store.profileDirty = computed(() => {
      return !store.sameSnapshot(store.profileForm, store.profile);
});

// 面板上那一行"当前预设"：载入过预设就显示它的名字；如果之后手改过表单（当前配置已经
// 不等于那条预设了），加一个"（已修改）"——一眼就能看出当下的配置还是不是那条预设原样
store.currentPreset = computed(() => {
      return store.profilePresets.find((p) => p.id === store.currentPresetId) || null;
});
store.currentPresetLabel = computed(() => {
      const p = store.currentPreset;
      if (!p) return "未选择预设";
      const same = store.sameSnapshot(store.profile, {
        name: p.name || "",
        identity: p.identity || "",
        appearance: p.appearance || "",
        avatar: p.avatar || "",
      });
      return same ? p.name : `${p.name}（已修改）`;
});

store.worldDirty = computed(() => {
      return !store.sameSnapshot(store.worldForm, store.world);
});

store.showUserSide = computed(() => {
      return !!store.activeChar && !!(store.profile.avatar || store.profile.name);
});
