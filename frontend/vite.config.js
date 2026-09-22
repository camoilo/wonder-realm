import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// 构建产物直接落进后端的静态目录（app/static）：main.py 一行都不用改，
// run.py / start.bat 也不需要 Node——没装 Node 就用仓库里已提交的产物。
export default defineConfig({
  plugins: [vue()],
  // 模板都在 .vue 单文件组件里，构建期就编译好了，所以**不需要**再 alias 到带编译器的
  // vue.esm-bundler：用默认的运行时版即可（省下约 30KB）。DOM 内模板时代那条 alias 见 10.47。
  define: {
    // 本项目大量使用 Options API 风格的选项对象（收在 store.js 里），且不需要 devtools
    __VUE_OPTIONS_API__: "true",
    __VUE_PROD_DEVTOOLS__: "false",
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: "false",
  },
  build: {
    outDir: fileURLToPath(new URL("../app/static", import.meta.url)),
    // 产物目录在 Vite 根之外，必须显式允许清空（每次构建都会重建它）
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // 开发时后端仍在 17800：/api 走代理，前端只跑 Vite（热更新）
    proxy: { "/api": "http://127.0.0.1:17800" },
  },
});
