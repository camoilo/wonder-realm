<template>
<aside class="sidebar" :class="{collapsed: sideCollapsed}">
    <div class="sidebar-inner">
      <div class="side-label">模式选择</div>
      <nav class="mode-tabs">
        <button v-for="(m, key) in MODES" :key="key" class="mode-tab" :class="{active: mode === key}"
                @click="switchMode(key)">{{ m.label }}</button>
      </nav>

      <div class="side-list">
        <template v-if="isCharacterMode">
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
              <button class="icon-btn" title="编辑角色" @click.stop="openCharacterModal(c)">✎</button>
            </div>
            <div v-show="expandedChars[c.id]" class="char-sessions">
              <div v-for="s in sessionsOf(c.id)" :key="s.id" class="session-row"
                   :class="{active: activeSessionId === s.id}" @click="openSession(s.id)">
                <span class="session-title">{{ s.title }}</span>
                <button class="icon-btn danger" title="删除会话" @click.stop="removeSession(s)">✕</button>
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
                <button class="icon-btn danger" title="删除会话" @click.stop="removeSession(s)">✕</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-if="freeSessions.length === 0" class="side-empty"><p>还没有会话</p></div>
          <div v-for="s in freeSessions" :key="s.id" class="session-row"
               :class="{active: activeSessionId === s.id}" @click="openSession(s.id)">
            <span class="session-title">{{ s.title }}</span>
            <button class="icon-btn danger" title="删除会话" @click.stop="removeSession(s)">✕</button>
          </div>
        </template>
      </div>

      <div class="side-footer">
        <button v-if="isCharacterMode" class="ghost-btn full" @click="openCharacterModal()">新建角色</button>
        <button class="primary-btn full" @click="newSession">新建会话</button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { toRefs } from "vue";
import { store, MODES } from "../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSessionId,
  characters,
  expandedChars,
  freeSessions,
  isCharacterMode,
  mode,
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
