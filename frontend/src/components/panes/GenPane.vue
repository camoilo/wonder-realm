<template>
<div v-for="f in fieldsOf(activeSession.mode)" :key="f.key" class="field">
  <span class="field-label">{{ f.label }}</span>
  <div v-if="f.type === 'radio'" class="radio-row">
    <label v-for="opt in f.options" :key="opt[0]" class="radio-item" :class="{on: genForm[f.key] === opt[0]}">
      <input type="radio" :name="f.key" :value="opt[0]" v-model="genForm[f.key]">{{ opt[1] }}
    </label>
  </div>
  <div v-else-if="f.type === 'tags'" class="tags-box">
    <div class="tag-chips">
      <span v-for="p in f.presets" :key="p" class="chip-btn"
            :class="{on: (genForm[f.key] || []).includes(p)}" @click="toggleTag(f.key, p)">{{ p }}</span>
    </div>
    <div class="tag-custom">
      <span v-for="t in customTags(f)" :key="t" class="tag">{{ t }}<button class="tag-x" @click="removeTag(f.key, t)">&times;</button></span>
      <input class="tag-input" v-model="tagDraft[f.key]" :placeholder="f.placeholder"
             :maxlength="f.max" @keydown.enter.prevent="addTag(f.key)" @blur="addTag(f.key)">
    </div>
  </div>
  <div v-else class="input-wrap">
    <div class="counted">
      <textarea v-if="f.type === 'textarea'" v-model="genForm[f.key]" rows="2"
                :maxlength="f.max" :placeholder="f.placeholder"></textarea>
      <input v-else type="text" v-model="genForm[f.key]" :maxlength="f.max" :placeholder="f.placeholder">
      <span class="char-count" :class="{near: isNear(genForm[f.key], f.max), inline: f.type !== 'textarea'}">{{ len(genForm[f.key]) }}/{{ f.max }}</span>
    </div>
    <button v-if="genForm[f.key]" class="clear-btn" title="清空这一栏" tabindex="-1"
            @click="genForm[f.key] = ''">✕</button>
  </div>
  <span v-if="f.hint" class="field-hint">{{ f.hint }}</span>
</div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  activeSession,
  genForm,
  tagDraft,
} = toRefs(store);

const {
  addTag,
  customTags,
  fieldsOf,
  isNear,
  len,
  removeTag,
  toggleTag,
} = store;
</script>
