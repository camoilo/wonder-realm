<template>
<div class="modal-mask" v-if="bindModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal load-modal">
      <h2>{{ kind.bindTitle }}</h2>
      <!-- 左边挑、右边看详情：预设名字可能重复，光看一行字分不清是谁，这里把内容摆出来。
           确认后**绑定**（写角色的 profile_id / world_id，导演会话写 world_id）——面板那两页
           从此只读地显示这份内容。"我的设定"与"世界设定"共用这一对弹窗，
           差别只有右侧的字段与接口（kind 决定，见 helpers.js 的 PRESET_KINDS）。 -->
      <div class="modal-body preset-split">
        <div class="preset-list">
          <button v-for="p in presets" :key="p.id" class="preset-item"
                  :class="{on: p.id === bindModal.pick}"
                  @click="pickBindPreset(p.id)">
            <span class="avatar sm">
              <img v-if="kind.hasAvatar && p.avatar" :src="p.avatar" alt="">
              <template v-else>{{ (p.name || "预").slice(0, 1) }}</template>
            </span>
            <span class="preset-item-text">
              <span class="preset-item-name">{{ p.name }}</span>
              <span class="preset-item-sub">{{ kind.sub(p) }}</span>
              <span class="preset-item-bind">角色：{{ presetBindLabel(p) }}</span>
            </span>
          </button>
        </div>
        <div class="preset-detail">
          <template v-if="picked">
            <div class="avatar-pick">
              <span class="avatar xl">
                <img v-if="kind.hasAvatar && picked.avatar" :src="picked.avatar" alt="">
                <template v-else>{{ (picked.name || "预").slice(0, 1) }}</template>
              </span>
            </div>
            <dl>
              <template v-if="isProfile">
                <dt>名字</dt><dd>{{ picked.name }}</dd>
                <dt>身份</dt><dd>{{ picked.identity || "（未填）" }}</dd>
                <dt>外观</dt><dd class="pre">{{ picked.appearance || "（未填）" }}</dd>
              </template>
              <template v-else>
                <dt>世界名称</dt><dd>{{ picked.name }}</dd>
                <dt>描述</dt><dd class="pre">{{ picked.description || "（未填）" }}</dd>
                <dt>规则</dt><dd class="pre">{{ picked.rules || "（未填）" }}</dd>
                <dt>词库</dt>
                <dd class="pre">
                  <template v-if="(picked.terms || []).length">
                    <div v-for="(t, i) in picked.terms" :key="i">{{ t.term }}：{{ t.meaning || "（无解释）" }}</div>
                  </template>
                  <template v-else>（未填）</template>
                </dd>
              </template>
              <dt>绑定角色</dt><dd>{{ presetBindLabel(picked) }}</dd>
            </dl>
          </template>
        </div>
      </div>
      <div class="modal-actions">
        <span class="hint">{{ kind.bindHint }}</span>
        <button class="ghost-btn" @click="closeBindModal">取消</button>
        <button class="primary-btn" :disabled="!picked" @click="confirmBind">确定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, toRefs } from "vue";
import { store } from "../../store.js";
import { PRESET_KINDS } from "../../store/helpers.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  bindModal,
} = toRefs(store);

// 这一次打开的是哪种预设：标题、列表、右侧字段都由它决定
const kind = computed(() => PRESET_KINDS[store.bindModal.kind] || PRESET_KINDS.profile);
const isProfile = computed(() => store.bindModal.kind === "profile");
const presets = computed(() => store[kind.value.listKey]);
const picked = computed(() =>
  presets.value.find((p) => p.id === store.bindModal.pick) || null
);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  closeBindModal,
  confirmBind,
  pickBindPreset,
  presetBindLabel,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(closeBindModal);
</script>
