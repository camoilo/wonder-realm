import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// 构建产物直接落进后端的静态目录（app/static）：main.py 一行都不用改，
// run.py / start.bat 也不需要 Node——没装 Node 就用仓库里已提交的产物。
export default defineConfig({
  resolve: {
    alias: {
      // 模板现在还写在 index.html 里（DOM 内模板），必须用**带编译器的完整版**：
      // 默认的运行时版挂载后只渲染一个空注释节点、页面全白（实测过，见 DEVELOPMENT 10.47）。
      // 等模板拆进 .vue 单文件组件后由构建期预编译，就能改回运行时版、省下这 30KB 左右
      vue: "vue/dist/vue.esm-bundler.js",
    },
  },
  define: {
    // 本项目大量使用 Options API，且不需要 devtools：显式声明，免得 Vue 在控制台抱怨未定义
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
