<template>
<aside class="sidebar" :class="{collapsed: sideCollapsed, 'mobile-open': mobileSideOpen}">
    <div class="sidebar-inner">
      <div class="app-brand">
        <span class="brand-mark">◇</span>
        <span class="brand-stack">
          <span class="brand-name">多模式对话助手</span>
          <span class="brand-sub">本地 · Ollama</span>
        </span>
      </div>
      <div class="side-label">模式选择</div>
      <nav class="mode-tabs">
        <button v-for="(m, key) in MODES" :key="key" class="mode-tab" :class="{active: mode === key}"
                :aria-label="m.hint"
                @click="switchMode(key)"
                @mouseenter="hoveredMode = key" @mouseleave="hoveredMode = ''"
                @focus="hoveredMode = key" @blur="hoveredMode = ''">{{ m.label }}</button>
        <!-- 模式介绍：鼠标移入或键盘聚焦时出现。绝对定位在按钮行下方，所以不改变任何布局；
             pointer-events: none 让它不会截住鼠标，也就不会自己把自己关掉 -->
        <div v-if="hoveredMode" class="mode-tip" role="tooltip">{{ MODES[hoveredMode].hint }}</div>
      </nav>

      <div class="side-list">
        <template v-if="usesCharacter">
          <div v-if="characters.length === 0" class="side-empty">
            <p>还没有角色</p>
            <button class="ghost-btn full" @click="openCharacterModal()">创建第一个角色</button>
          </div>
          <div v-for="c in characters" :key="c.id" class="char-group">
            <div class="char-row" @click="toggleChar(c.id)">
              <span class="chevron" :class="{open: expandedChars[c.id]}">›</span>
              <span class="avatar sm">
                <img v-if="c.avatar" :src="c.avatar" alt="">
                <template v-else>{{ c.name.slice(0, 1) }}</template>
              </span>
              <span class="char-name">{{ c.name }}</span>
              <button class="icon-btn" v-hint="'编辑角色'" aria-label="编辑角色" @click.stop="openCharacterModal(c)">✎</button>
            </div>
            <div v-show="expandedChars[c.id]" class="char-sessions">
              <div v-for="s in sessionsOf(c.id)" :key="s.id" class="session-row"
                   :class="{active: activeSessionId === s.id}" @click="openSession(s.id)">
                <span class="session-title">{{ s.title }}</span>
                <button class="icon-btn danger" v-hint="'删除会话'" aria-label="删除会话" @click.stop="removeSession(s)">✕</button>
              </div>
              <div class="session-row add" @click="createSessionForCharacter(c.id)">＋ 新会话</div>
            </div>
          </div>
          <div v-if="orphanSessions.length" class="char-group">
            <div class="char-row muted"><span class="chevron"></span>已删除角色的会话</div>
            <div class="char-sessions">
              <div v-for="s in orphanSessions" :key="s.id" class="session-row"
                   :class="{active: activeSessionId === s.id}" @click="openSession(s.id)">
                <span class="session-title">{{ s.title }}</span>
                <button class="icon-btn danger" v-hint="'删除会话'" aria-label="删除会话" @click.stop="removeSession(s)">✕</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-if="directorSessions.length === 0" class="side-empty"><p>还没有会话</p></div>
          <div v-for="s in directorSessions" :key="s.id" class="session-row"
               :class="{active: activeSessionId === s.id}" @click="openSession(s.id)">
            <span class="session-title">{{ s.title }}</span>
            <button class="icon-btn danger" v-hint="'删除会话'" aria-label="删除会话" @click.stop="removeSession(s)">✕</button>
          </div>
        </template>
      </div>

      <div class="side-footer">
        <button v-if="usesCharacter" class="ghost-btn full" @click="openCharacterModal()">新建角色</button>
        <button class="primary-btn full" @click="newSession">新建会话</button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, toRefs } from "vue";
import { store, MODES } from "../store.js";

// 当前鼠标悬停（或键盘聚焦）的模式 key；空串表示不显示介绍浮层
const hoveredMode = ref("");

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSessionId,
  characters,
  expandedChars,
  directorSessions,
  usesCharacter,
  mode,
  mobileSideOpen,
  orphanSessions,
  sideCollapsed,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  createSessionForCharacter,
  newSession,
  openCharacterModal,
  openSession,
  removeSession,
  sessionsOf,
  switchMode,
  toggleChar,
} = store;
</script>
