<template>
<div class="modal-mask" v-if="confirmBox.visible" @click.self="answerConfirm(false)">
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

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  confirmBox,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  answerConfirm,
} = store;
</script>
