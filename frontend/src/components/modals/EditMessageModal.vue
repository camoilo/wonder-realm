<template>
<div class="modal-mask" v-if="editingId !== null"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal edit-modal">
      <h2>编辑消息</h2>
      <!-- 两个输入框：弹窗里唯一可滚动的部分（操作行在它外面，始终可见） -->
      <div class="modal-body">
        <label v-if="editForm.hasScenario" class="edit-field">
          <span class="edit-label">情境说明</span>
          <div class="counted">
            <textarea v-model="editForm.scenario" rows="4" @input="autoGrow"
                      :maxlength="limits.scenario"
                      placeholder="场景、动作、氛围等（留空则不显示情境块）"></textarea>
            <span class="char-count" :class="{near: isNear(editForm.scenario, limits.scenario)}">{{ len(editForm.scenario) }}/{{ limits.scenario }}</span>
          </div>
        </label>
        <label class="edit-field">
          <span class="edit-label">{{ editForm.contentLabel }}</span>
          <div class="counted">
            <textarea v-model="editForm.content" rows="5" @input="autoGrow"
                      :maxlength="limits.message" :placeholder="editForm.contentPlaceholder"></textarea>
            <span class="char-count" :class="{near: isNear(editForm.content, limits.message)}">{{ len(editForm.content) }}/{{ limits.message }}</span>
          </div>
        </label>
        <p v-if="editForm.contentHint" class="hint">{{ editForm.contentHint }}</p>
      </div>
      <div class="edit-actions">
        <span class="hint">仅影响后续生成的上下文，不修改已沉淀的记忆</span>
        <div class="edit-btns">
          <button class="ghost-btn" @click="cancelEdit">取消</button>
          <button class="primary-btn"
                  :disabled="!editForm.content.trim() && !(editForm.hasScenario && editForm.scenario.trim())"
                  @click="saveEdit">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  editForm,
  editingId,
  limits,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  autoGrow,
  cancelEdit,
  isNear,
  len,
  saveEdit,
} = store;

// 点窗口外 = 取消编辑（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(cancelEdit);
</script>
