<template>
<label class="field">世界名称
  <div class="counted">
    <input v-model="worldForm.name" type="text" :maxlength="limits.world_name"
           placeholder="只用于自己辨认，不发给模型">
    <span class="char-count inline"
          :class="{near: isNear(worldForm.name, limits.world_name)}">{{ len(worldForm.name) }}/{{ limits.world_name }}</span>
  </div>
</label>
<label class="field">描述
  <div class="counted">
    <textarea v-model="worldForm.description" rows="4" :maxlength="limits.world_description"
              placeholder="这个世界的详细信息：地理、时代、势力、氛围…"></textarea>
    <span class="char-count"
          :class="{near: isNear(worldForm.description, limits.world_description)}">{{ len(worldForm.description) }}/{{ limits.world_description }}</span>
  </div>
</label>
<label class="field">规则
  <div class="counted">
    <textarea v-model="worldForm.rules" rows="4" :maxlength="limits.world_rules"
              placeholder="独属于这个世界的规则：力量体系、禁忌、铁律…"></textarea>
    <span class="char-count"
          :class="{near: isNear(worldForm.rules, limits.world_rules)}">{{ len(worldForm.rules) }}/{{ limits.world_rules }}</span>
  </div>
</label>
<div class="field">
  <span class="field-label">词库</span>
  <div v-for="(t, i) in worldForm.terms" :key="i" class="term-row">
    <div class="term-head">
      <span class="term-index">词条 {{ i + 1 }}</span>
      <button type="button" class="term-del" title="删除这一条"
              @click="removeTerm(i)">删除</button>
    </div>
    <div class="counted">
      <input v-model="t.term" type="text" :maxlength="limits.world_term" placeholder="专有名词">
      <span class="char-count inline"
            :class="{near: isNear(t.term, limits.world_term)}">{{ len(t.term) }}/{{ limits.world_term }}</span>
    </div>
    <div class="counted">
      <textarea v-model="t.meaning" rows="2" :maxlength="limits.world_term_meaning"
                placeholder="它的含义（可留空）"></textarea>
      <span class="char-count"
            :class="{near: isNear(t.meaning, limits.world_term_meaning)}">{{ len(t.meaning) }}/{{ limits.world_term_meaning }}</span>
    </div>
  </div>
  <button type="button" class="ghost-btn full"
          :disabled="worldForm.terms.length >= limits.world_terms_max"
          @click="addTerm">＋ 添加词条</button>
  <p class="hint">
    最多 {{ limits.world_terms_max }} 条，按这里的顺序注入；名词留空的行在保存时自动丢弃。
  </p>
</div>
<p class="hint">名称只给自己看；描述、规则、词库会写进三种模式的提示词（在角色设定之前）。</p>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  limits,
  worldForm,
} = toRefs(store);

const {
  addTerm,
  isNear,
  len,
  removeTerm,
} = store;
</script>
