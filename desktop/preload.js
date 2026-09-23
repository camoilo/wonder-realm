// 桌面端（Electron）与网页之间的唯一接口（见 DEVELOPMENT §7.4）。
//
// 只暴露"壳才能做的事"：切换手机视图、取局域网地址、订阅手机视图状态。
// 页面本身照旧只跟本机后端说 HTTP（局域网开关就是 PUT /api/settings），
// 所以这里不需要、也不该暴露任何文件系统或 Node 能力。
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dshDesktop", {
  isDesktop: true,
  platform: process.platform,
  // 挂载前就要知道：上次退出时是不是手机视图（第一屏不闪桌面键）
  phoneView: ipcRenderer.sendSync("desktop:phone-view-state"),
  togglePhoneView: () => ipcRenderer.invoke("desktop:toggle-phone-view"),
  onPhoneView: (cb) => ipcRenderer.on("desktop:phone-view", (_e, on) => cb(on)),
  getLanUrl: () => ipcRenderer.invoke("desktop:lan-url"),
});
