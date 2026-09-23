<template>
<!-- 对话页顶部的附加属性浮层（见 DEVELOPMENT §2.6）：
     覆盖在消息之上、不占布局，点标题行收起成一个小胶囊；只在选中会话且这一轮有属性时出现。
     文字型直接显示文字，百分比型渲染成横向进度条。 -->
<div v-if="showAttrPanel" class="attr-panel" :class="{collapsed: attrsCollapsed}">
  <button class="attr-toggle" v-hint="attrsCollapsed ? '展开附加属性' : '收起附加属性'"
          :aria-expanded="!attrsCollapsed" @click="attrsCollapsed = !attrsCollapsed">
    <span class="attr-caret">{{ attrsCollapsed ? "▸" : "▾" }}</span>
    <span class="attr-title">附加属性</span>
    <span v-if="attrsCollapsed" class="attr-summary">{{ summary }}</span>
  </button>
  <div v-if="!attrsCollapsed" class="attr-body">
    <div v-for="a in latestAttrs" :key="a.name" class="attr-item">
      <span class="attr-name">{{ a.name }}</span>
      <template v-if="a.type === 'percent'">
        <span class="attr-bar" role="img" :aria-label="`${a.name} ${attrText(a)}`">
          <span class="attr-bar-fill" :style="{ width: attrPercent(a) + '%' }"></span>
        </span>
        <span class="attr-num">{{ attrText(a) }}</span>
      </template>
      <span v-else class="attr-value">{{ attrText(a) }}</span>
    </div>
  </div>
</div>
</template>

<script setup>
import { computed, toRefs } from "vue";
import { store } from "../store.js";

const {
  attrsCollapsed,
  latestAttrs,
  showAttrPanel,
} = toRefs(store);

// 收起时那一行摘要：文字型直接给文字、百分比型给"42%"，让用户不展开也能看个大概
const summary = computed(() =>
  latestAttrs.value.map((a) => `${a.name} ${store.attrText(a)}`).join(" · ")
);

const {
  attrPercent,
  attrText,
} = store;
</script>
