<template>
<!-- 预设是"另存的一份设定"，与下面这份表单（当前使用的设定）分开：
     面板只显示"当前预设是谁"，挑选、看详情、编辑都在弹窗里做——
     预设名字可能重复，光看下拉里一行字分不清，弹窗里能一眼看到头像与身份/外观。
     删除也收在"编辑预设"弹窗里，面板上不放不可逆的操作。 -->
<div class="preset-current">当前预设：<b>{{ currentPresetLabel }}</b></div>
<div class="preset-row preset-actions">
  <button class="ghost-btn" :disabled="!profilePresets.length"
          v-hint="'在弹窗里挑一条预设，看清详情后载入（立即生效，覆盖当前使用的设定）'"
          @click="openLoadModal('profile')">载入预设…</button>
  <button class="ghost-btn" :disabled="!profilePresets.length"
          v-hint="'在弹窗里选一条预设来改（含头像），删除也在这里'"
          @click="openPresetModal('profile')">编辑预设…</button>
  <button class="ghost-btn" :disabled="!profileForm.name.trim()"
          v-hint="'把下面的表单另存成一条新预设'"
          @click="savePreset('profile')">存为预设</button>
</div>
<p v-if="presetError" class="avatar-error">{{ presetError }}</p>
<p v-if="!profilePresets.length" class="hint">
  还没有预设：填好下面几项后点「存为预设」，以后就能在这里挑一条载入（含头像）。
</p>
<div class="avatar-pick">
  <span class="avatar xl">
    <img v-if="profileForm.avatar" :src="profileForm.avatar" alt="">
    <template v-else>{{ (profileForm.name || "我").slice(0, 1) }}</template>
  </span>
  <div class="avatar-pick-actions">
    <label class="ghost-btn file-btn">{{ profileForm.avatar ? "更换头像" : "上传头像" }}
      <input type="file" accept="image/*" @change="pickAvatar($event, 'profile')">
    </label>
    <button v-if="profileForm.avatar" class="ghost-btn" @click="clearAvatar('profile')">移除头像</button>
  </div>
</div>
<p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
<label class="field">名字
  <div class="counted">
    <input v-model="profileForm.name" type="text" :maxlength="limits.user_name"
           placeholder="角色对你的称呼">
    <span class="char-count inline" :class="{near: isNear(profileForm.name, limits.user_name)}">{{ len(profileForm.name) }}/{{ limits.user_name }}</span>
  </div>
</label>
<label class="field">身份
  <div class="counted">
    <textarea v-model="profileForm.identity" rows="3" :maxlength="limits.identity"
              placeholder="你是谁：如「被卷入事件的见习侦探」"></textarea>
    <span class="char-count" :class="{near: isNear(profileForm.identity, limits.identity)}">{{ len(profileForm.identity) }}/{{ limits.identity }}</span>
  </div>
</label>
<label class="field">外观
  <div class="counted">
    <textarea v-model="profileForm.appearance" rows="3" :maxlength="limits.user_appearance"
              placeholder="年龄、身形、衣着等"></textarea>
    <span class="char-count" :class="{near: isNear(profileForm.appearance, limits.user_appearance)}">{{ len(profileForm.appearance) }}/{{ limits.user_appearance }}</span>
  </div>
</label>
<p class="hint">「身份」与「外观」会写进聊天与沉浸两种模式的提示词，让角色知道你是谁；导演模式不使用这些内容。</p>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  avatarError,
  currentPresetLabel,
  limits,
  presetError,
  profileForm,
  profilePresets,
} = toRefs(store);

const {
  clearAvatar,
  isNear,
  len,
  openLoadModal,
  openPresetModal,
  pickAvatar,
  savePreset,
} = store;
</script>
