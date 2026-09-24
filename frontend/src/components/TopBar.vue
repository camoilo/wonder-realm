<template>
<header class="topbar">
      <div class="title-area">
        <!-- 汉堡：桌面断点收起/展开左侧栏；手机断点打开抽屉（关闭走遮罩） -->
        <button class="icon-btn rail-toggle" v-hint="sideToggleHint()" :aria-label="sideToggleHint()"
                @click="toggleSide">&#9776;</button>
        <template v-if="activeSession">
          <span v-if="renaming" class="counted title-counted">
            <input v-model="renameText" class="title-input" :maxlength="limits.title"
                   @keydown.enter.prevent="saveRename" @blur="saveRename" />
            <span class="char-count inline" :class="{near: isNear(renameText, limits.title)}">{{ len(renameText) }}/{{ limits.title }}</span>
          </span>
          <h1 v-else class="title" v-hint="'点击重命名'" @click="startRename">{{ activeSession.title }}</h1>
          <span class="chip">{{ MODES[activeSession.mode].label }}</span>
          <span v-if="orphanActive" class="chip warn">角色已删除 · 仅可查看</span>
        </template>
        <h1 v-else class="title muted">未选择会话</h1>
      </div>
      <div class="toolbar">
        <span v-if="initError" class="chip warn">{{ initError }}</span>
        <span v-if="modelWarning" class="model-warning">{{ modelWarning }}</span>
        <!-- 会话内搜索：命中处标黄，↑/↓ 在命中之间跳转（Enter 下一个、Shift+Enter 上一个）。
             计数、清空键与两个跳转键**始终**占位（不按有无关键词显示/隐藏）——否则输入前后整个框
             会变宽变窄，看起来像换了个控件；没有关键词 / 没有命中时它们只是置灰 -->
        <div v-if="activeSession" class="search-box">
          <input v-model="searchQuery" type="text" class="search-input"
                 v-hint="'在当前会话里搜索：Enter 下一个、Shift+Enter 上一个、Esc 清空'"
                 placeholder="搜索当前会话"
                 @keydown.enter.exact.prevent="searchNext"
                 @keydown.shift.enter.prevent="searchPrev"
                 @keydown.esc="clearSearch">
          <button class="icon-btn" v-hint="'清空搜索（Esc）'" aria-label="清空搜索"
                  :disabled="!searchQuery" @click="clearSearch">&times;</button>
          <span class="search-count">{{ searchTotal ? searchIndex + 1 : 0 }}/{{ searchTotal }}</span>
          <button class="icon-btn" v-hint="'上一个（Shift+Enter）'" aria-label="上一个（Shift+Enter）" :disabled="!searchTotal" @click="searchPrev">↑</button>
          <button class="icon-btn" v-hint="'下一个（Enter）'" aria-label="下一个（Enter）" :disabled="!searchTotal" @click="searchNext">↓</button>
        </div>
        <select v-model="currentModel" class="model-select" :disabled="models.length === 0" @change="switchModel">
          <option value="" disabled>选择模型</option>
          <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}{{ m.thinking ? "（思考型）" : "" }}</option>
        </select>
        <button class="ghost-btn think-btn" :class="{off: disableThinking}"
                :disabled="!currentModelSupportsThinking"
                v-hint="thinkToggleTitle"
                @click="toggleThinking">{{ disableThinking ? "思考：关" : "思考：开" }}</button>
        <!-- 主题切换：跟随系统 → 浅色 → 深色 → 跟随系统 …。选择存本地，详见 store/ui.js 的 setTheme -->
        <button class="theme-toggle" :class="'theme-' + theme"
                v-hint="themeButtonTitle()" :aria-label="themeButtonTitle()"
                @click="cycleTheme">{{ themeIcon() }}</button>
        <!-- 桌面端（Electron 壳）专属：收纳成手机视图（配置键已搬到右侧图标列最低栏，见 Panel.vue）。
             网页端与手机浏览器没有 window.dshDesktop，这个键根本不渲染；手机视图下也隐藏
             （见 DEVELOPMENT §3.3） -->
        <button v-if="isDesktop && !desktopPhoneView" class="icon-btn desktop-btn"
                v-hint="'收纳成手机视图（再点恢复，F9）'" aria-label="收纳成手机视图" @click="togglePhoneView">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="2" width="12" height="20" rx="2.5"/><line x1="10.5" y1="18.5" x2="13.5" y2="18.5"/>
          </svg>
        </button>
        <!-- 没有会话时右侧图标列整块不存在（Panel.vue 以 activeSession 为条件），
             配置就没人能打开了 —— 所以这一屏把 ⚙ 留在顶栏当兜底 -->
        <button v-if="isDesktop && !desktopPhoneView && !activeSession" class="icon-btn desktop-btn"
                :class="{on: desktopConfigOpen}"
                v-hint="'配置（局域网推送、手机扫码、日志）'" aria-label="配置"
                :aria-expanded="desktopConfigOpen" @click="toggleDesktopConfig">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <circle cx="12" cy="12" r="3.4"/>
            <path d="M12 2.6v3M12 18.4v3M2.6 12h3M18.4 12h3M5.3 5.3l2.2 2.2M16.5 16.5l2.2 2.2M18.7 5.3l-2.2 2.2M7.5 16.5l-2.2 2.2"/>
          </svg>
        </button>
      </div>
      <ConfigPanel v-if="isDesktop && !desktopPhoneView && !activeSession && desktopConfigOpen" />
      <!-- 手机端三个入口：放大镜（折叠搜索条）+ 面板（右侧设置弹层）+ 更多（⋮，收纳模型/思考/主题）。
           桌面断点由 CSS 隐藏 -->
      <button class="icon-btn mobile-search-btn" aria-label="搜索当前会话" @click="toggleSearch">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
      </button>
      <button class="icon-btn mobile-panel-btn" :class="{on: mobilePanelOpen}"
              v-hint="'打开右侧面板'" aria-label="打开右侧面板"
              :aria-pressed="mobilePanelOpen" @click="toggleMobilePanel">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
      </button>
      <button class="icon-btn mobile-more-btn" aria-label="更多设置" @click="toggleMore">&#8942;</button>
      <!-- 折叠搜索条：点放大镜展开，占顶栏一整行 -->
      <div v-if="activeSession && mobileSearchOpen" class="mobile-search">
        <div class="search-box mobile-search-box">
          <input v-model="searchQuery" type="text" class="search-input"
                 placeholder="搜索当前会话"
                 @keydown.enter.exact.prevent="searchNext"
                 @keydown.shift.enter.prevent="searchPrev"
                 @keydown.esc="clearSearch">
          <button class="icon-btn" aria-label="清空搜索" :disabled="!searchQuery" @click="clearSearch">&times;</button>
          <span class="search-count">{{ searchTotal ? searchIndex + 1 : 0 }}/{{ searchTotal }}</span>
        </div>
      </div>
      <!-- 更多菜单：模型 / 思考开关 / 主题切换（手机断点替代顶栏右侧那一排） -->
      <div v-if="mobileMoreOpen" class="mobile-more">
        <div class="more-row">
          <span class="more-label">模型</span>
          <select v-model="currentModel" class="model-select mobile-model"
                  :disabled="models.length === 0" @change="switchModel">
            <option value="" disabled>选择模型</option>
            <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}{{ m.thinking ? "（思考型）" : "" }}</option>
          </select>
        </div>
        <div class="more-row">
          <span class="more-label">思考模式</span>
          <button class="ghost-btn mobile-think" :class="{off: disableThinking}"
                  :disabled="!currentModelSupportsThinking"
                  @click="toggleThinking">{{ disableThinking ? "思考：关" : "思考：开" }}</button>
        </div>
        <div class="more-row">
          <span class="more-label">主题</span>
          <button class="ghost-btn mobile-theme" @click="cycleTheme">{{ themeIcon() }} {{ THEME_UI[theme].label }}</button>
        </div>
      </div>
    </header>
