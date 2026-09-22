<template>
<div class="modal-mask crop-mask" v-if="crop.visible" @click.self="cancelCrop">
    <div class="modal crop-modal">
      <h2>裁剪头像</h2>
      <p class="hint">拖动图片调整位置，方框内的部分会成为头像</p>
      <div class="crop-view" :style="{ width: crop.view + 'px', height: crop.view + 'px' }"
           @pointerdown="cropDown" @pointermove="cropMove"
           @pointerup="cropUp" @pointercancel="cropUp">
        <img :src="crop.src" :style="cropImageStyle" alt="" draggable="false">
      </div>
      <p v-if="cropSamplePx && cropSamplePx < 256" class="crop-warn">
        取景范围只有 {{ cropSamplePx }}×{{ cropSamplePx }} 像素，放大到 256 后会偏糊；缩小一点缩放或换更大的图
      </p>
      <label class="crop-zoom">
        <span>缩放</span>
        <input type="range" min="1" :max="crop.maxZoom" step="0.01" :value="crop.zoom"
               @input="setCropZoom($event.target.value)">
        <button class="ghost-btn crop-reset" type="button" @click="setCropZoom(1)">复位</button>
      </label>
      <div class="modal-actions">
        <button class="ghost-btn" @click="cancelCrop">取消</button>
        <button class="primary-btn" @click="confirmCrop">确定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  crop,
  cropImageStyle,
  cropSamplePx,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  cancelCrop,
  confirmCrop,
  cropDown,
  cropMove,
  cropUp,
  setCropZoom,
} = store;
</script>
