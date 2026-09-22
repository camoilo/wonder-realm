<template>
<p class="memory-meta">
  已归档 {{ memoryData.message_count }} 条消息<template v-if="memoryData.updated_at"> · 更新于 {{ memoryData.updated_at }}</template>
  <a class="refresh-link" @click="loadMemory">刷新</a>
  <span v-if="memoryData.compress_failed" class="warn-text">上次压缩失败</span>
</p>
<div class="counted">
  <textarea class="memory-text" v-model="memoryText" rows="10" :maxlength="limits.memory"
            placeholder="暂无记忆，随对话自动沉淀"></textarea>
  <span class="char-count" :class="{near: isNear(memoryText, limits.memory)}">{{ len(memoryText) }}/{{ limits.memory }}</span>
</div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  limits,
  memoryData,
  memoryText,
} = toRefs(store);

const {
  isNear,
  len,
  loadMemory,
} = store;
</script>
