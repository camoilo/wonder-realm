<template>
<!-- 对话页顶部的附加属性浮层（见 DEVELOPMENT §2.6）。
     **sticky**：静止时它是内容流里的一项，天然把消息往下推（不会遮住任何人）；
     往下滚时它贴住对话区顶部，消息从它下面穿过——也就是"位于顶部、覆盖在消息之上"。
     这样不必量高度、也就不依赖 rAF / ResizeObserver 的回调时机。
     **收起时只是一个图标**，展开才显示标题与详细内容。 -->
<div v-if="showAttrPanel" class="attr-panel" :class="{collapsed: attrsCollapsed}">
  <button v-if="attrsCollapsed" class="attr-icon" v-hint="'展开附加属性'"
          aria-label="展开附加属性" @click="attrsCollapsed = false">▤</button>
  <template v-else>
    <button class="attr-toggle" v-hint="'收起附加属性'" aria-expanded="true"
            @click="attrsCollapsed = true">
      <span class="attr-caret">▾</span>
      <span class="attr-title">附加属性</span>
    </button>
    <div class="attr-body">
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
  </template>
</div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

const {
  attrsCollapsed,
  latestAttrs,
  showAttrPanel,
} = toRefs(store);

const {
  attrPercent,
  attrText,
} = store;
</script>
