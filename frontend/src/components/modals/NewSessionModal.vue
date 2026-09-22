<template>
<div class="modal-mask" v-if="newSessionModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal">
      <h2>新会话 · {{ MODES[mode].label }}</h2>
      <label class="field">角色
        <select v-model="newSessionModal.characterId">
          <option v-for="c in characters" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </label>
      <label class="field">标题（可选）
        <div class="counted">
          <input v-model="newSessionModal.title" type="text" :maxlength="limits.title"
                 placeholder="留空则首轮对话后自动命名">
          <span class="char-count inline" :class="{near: isNear(newSessionModal.title, limits.title)}">{{ len(newSessionModal.title) }}/{{ limits.title }}</span>
        </div>
      </label>
      <div class="modal-actions">
        <button class="ghost-btn" @click="newSessionModal.visible = false">取消</button>
        <button class="primary-btn" :disabled="!newSessionModal.characterId" @click="confirmNewSession">创建</button>
      </div>
      <p class="hint"><a @click="newSessionModal.visible = false; openCharacterModal()">没有角色？先创建一个</a></p>
    </div>
  </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store, MODES } from "../../store.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  characters,
  limits,
  mode,
  newSessionModal,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  confirmNewSession,
  isNear,
  len,
  openCharacterModal,
} = store;

// 点窗口外 = 关闭（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(() => {
  newSessionModal.value.visible = false;
});
</script>
