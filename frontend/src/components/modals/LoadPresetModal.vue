<template>
<div class="modal-mask" v-if="loadPresetModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal load-modal">
      <h2>载入预设</h2>
      <!-- 左边挑、右边看详情：预设名字可能重复，光看一行字分不清是谁，
           这里把头像、身份、外观都摆出来。确认后立即写入"当前使用的设定"。 -->
      <div class="modal-body preset-split">
        <div class="preset-list">
          <button v-for="p in profilePresets" :key="p.id" class="preset-item"
                  :class="{on: p.id === loadPresetModal.pick}"
                  @click="pickLoadPreset(p.id)">
            <span class="avatar sm">
              <img v-if="p.avatar" :src="p.avatar" alt="">
              <template v-else>{{ (p.name || "预").slice(0, 1) }}</template>
            </span>
            <span class="preset-item-text">
              <span class="preset-item-name">{{ p.name }}</span>
              <span class="preset-item-sub">{{ p.identity || "（没填身份）" }}</span>
              <span class="preset-item-bind">角色：{{ presetBindLabel(p) }}</span>
            </span>
          </button>
        </div>
        <div class="preset-detail">
          <template v-if="picked">
            <div class="avatar-pick">
              <span class="avatar xl">
                <img v-if="picked.avatar" :src="picked.avatar" alt="">
                <template v-else>{{ (picked.name || "预").slice(0, 1) }}</template>
              </span>
            </div>
            <dl>
              <dt>名字</dt><dd>{{ picked.name }}</dd>
              <dt>身份</dt><dd>{{ picked.identity || "（未填）" }}</dd>
              <dt>外观</dt><dd class="pre">{{ picked.appearance || "（未填）" }}</dd>
              <dt>绑定角色</dt><dd>{{ presetBindLabel(picked) }}</dd>
            </dl>
          </template>
        </div>
      </div>
      <div class="modal-actions">
        <span class="hint">载入会用这条预设覆盖"当前使用的设定"</span>
        <button class="ghost-btn" @click="closeLoadModal">取消</button>
        <button class="primary-btn" :disabled="!picked" @click="confirmLoadPreset">载入这条</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, toRefs } from "vue";
import { store } from "../../store.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  loadPresetModal,
  profilePresets,
} = toRefs(store);

const picked = computed(() =>
  store.profilePresets.find((p) => p.id === store.loadPresetModal.pick) || null
);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  closeLoadModal,
  confirmLoadPreset,
  pickLoadPreset,
  presetBindLabel,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(closeLoadModal);
</script>
