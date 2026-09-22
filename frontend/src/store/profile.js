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
      // 选中的那条可能已被删掉（比如另开一个标签页删的），清掉选择
      if (store.presetPick && !store.profilePresets.some((p) => p.id === store.presetPick)) {
        store.presetPick = "";
      }
    } catch (e) {
      store.presetError = e.message;
    }
  },
  loadPreset() {
    // 只把预设内容填进表单：不落库、也不改"当前使用的设定"，
    // 真正生效要等用户按底部「保存当前配置」（选错了可以直接还原）
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
    // 「存为预设」= 用面板里当前的这份设定新建一条预设（不碰当前配置，也不改已有预设；
    // 要改已有预设走「编辑预设」那个弹窗）
    store.presetError = "";
    try {
      const p = await store.api(
        "/api/profile/presets",
        store.jsonOpts("POST", store.profileForm)
      );
      await store.loadPresets();
      store.presetPick = p.id; // 存完选中它，方便接着编辑或删除
    } catch (e) {
      store.presetError = e.message;
    }
  },
  openPresetModal() {
    const p = store.profilePresets.find((x) => x.id === store.presetPick);
    if (!p) return;
    store.avatarError = "";
    store.presetModal = {
      visible: true,
      id: p.id,
      form: {
        name: p.name || "",
        identity: p.identity || "",
        appearance: p.appearance || "",
        avatar: p.avatar || "",
      },
      saveError: "",
    };
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
      const saved = await store.api(
        `/api/profile/presets/${store.presetModal.id}`,
        store.jsonOpts("PUT", form)
      );
      await store.loadPresets();
      store.presetPick = saved.id;
      store.presetModal.visible = false;
    } catch (e) {
      store.presetModal.saveError = e.message;
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
});

store.profileDirty = computed(() => {
      return !store.sameSnapshot(store.profileForm, store.profile);
});

store.worldDirty = computed(() => {
      return !store.sameSnapshot(store.worldForm, store.world);
});

store.showUserSide = computed(() => {
      return !!store.activeChar && !!(store.profile.avatar || store.profile.name);
});
