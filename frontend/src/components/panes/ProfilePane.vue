<template>
<!-- 预设是"另存的一份设定"，与当前配置完全分开：
     下拉只挑"要操作哪条预设"，不碰表单（所以选来选去不会冒出"未保存"）；
     要拿来用就点「载入」（只填表单，仍走底部"保存当前配置"才真正生效）；
     选中某条后，存按钮从「存为预设」变成「保存预设」（覆盖这一条） -->
<div class="preset-row">
  <select class="preset-select" v-model="presetPick">
    <option value="">选择预设…</option>
    <option v-for="p in profilePresets" :key="p.id" :value="p.id">
      {{ p.name }}{{ p.identity ? " · " + p.identity : "" }}
    </option>
  </select>
  <button v-if="presetPick" class="ghost-btn"
          v-hint="'把这条预设填进下面的表单（这时还没生效，点底部「保存当前配置」才写入）'"
          @click="loadPreset">载入</button>
  <button class="ghost-btn" :disabled="!profileForm.name.trim()"
          v-hint="presetPick ? '把当前表单覆盖保存到选中的这条预设' : '把当前这几项存成一条新预设，之后可以一键载入'"
          @click="savePreset">{{ presetPick ? "保存预设" : "存为预设" }}</button>
  <button v-if="presetPick" class="ghost-btn" v-hint="'删除选中的这条预设'"
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
  pickAvatar,
  removePreset,
  savePreset,
} = store;
</script>
