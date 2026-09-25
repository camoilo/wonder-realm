<template>
<!-- 词库编辑器：世界设定的动态列表（面板里与预设弹窗里各有一份），所以抽成组件。
     目标表单由调用方传进来，增删都走同一个 store 方法，两边行为不会走偏。
     readonly：面板那一页只读（内容来自绑定的预设），此时不能增删、框也不可改。 -->
<div class="field">
  <span class="field-label">词库</span>
  <div v-for="(t, i) in form.terms" :key="i" class="term-row">
    <div class="term-head">
      <span class="term-index">词条 {{ i + 1 }}</span>
      <button v-if="!readonly" type="button" class="term-del" v-hint="'删除这一条'" aria-label="删除这一条"
              @click="removeTerm(form, i)">删除</button>
    </div>
    <div class="counted">
      <input v-model="t.term" type="text" :maxlength="limits.world_term" placeholder="专有名词" :readonly="readonly">
      <span class="char-count inline"
            :class="{near: isNear(t.term, limits.world_term)}">{{ len(t.term) }}/{{ limits.world_term }}</span>
    </div>
    <div class="counted">
      <textarea v-model="t.meaning" rows="2" :maxlength="limits.world_term_meaning"
                placeholder="它的含义（可留空）" :readonly="readonly"></textarea>
      <span class="char-count"
            :class="{near: isNear(t.meaning, limits.world_term_meaning)}">{{ len(t.meaning) }}/{{ limits.world_term_meaning }}</span>
    </div>
  </div>
  <p v-if="readonly && !form.terms.length" class="hint">这份世界没有词库。</p>
  <button v-if="!readonly" type="button" class="ghost-btn full"
          :disabled="form.terms.length >= limits.world_terms_max"
          @click="addTerm(form)">＋ 添加词条</button>
  <p v-if="!readonly" class="hint">
    最多 {{ limits.world_terms_max }} 条，按这里的顺序注入；名词留空的行在保存时自动丢弃。
  </p>
</div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

// 要编辑的那份世界设定（面板表单或预设弹窗里的表单）；readonly = 只看不改（面板那页）
defineProps({
  form: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
});

const {
  limits,
} = toRefs(store);

const {
  addTerm,
  isNear,
  len,
  removeTerm,
} = store;
</script>
