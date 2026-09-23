// 跨功能的小工具：计数、时间与名字、确认弹窗、全局点击/按键、输入框自增高。
//
// 只依赖 state.js（唯一的 reactive 对象），不 import 别的领域模块 —— 依赖是星形的，
// 所以不存在循环依赖；跨领域的调用都走 store.xxx（运行时才解析）。
import { store } from "./state.js";

Object.assign(store, {
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
    localStorage.setItem("ollama_agent_theme", mode);
    applyTheme(mode);
  },
  initTheme() {
    const saved = localStorage.getItem("ollama_agent_theme");
    const start = saved === "light" || saved === "dark" ? saved : "auto";
    store.theme = start;
    applyTheme(start);
  },
});

const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

function applyTheme(mode) {
  const dark = mode === "dark" || (mode === "auto" && prefersDark.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

// auto 模式下系统偏好变了就即时跟随，不用重新加载
prefersDark.addEventListener("change", () => {
  if (store.theme === "auto") applyTheme("auto");
});
