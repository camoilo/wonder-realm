<template>
<!-- 我的设定（见 DEVELOPMENT §2.3）：**这一页只读** —— 显示的是选中的那条身份预设的内容。
     改内容去「编辑预设」，启用/换一份去「选择预设」；未选择就是不启用（不注入身份）。
     绑定在角色侧（characters.profile_id），所以换角色就是换一份设定。 -->
<div class="preset-current">当前预设：<b>{{ currentPresetLabel }}</b></div>
<div class="preset-row preset-actions">
  <button class="ghost-btn" :disabled="!profilePresets.length"
          v-hint="boundProfileId ? '换一份身份预设' : '给这个角色选一份设定'"
          @click="openBindModal('profile')">{{ boundProfileId ? "更换预设" : "选择预设" }}</button>
  <button class="ghost-btn" v-hint="'新建或修改预设内容'"
          @click="openPresetModal('profile')">编辑预设</button>
  <button v-if="boundProfileId" class="ghost-btn" v-hint="'不再使用「我的设定」'"
          @click="unbindPreset('profile')">解除绑定</button>
</div>
<p v-if="presetError" class="avatar-error">{{ presetError }}</p>
<p v-if="!profilePresets.length" class="hint">还没有预设：点「编辑预设」→「添加预设」新建一条。</p>
<p v-else-if="!boundProfileId" class="hint">未选择 = 不启用：不注入你的身份与外观。</p>
<div class="avatar-pick">
  <span class="avatar xl">
    <img v-if="profileForm.avatar" :src="profileForm.avatar" alt="">
    <template v-else>{{ (profileForm.name || "我").slice(0, 1) }}</template>
  </span>
</div>
<label class="field">名字
  <div class="counted">
    <input :value="profileForm.name" type="text" readonly>
  </div>
</label>
<label class="field">身份
  <div class="counted">
    <textarea :value="profileForm.identity" rows="3" readonly></textarea>
  </div>
</label>
<label class="field">外观
  <div class="counted">
    <textarea :value="profileForm.appearance" rows="3" readonly></textarea>
  </div>
</label>
<p class="hint">「身份」「外观」会进聊天与沉浸模式的提示词；导演模式不用。</p>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  boundProfileId,
  currentPresetLabel,
  presetError,
  profileForm,
  profilePresets,
} = toRefs(store);

const {
  openBindModal,
  openPresetModal,
  unbindPreset,
} = store;
</script>
