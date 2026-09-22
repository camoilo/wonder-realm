<template>
<div class="modal-mask" v-if="confirmBox.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal confirm-modal">
      <p class="confirm-text">{{ confirmBox.text }}</p>
      <div class="modal-actions">
        <button class="ghost-btn" @click="answerConfirm(false)">取消</button>
        <button class="danger-btn" @click="answerConfirm(true)">确认</button>
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
  confirmBox,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  answerConfirm,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(() => answerConfirm(false));
</script>
