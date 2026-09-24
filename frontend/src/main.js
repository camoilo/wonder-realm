// 前端入口（Vue 3 + Vite）。
//
// 样式仍然是**全局一份**：这个项目的 CSS 依赖源码顺序与跨上下文的优先级
// （见 DEVELOPMENT §9.2 单一数据源），拆成 scoped 会改变匹配范围、把那些修好的坑重新踩一遍，
// 所以这里一次性引入。
import { createApp } from "vue";

import "./style.css";
import App from "./App.vue";
import { hintDirective } from "./composables/hint.js";
import { initDesktop, store } from "./store.js";

// 主题：挂载前先按"本地选择 / 系统偏好"定下 data-theme，避免一开始闪成默认浅色
store.initTheme();

// 桌面端（Electron 壳）：挂载前认一下壳的标记，第一屏就不会先闪出桌面专属键（§3.3）
initDesktop();

// 悬停提示统一走 v-hint（不用原生 title，理由见 composables/hint.js）。
// 指令全局注册，模板里直接写 v-hint="'文案'"，不必逐个组件 import。
createApp(App).directive("hint", hintDirective).mount("#app");