</template>

<script setup>
import { onBeforeUnmount, onMounted, toRefs } from "vue";
import ConfigPanel from "./ConfigPanel.vue";
import { store, MODES } from "../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  currentModel,
  currentModelSupportsThinking,
  desktopConfigOpen,
  desktopPhoneView,
  disableThinking,
  initError,
  isDesktop,
  limits,
  mobileMoreOpen,
  mobilePanelOpen,
  mobileSearchOpen,
  modelWarning,
  models,
  orphanActive,
  renameText,
  renaming,
  searchIndex,
  searchQuery,
  searchTotal,
  sideCollapsed,
  theme,
  thinkToggleTitle,
} = toRefs(store);

// 主题按钮的三个可用 handle（图标 / 标题 / 短名随模式变）
const THEME_UI = {
  auto:    { icon: "◐", title: "主题：跟随系统（点按切换）", label: "跟随系统" },
  light:   { icon: "☀", title: "主题：浅色", label: "浅色" },
  dark:    { icon: "☾", title: "主题：深色", label: "深色" },
};
const themeIcon = () => THEME_UI[theme.value].icon;
const themeButtonTitle = () => THEME_UI[theme.value].title;

function cycleTheme() {
  const next = theme.value === "auto" ? "light" : theme.value === "light" ? "dark" : "auto";
  store.setTheme(next);
}

// 汉堡：桌面断点收起/展开左侧栏；手机断点打开抽屉（关闭走遮罩）
const sideToggleHint = () => window.innerWidth <= 640
  ? "打开左侧栏"
  : (store.sideCollapsed ? "展开左侧栏" : "收起左侧栏");
function toggleSide() {
  if (window.innerWidth <= 640) store.mobileSideOpen = !store.mobileSideOpen;
  else store.sideCollapsed = !store.sideCollapsed;
}
// 放大镜与更多互斥：展开一个时收起另一个，避免两个浮层叠着
function toggleSearch() {
  store.mobileSearchOpen = !store.mobileSearchOpen;
  store.mobileMoreOpen = false;
}
function toggleMore() {
  store.mobileMoreOpen = !store.mobileMoreOpen;
  store.mobileSearchOpen = false;
}

// 「配置」面板：点别处或按 Esc 关掉（与删除菜单、提示浮层同一套习惯）。
// 触发它的 ⚙ 现在在右侧图标列最低栏（Panel.vue），所以这里也要放过 .rail-config，
// 否则点它会被这个"点外部就关"先关掉、再被按钮自己打开，看着像没反应。
function onDocClick(e) {
  if (!store.desktopConfigOpen) return;
  if (e.target.closest && e.target.closest(".desktop-config, .desktop-btn, .rail-config")) return;
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

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  clearSearch,
  isNear,
  len,
  saveRename,
  searchNext,
  searchPrev,
  startRename,
  switchModel,
  toggleDesktopConfig,
  toggleMobilePanel,
  togglePhoneView,
  toggleThinking,
} = store;
</script>
