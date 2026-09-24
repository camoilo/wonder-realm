// 桌面端（Electron 壳，见 DEVELOPMENT §3.3）。
//
// 壳在 preload 里注入 `window.dshDesktop`（开窗口、缩放手机视图、算局域网地址都是壳的事）；
// 网页端与手机浏览器没有这个对象，于是"配置 / 手机视图"两个键、以及复制局域网地址的能力
// 自然不会出现——**同一份前端代码，桌面端只是多了一层壳**。
import { watch } from "vue";
import { store } from "./state.js";

export function initDesktop() {
  const api = window.dshDesktop;
  if (!api) return false;
  store.isDesktop = true;
  // 自绘标题栏：顶栏要变成拖拽区、给右上角那三个系统按钮留宽度（见 DEVELOPMENT 3.3）
  store.wco = !!api.titleBar;
  if (store.wco && typeof api.setTitleBarTheme === "function") {
    // 那三个按钮是**壳**画的，主题一变要告诉它，否则深色页面会顶着一条浅色标题栏
    const push = () => api.setTitleBarTheme(store.theme === "dark");
    watch(() => store.theme, push);
    push();
  }
  // 壳记住了上次是不是手机视图：挂载前就定下来，第一屏不会先闪一下桌面键
  store.desktopPhoneView = !!api.phoneView;
  if (typeof api.onPhoneView === "function") {
    api.onPhoneView((on) => {
      store.desktopPhoneView = !!on;
      if (store.desktopPhoneView) store.desktopConfigOpen = false;
    });
  }
  return true;
}

Object.assign(store, {
  // ---- 手机视图：交给壳去缩窗口（页面只负责隐藏桌面专属键） ----
  togglePhoneView() {
    if (window.dshDesktop && window.dshDesktop.togglePhoneView) {
      window.dshDesktop.togglePhoneView();
    }
  },
  // ---- 配置面板（桌面端才有这个入口） ----
  async toggleDesktopConfig() {
    store.desktopConfigOpen = !store.desktopConfigOpen;
    if (store.desktopConfigOpen) await store.refreshLanUrl();
  },
  closeDesktopConfig() {
    store.desktopConfigOpen = false;
  },
  async refreshLanUrl() {
    try {
      store.lanUrl = (window.dshDesktop && window.dshDesktop.getLanUrl
        ? await window.dshDesktop.getLanUrl()
        : "") || "";
    } catch (e) {
      store.lanUrl = "";
    }
  },
  // 推送局域网：写后端设置（只有本机能改，壳里跑的这份一定来自本机）
  async toggleLan() {
    if (store.lanBusy) return;
    store.lanBusy = true;
    try {
      const s = await store.api(
        "/api/settings",
        store.jsonOpts("PUT", { lan_enabled: !store.lanEnabled })
      );
      store.lanEnabled = !!s.lan_enabled;
    } catch (e) {
      store.error = e.message;
    } finally {
      store.lanBusy = false;
    }
  },
  async copyLanUrl() {
    if (!store.lanUrl) await store.refreshLanUrl();
    if (!store.lanUrl) return;
    try {
      await navigator.clipboard.writeText(store.lanUrl);
      store.lanCopied = true;
      setTimeout(() => { store.lanCopied = false; }, 1500);
    } catch (e) {
      store.error = `复制失败：${e.message}`;
    }
  },
  // ---- 防火墙放行命令：只复制，不代跑（加规则要管理员权限，壳不该偷偷提权） ----
  firewallCmd() {
    const port = window.location.port || "17800";
    return "netsh advfirewall firewall add rule "
      + `name="OllamaAgent 局域网访问 ${port}" dir=in action=allow protocol=TCP localport=${port}`;
  },
  async copyFirewallCmd() {
    try {
      await navigator.clipboard.writeText(store.firewallCmd());
      store.firewallCopied = true;
      setTimeout(() => { store.firewallCopied = false; }, 1500);
    } catch (e) {
      store.error = `复制失败：${e.message}`;
    }
  },
  // ---- 壳日志：只有壳能打开（网页端没有这个按钮） ----
  async openLog() {
    if (!window.dshDesktop || !window.dshDesktop.openLog) return;
    try {
      const ok = await window.dshDesktop.openLog();
      if (!ok) store.error = "还没有日志文件（壳正常启动过一次就会有）";
    } catch (e) {
      store.error = `打开日志失败：${e.message}`;
    }
  },
});
