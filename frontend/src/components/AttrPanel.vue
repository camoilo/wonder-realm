<template>
<!-- 附加属性的入口与下拉（见 DEVELOPMENT §2.6）。
     入口是**顶栏紧挨着搜索键右边**的那颗图标键（键永远在，面板按需弹出），
     展开后是一张小下拉：贴在键的正下方、右边缘对齐，宽度只占屏幕一半（手机端 50vw），
     不像早先那样在对话区顶部铺一张 400px 的 sticky 卡片（用户要求"移进顶栏、缩小"）。
     **面板里不再放 × 键**：收起就用顶栏那颗键本身（用户要求去掉重复的关闭入口）。 -->
<div v-if="showAttrPanel" class="attr-slot">
  <button class="icon-btn attr-btn" :class="{on: !attrsCollapsed}"
          v-hint="attrsCollapsed ? '查看附加属性' : '收起附加属性'"
          :aria-label="attrsCollapsed ? '查看附加属性' : '收起附加属性'"
          :aria-expanded="!attrsCollapsed" @click="attrsCollapsed = !attrsCollapsed">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5-7 4 14 2.5-7h5"/></svg>
  </button>
  <div v-if="!attrsCollapsed" class="attr-panel">
    <div class="attr-head">
      <span class="attr-title">附加属性</span>
    </div>
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
  </div>
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
