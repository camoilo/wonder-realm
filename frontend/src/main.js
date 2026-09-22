// 前端入口（Vue 3 + Vite）。
//
// 样式仍然是**全局一份**：这个项目的 CSS 依赖源码顺序与跨上下文的优先级
// （见 DEVELOPMENT §9.2 单一数据源），拆成 scoped 会改变匹配范围、把那些修好的坑重新踩一遍，
// 所以这里一次性引入。
import { createApp } from "vue";

import "./style.css";
import App from "./App.vue";

createApp(App).mount("#app");
