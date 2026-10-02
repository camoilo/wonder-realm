// 跨功能的小工具：计数、时间与名字、确认弹窗、全局点击/按键、输入框自增高。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";
import { computed } from "vue";

Object.assign(store, {
  // 手机端三个浮层（抽屉 / 底部面板 / 更多菜单）共用一个遮罩：任一打开就显示，
  // 点遮罩全部关闭。桌面端这三个状态不会打开，所以遮罩在桌面从不出现。
  // 搜索条**不进遮罩**：它双端都用，是顶栏自己的浮条，点遮罩关它没意义（桌面更没有遮罩）。
  mobileMask: computed(() => store.mobileSideOpen || store.mobilePanelOpen || store.mobileMoreOpen),
  closeMobileLayers() {
    store.mobileSideOpen = false;
    store.mobilePanelOpen = false;
    store.mobileMoreOpen = false;
    store.searchOpen = false;
  },
  len(value) {
    return (value || "").length;
  },
  isNear(value, max) {
    return !!max && (value || "").length >= max * 0.9;
  },
  msgName(m) {
    if (!store.activeChar) return "";
    return m.role === "assistant" ? store.activeChar.name : store.profile.name || "";
  },
  timeOf(m) {
    const s = (m && m.created_at) || "";
    return s.length >= 19 ? s.slice(11, 19) : "";
  },
  fullTimeOf(m) {
    const s = (m && m.created_at) || "";
    return s ? s.replace("T", " ") : "";
  },
  onDocumentClick(e) {
    // 删除菜单与触发它的按钮都做了 stopPropagation，能走到这里就说明点的是别处
    store.deleteMenuId = null;
    // 搜索条"点别处就收"：它是一次性的浮条，选完就走
    const el = e && e.target;
    const inside = (sel) => !!(el && el.closest && el.closest(sel));
    if (store.searchOpen && !inside(".search-slot")) store.searchOpen = false;
    // 附加属性**不跟着点击收起来**：它是"随时瞄一眼"的状态面板，点输入框或按键就收会很别扭；
    // 改成"模型每生成完一条消息就自动展开"（见 chat.js 的 done 处理）
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
  // ---- 手机端顶栏的全屏键：交给浏览器的全屏 API（桌面端没有这个键）----
  // 状态不自己存：以 `document.fullscreenElement` 为准（按 Esc / 手势退出时也要跟着变），
  // 由 fullscreenchange 事件回写（见 api.js 的注册处）
  async toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch (e) {
      store.error = "这个浏览器不让全屏（iOS Safari 只支持「加到主屏幕」）";
    }
  },
  onFullscreenChange() {
    store.isFullscreen = !!document.fullscreenElement;
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
  async copyText(m) {
    try {
      await navigator.clipboard.writeText(m.content);
    } catch (e) {
      store.error = "复制失败，请手动选择复制";
    }
  },
  autoGrow(e) {
    store.autoGrowEl(e.target);
  },
  autoGrowEl(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight + 2, 460) + "px";
  },
  // 主题切换：light / dark / auto（跟随系统的亮暗偏好，选择存进 localStorage，
  // 下次启动仍有效；auto 下若系统偏好有变化，由下面 initTheme 的监听即时跟上）。
  setTheme(mode) {
    store.theme = mode;
    localStorage.setItem("wonder_realm_theme", mode);
    applyTheme(mode);
  },
  initTheme() {
    const saved = localStorage.getItem("wonder_realm_theme");
    const start = saved === "light" || saved === "dark" ? saved : "auto";
    store.theme = start;
    applyTheme(start);
  },
  // 主题按钮的三个状态与图标：壳里它在窗口标题栏那一行，浏览器里在顶栏，所以放在 store 里共用
  cycleTheme() {
    const next = store.theme === "auto" ? "light" : store.theme === "light" ? "dark" : "auto";
    store.setTheme(next);
  },
  themeIcon() {
    return THEME_UI[store.theme].icon;
  },
  themeButtonTitle() {
    return THEME_UI[store.theme].title;
  },
  themeLabel() {
    return THEME_UI[store.theme].label;   // 手机 ⋯ 菜单里那个短名
  },
});

// 主题三态：图标 / 悬停说明 / 手机 ⋯ 菜单里的短名
const THEME_UI = {
  auto:  { icon: "◐", title: "主题：跟随系统（点按切换）", label: "跟随系统" },
  light: { icon: "☀", title: "主题：浅色", label: "浅色" },
  dark:  { icon: "☾", title: "主题：深色", label: "深色" },
};

// matchMedia 只在浏览器存在：Node 纯逻辑测试（tests/test_*.mjs）import 时没有 window，
// 退回 null。applyTheme 只在浏览器里被调用（initTheme/setTheme 来自 App.vue），到那时总有
const prefersDark = typeof window !== "undefined"
  ? window.matchMedia("(prefers-color-scheme: dark)")
  : null;

function applyTheme(mode) {
  const dark = mode === "dark" || (mode === "auto" && !!prefersDark && prefersDark.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

// auto 模式下系统偏好变了就即时跟随，不用重新加载（Node 下没有 matchMedia，跳过）
if (prefersDark) {
  prefersDark.addEventListener("change", () => {
    if (store.theme === "auto") applyTheme("auto");
  });
}
