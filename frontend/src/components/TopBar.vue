<template>
<header class="topbar">
      <div class="title-area">
        <button class="icon-btn rail-toggle" :title="sideCollapsed ? '展开左侧栏' : '收起左侧栏'"
                @click="sideCollapsed = !sideCollapsed">&#9776;</button>
        <template v-if="activeSession">
          <span v-if="renaming" class="counted title-counted">
            <input v-model="renameText" class="title-input" :maxlength="limits.title"
                   @keydown.enter.prevent="saveRename" @blur="saveRename" />
            <span class="char-count inline" :class="{near: isNear(renameText, limits.title)}">{{ len(renameText) }}/{{ limits.title }}</span>
          </span>
          <h1 v-else class="title" title="点击重命名" @click="startRename">{{ activeSession.title }}</h1>
          <span class="chip">{{ MODES[activeSession.mode].label }}</span>
          <span v-if="orphanActive" class="chip warn">角色已删除 · 仅可查看</span>
        </template>
        <h1 v-else class="title muted">未选择会话</h1>
      </div>
      <div class="toolbar">
        <span v-if="initError" class="chip warn">{{ initError }}</span>
        <span v-if="modelWarning" class="model-warning">{{ modelWarning }}</span>
        <!-- 会话内搜索：命中处标黄，↑/↓ 在命中之间跳转（Enter 下一个、Shift+Enter 上一个）。
             计数与两个键**始终**占位（不按有无关键词显示/隐藏）——否则输入前后整个框会变宽
             变窄，看起来像换了个控件；清空用 Esc，不再多放一个 ✕ 占顶栏宽度 -->
        <div v-if="activeSession" class="search-box">
          <input v-model="searchQuery" type="text" class="search-input"
                 title="在当前会话里搜索：Enter 下一个、Shift+Enter 上一个、Esc 清空"
                 placeholder="搜索当前会话"
                 @keydown.enter.exact.prevent="searchNext"
                 @keydown.shift.enter.prevent="searchPrev"
                 @keydown.esc="clearSearch">
          <span class="search-count">{{ searchTotal ? searchIndex + 1 : 0 }}/{{ searchTotal }}</span>
          <button class="icon-btn" title="上一个（Shift+Enter）" :disabled="!searchTotal" @click="searchPrev">↑</button>
          <button class="icon-btn" title="下一个（Enter）" :disabled="!searchTotal" @click="searchNext">↓</button>
        </div>
        <select v-model="currentModel" class="model-select" :disabled="models.length === 0" @change="switchModel">
          <option value="" disabled>选择模型</option>
          <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}{{ m.thinking ? "（思考型）" : "" }}</option>
        </select>
        <button class="ghost-btn think-btn" :class="{off: disableThinking}"
                :disabled="!currentModelSupportsThinking"
                :title="thinkToggleTitle"
                @click="toggleThinking">{{ disableThinking ? "思考：关" : "思考：开" }}</button>
        <!-- "配置"面板的开关。三点约定（见 DEVELOPMENT §9.6 界面约定）：**常驻**（没有会话时也在，只是禁用）、
             **改名"配置"**、**位置固定**——它永远待在顶栏最右这一格，面板开、关都不移动，
             所以能"不挪鼠标点开、看一眼、再点关"。文案只换箭头、字数不变，宽度也不变。
             未保存的小圆点同样常驻（面板收起时标签看不见，只能靠它提示） -->
        <button class="ghost-btn panel-toggle"
                :disabled="!activeSession"
                :title="!activeSession ? '先打开一个会话，才能打开配置面板'
                        : ((panelCollapsed ? '展开配置面板' : '收起配置面板')
                           + (anyDirty ? '（有未保存的修改）' : ''))"
                @click="panelCollapsed = !panelCollapsed">{{ activeSession && !panelCollapsed ? "配置 ‹" : "配置 ›" }}<span v-if="anyDirty" class="dirty-dot"></span></button>
      </div>
    </header>
</template>

<script setup>
import { toRefs } from "vue";
import { store, MODES } from "../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  anyDirty,
  currentModel,
  currentModelSupportsThinking,
  disableThinking,
  initError,
  limits,
  modelWarning,
  models,
  orphanActive,
  panelCollapsed,
  renameText,
  renaming,
  searchIndex,
  searchQuery,
  searchTotal,
  sideCollapsed,
  thinkToggleTitle,
} = toRefs(store);

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
  toggleThinking,
} = store;
</script>
