<template>
<!-- 页面自己的工具条：会话名 / 搜索 / 模型 / 思考（浏览器里还有主题键）。
     壳里它上面还有一行窗口标题栏（TitleBar.vue，见 DEVELOPMENT 3.3） -->
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
        <!-- Ollama 刚被顺手拉起来 / 还没就绪时点一下就能自己恢复，不用重启应用：
             它会让后端再确保一次 Ollama（后端本来就在跑时，启动那条路径不会再走） -->
        <button v-if="modelWarning && !models.length" class="ghost-btn retry-btn"
                :disabled="ollamaBusy"
                v-hint="'再确保一次 Ollama 并重拉模型列表'"
                @click="loadModels(true)">{{ ollamaBusy ? "重试中…" : "重试" }}</button>
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
        <!-- 主题切换：跟随系统 → 浅色 → 深色 → 跟随系统 …。选择存本地，详见 store/ui.js 的 setTheme。
             **壳里它在标题栏那一行**（见上面），这里只给浏览器/手机留一份 -->
        <button v-if="!isDesktop" class="theme-toggle" :class="'theme-' + theme"
                v-hint="themeButtonTitle()" :aria-label="themeButtonTitle()"
                @click="cycleTheme">{{ themeIcon() }}</button>
      </div>
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
          <button class="ghost-btn mobile-theme" @click="cycleTheme">{{ themeIcon() }} {{ themeLabel() }}</button>
        </div>
      </div>
    </header>
</template>

<script setup>
import { toRefs } from "vue";
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
  ollamaBusy,
  orphanActive,
  renameText,
  renaming,
  searchIndex,
  searchQuery,
  searchTotal,
  sideCollapsed,
  theme,
  thinkToggleTitle,
  wco,
} = toRefs(store);

// 主题三态的图标 / 短名来自 store（窗口标题栏那一行也在用，见 TitleBar.vue）

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

// 模板用到的方法（函数不是响应式的，直接解构）。
// 「配置」面板的开合与"点外部就关"跟着窗口标题栏那一行走（TitleBar.vue），这里不再管。
const {
  clearSearch,
  cycleTheme,
  isNear,
  len,
  loadModels,
  saveRename,
  searchNext,
  searchPrev,
  startRename,
  switchModel,
  themeButtonTitle,
  themeIcon,
  themeLabel,
  toggleMobilePanel,
  toggleThinking,
} = store;
</script>
