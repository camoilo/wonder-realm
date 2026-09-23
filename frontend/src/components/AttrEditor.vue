<template>
<!-- 附加属性定义编辑器（放在角色设定标签页里，见 DEVELOPMENT §2.6）。
     一行一条：名称（必填）+ 类型（必选）+ 解释（可选，只进提示词）+ 删除。
     目标表单由调用方传进来，增删都走同一个 store 方法。 -->
<div class="field">
  <span class="field-label">附加属性</span>
  <p class="hint">
    角色的动态状态（如心情、好感、表情）。模型每轮都会输出它们的当前值，
    最新一份显示在对话页顶部的浮层上；注入上下文时只用上一条消息的那一份。
  </p>
  <div v-for="(d, i) in form.attr_defs" :key="i" class="attr-row">
    <div class="attr-head">
      <span class="term-index">属性 {{ i + 1 }}</span>
      <button type="button" class="term-del" v-hint="'删除这一条'" aria-label="删除这一条"
              @click="removeAttr(form, i)">删除</button>
    </div>
    <label class="attr-line">
      <span class="attr-label">名称</span>
      <div class="counted">
        <input v-model="d.name" type="text" :maxlength="limits.attr_name" placeholder="如：好感">
        <span class="char-count inline"
              :class="{near: isNear(d.name, limits.attr_name)}">{{ len(d.name) }}/{{ limits.attr_name }}</span>
      </div>
    </label>
    <label class="attr-line">
      <span class="attr-label">类型</span>
      <select v-model="d.type" :class="{empty: !d.type}">
        <option value="">选择类型…</option>
        <option v-for="t in ATTR_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
    </label>
    <label class="attr-line">
      <span class="attr-label">解释</span>
      <div class="counted">
        <input v-model="d.hint" type="text" :maxlength="limits.attr_hint"
               placeholder="给模型的取值参考，可留空（如：对用户的好感程度）">
        <span class="char-count inline"
              :class="{near: isNear(d.hint, limits.attr_hint)}">{{ len(d.hint) }}/{{ limits.attr_hint }}</span>
      </div>
    </label>
  </div>
  <button type="button" class="ghost-btn full"
          :disabled="form.attr_defs.length >= limits.attr_max"
          @click="addAttr(form)">＋ 添加属性</button>
  <p v-if="attrError" class="avatar-error">{{ attrError }}</p>
  <p class="hint">
    最多 {{ limits.attr_max }} 条；名称留空的行在保存时自动丢弃，填了名称就必须选类型。
    属性值不进消息气泡，只在顶部浮层与编辑面板里出现。
  </p>
</div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

// 要编辑的那份角色表单（右侧面板的 charForm）
defineProps({ form: { type: Object, required: true } });

const {
  ATTR_TYPES,
  attrError,
  limits,
} = toRefs(store);

const {
  addAttr,
  isNear,
  len,
  removeAttr,
} = store;
</script>
