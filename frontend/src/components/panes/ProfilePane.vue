<template>
<!-- 预设是"另存的一份设定"，与当前配置（下面这份表单）彻底分开：
     下拉只挑"要操作哪条预设"，选它不碰表单；
     「载入」把预设复制进下面的表单（还要点底部"保存当前配置"才生效）；
     「存为预设」把当前表单另存成一条新预设；
     「编辑预设」在弹窗里改选中的那一条（含头像），改完列表立刻更新——都不影响当前配置。
     四个键常驻、不适用时置灰：控件不按状态出现/消失，免得按钮跳来跳去 -->
<div class="preset-row">
  <select class="preset-select" v-model="presetPick">
    <option value="">选择预设…</option>
    <option v-for="p in profilePresets" :key="p.id" :value="p.id">
      {{ p.name }}{{ p.identity ? " · " + p.identity : "" }}
    </option>
  </select>
</div>
<div class="preset-row preset-actions">
  <button class="ghost-btn" :disabled="!presetPick"
          v-hint="'把这条预设复制进下面的表单（这时还没生效，点底部「保存当前配置」才写入）'"
          @click="loadPreset">载入</button>
  <button class="ghost-btn" :disabled="!profileForm.name.trim()"
          v-hint="'把下面的表单另存成一条新预设'"
          @click="savePreset">存为预设</button>
  <button class="ghost-btn" :disabled="!presetPick"
          v-hint="'在弹窗里改选中的这条预设（含头像），不影响当前使用的设定'"
          @click="openPresetModal">编辑预设</button>
  <button class="ghost-btn" :disabled="!presetPick"
          v-hint="'删除选中的这条预设'"
          @click="removePreset">删除预设</button>
</div>
<p v-if="presetError" class="avatar-error">{{ presetError }}</p>
<p v-if="!profilePresets.length" class="hint">
  还没有预设：填好下面几项后点「存为预设」，以后就能从下拉里选一条「载入」（含头像）。
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
  limits,
  presetError,
  presetPick,
  profileForm,
  profilePresets,
} = toRefs(store);

const {
  clearAvatar,
  isNear,
  len,
  loadPreset,
  openPresetModal,
  pickAvatar,
  removePreset,
  savePreset,
} = store;
</script>
