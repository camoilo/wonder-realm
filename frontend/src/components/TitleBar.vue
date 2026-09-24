<template>
  <!-- 壳里的**窗口标题栏**：横向铺满整个窗口（在左栏与内容之上），左边图标 + 应用名，
       右边主题 / 配置 / 手机视图，再往右是系统画的最小化、最大化、关闭（自绘标题栏，
       见 DEVELOPMENT 3.3）。整行是拖拽区，里面的控件逐个排除。
       浏览器与手机没有 window.dshDesktop —— 这一整行不渲染，品牌区由左栏自己显示。 -->
  <div v-if="isDesktop" class="titlebar" :class="{wco}">
    <span class="brand-mark">&#9671;</span>
    <span class="titlebar-name">Wonder Realm（奇想界域）</span>
    <span class="titlebar-gap"></span>
    <button v-if="!desktopPhoneView" class="win-btn" :class="'theme-' + theme"
            v-hint="themeButtonTitle()" :aria-label="themeButtonTitle()"
            @click="cycleTheme">{{ themeIcon() }}</button>
    <button v-if="!desktopPhoneView" class="win-btn" :class="{on: desktopConfigOpen}"
            v-hint="'配置（局域网推送、手机扫码、日志）'" aria-label="配置"
            :aria-expanded="desktopConfigOpen" @click="toggleDesktopConfig">
      <!-- 齿轮（Lucide settings 那套线稿：带齿外圈 + 中心圆），比原来那个"太阳"更像齿轮 -->
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
        <circle cx="12" cy="12" r="3"/>
      </svg>
    </button>
    <!-- 手机视图这个键**在手机视图下也留着**：不然进去就没有看得见的出路（菜单栏是 autoHideMenuBar） -->
    <button class="win-btn" :class="{on: desktopPhoneView}"
            v-hint="desktopPhoneView ? '退出手机视图（F9）' : '收纳成手机视图（F9）'"
            :aria-label="desktopPhoneView ? '退出手机视图' : '收纳成手机视图'"
            :aria-pressed="desktopPhoneView" @click="togglePhoneView">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
           stroke-linecap="round" stroke-linejoin="round">
        <rect x="6" y="2" width="12" height="20" rx="2.5"/><line x1="10.5" y1="18.5" x2="13.5" y2="18.5"/>
      </svg>
    </button>
    <ConfigPanel v-if="!desktopPhoneView && desktopConfigOpen" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, toRefs } from "vue";
import ConfigPanel from "./ConfigPanel.vue";
import { store } from "../store.js";

const {
  desktopConfigOpen,
  desktopPhoneView,
  isDesktop,
  theme,
  wco,
} = toRefs(store);

const {
  cycleTheme,
  themeButtonTitle,
  themeIcon,
  toggleDesktopConfig,
  togglePhoneView,
} = store;

// 「配置」面板：点别处或按 Esc 关掉（与删除菜单、提示浮层同一套习惯）。
// 触发它的 ⚙ 就在这一行里，要放过 .win-btn，否则点它会被"点外部就关"先关掉、
// 再被按钮自己打开，看着像没反应。
function onDocClick(e) {
  if (!store.desktopConfigOpen) return;
  if (e.target.closest && e.target.closest(".desktop-config, .win-btn")) return;
  store.closeDesktopConfig();
}
function onDocKeydown(e) {
  if (e.key === "Escape") store.closeDesktopConfig();
}
onMounted(() => {
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onDocKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onDocKeydown);
});
</script>
