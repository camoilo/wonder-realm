<template>
<!-- 页面自己的工具条：会话名 / 搜索 / 附加属性 / 模型 / 思考（浏览器里还有主题键）。
     壳里它上面还有一行窗口标题栏（TitleBar.vue，见 DEVELOPMENT 3.3） -->
<header class="topbar">
      <div class="title-area">
        <!-- 汉堡：桌面断点收起/展开左侧栏；手机断点打开抽屉（关闭走遮罩） -->
        <button class="icon-btn rail-toggle" v-hint="sideToggleHint()" :aria-label="sideToggleHint()"
                @click="toggleSide">&#9776;</button>
        <template v-if="activeSession">
          <span v-if="renaming" class="counted title-counted">
            <input v-model="renameText" class="title-input" :maxlength="limits.title"
                   :style="{ width: titleInputWidth }"
                   @keydown.enter.prevent="saveRename" @blur="saveRename" />
            <span class="char-count inline" :class="{near: isNear(renameText, limits.title)}">{{ len(renameText) }}/{{ limits.title }}</span>
          </span>
          <h1 v-else class="title" v-hint="'点击重命名'" @click="startRename">{{ activeSession.title }}</h1>
          <!-- 当前模式不在这里标：左栏那排模式 Tab 上已经高亮着 -->
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
        <!-- 会话内搜索：顶栏只留一个放大镜（**双端一致**，桌面端也不再常驻一个输入框），
             点它才弹出搜索条；再点一次或 Esc 收起。
             键与条同在一个定位槽里：桌面端搜索条挂在键正下方、只有 300px 宽（整行铺开会把
             右侧那排图标盖住），手机端由 CSS 换成整条 -->
        <span v-if="activeSession" class="search-slot">
          <button class="icon-btn search-btn" :class="{on: searchOpen}"
                  v-hint="searchOpen ? '收起搜索' : '在当前会话里搜索'"
                  :aria-label="searchOpen ? '收起搜索' : '在当前会话里搜索'"
                  :aria-pressed="searchOpen" @click="toggleSearch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
          </button>
          <div v-if="searchOpen" class="search-pop">
            <div class="search-box">
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
          </div>
        </span>
        <!-- 附加属性：紧跟搜索键右边（展开的面板在 AttrPanel.vue 里，挂在键的正下方） -->
        <AttrPanel v-if="activeSession" />
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
      <!-- 手机端三个入口：全屏 + 面板（右侧设置弹层）+ 更多（⋮，收纳模型/思考/主题）。
           桌面断点由 CSS 隐藏（全屏键只在手机端出现） -->
      <button class="icon-btn mobile-full-btn"
              v-hint="isFullscreen ? '退出全屏' : '全屏显示'"
              :aria-label="isFullscreen ? '退出全屏' : '全屏显示'"
              :aria-pressed="isFullscreen" @click="toggleFullscreen">
        <svg v-if="isFullscreen" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3v6H3"/><path d="M15 21v-6h6"/><path d="M3 9l6-6"/><path d="M21 15l-6 6"/></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5"/><path d="M20 15v5h-5"/><path d="M4 4l6 6"/><path d="M20 20l-6-6"/></svg>
      </button>
      <button class="icon-btn mobile-panel-btn" :class="{on: mobilePanelOpen}"
              v-hint="'打开控制面板'" aria-label="打开控制面板"
              :aria-pressed="mobilePanelOpen" @click="toggleMobilePanel">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
        <!-- 面板里有没保存的改动就点一个小圆点：手机上图标列在弹层里，收着的时候看不见 -->
        <span v-if="panelAnyDirty" class="tab-dot"></span>
      </button>
      <button class="icon-btn mobile-more-btn" aria-label="更多设置" @click="toggleMore">&#8942;</button>
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
        <div class="more-row">
          <span class="more-label">生成</span>
          <button class="ghost-btn mobile-stop-all" @click="stopAllGenerations">停止所有生成</button>
        </div>
        <div class="more-row">
          <span class="more-label">备份</span>
          <button class="ghost-btn mobile-backup" :disabled="backupBusy" @click="runBackup">
            {{ backupBusy ? "备份中…" : "手动备份" }}
          </button>
        </div>
        <!-- 结果就显示在菜单里：文件名 manual-…，与启动时自动备份的 chatbot-… 分开 -->
        <p v-if="backupNote" class="hint more-note">{{ backupNote }}</p>
      </div>
    </header>
</template>

<script setup>
import { computed, toRefs } from "vue";
import { store } from "../store.js";
import AttrPanel from "./AttrPanel.vue";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  backupBusy,
  backupNote,
  currentModel,
  currentModelSupportsThinking,
  desktopConfigOpen,
  desktopPhoneView,
  disableThinking,
  initError,
  isDesktop,
  isFullscreen,
  limits,
  mobileMoreOpen,
  mobilePanelOpen,
  modelWarning,
  models,
  ollamaBusy,
  orphanActive,
  panelAnyDirty,
  renameText,
  renaming,
  searchIndex,
  searchOpen,
  searchQuery,
  searchTotal,
  sideCollapsed,
  theme,
  thinkToggleTitle,
  wco,
} = toRefs(store);

// 主题三态的图标 / 短名来自 store（窗口标题栏那一行也在用，见 TitleBar.vue）

// 重命名输入框的宽度按**当前名称**算（中日韩字符按两个宽度估）：不然它是一条写死的宽框，
// 短名字也占那么大地方。6ch 起、40ch 封顶。
const titleInputWidth = computed(() => {
  const text = store.renameText || "";
  const w = [...text].reduce(
    (n, c) => n + (/[\u2E80-\u9FFF\u3000-\u303F\uFF00-\uFF60]/.test(c) ? 2 : 1), 0);
  return `${Math.min(Math.max(w + 2, 6), 40)}ch`;
});

// 汉堡：桌面断点收起/展开左侧栏；手机断点打开抽屉（关闭走遮罩）
const sideToggleHint = () => window.innerWidth <= 640
  ? "打开左侧栏"
  : (store.sideCollapsed ? "展开左侧栏" : "收起左侧栏");
function toggleSide() {
  if (window.innerWidth <= 640) store.mobileSideOpen = !store.mobileSideOpen;
  else store.sideCollapsed = !store.sideCollapsed;
}
// 搜索条与更多菜单互斥：展开一个时收起另一个，避免两个浮层叠着
function toggleSearch() {
  store.searchOpen = !store.searchOpen;
  store.mobileMoreOpen = false;
}
function toggleMore() {
  store.mobileMoreOpen = !store.mobileMoreOpen;
  store.searchOpen = false;
}

// 模板用到的方法（函数不是响应式的，直接解构）。
// 「配置」面板的开合与"点外部就关"跟着窗口标题栏那一行走（TitleBar.vue），这里不再管。
const {
  clearSearch,
  cycleTheme,
  isNear,
  len,
  loadModels,
  runBackup,
  saveRename,
  searchNext,
  searchPrev,
  startRename,
  stopAllGenerations,
  switchModel,
  themeButtonTitle,
  themeIcon,
  themeLabel,
  toggleFullscreen,
  toggleMobilePanel,
  toggleThinking,
} = store;
</script>
