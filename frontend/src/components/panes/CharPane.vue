<template>
<div class="avatar-pick">
  <span class="avatar xl">
    <img v-if="charForm.avatar" :src="charForm.avatar" alt="">
    <template v-else>{{ (charForm.name || "?").slice(0, 1) }}</template>
  </span>
  <div class="avatar-pick-actions">
    <label class="ghost-btn file-btn">{{ charForm.avatar ? "更换头像" : "上传头像" }}
      <input type="file" accept="image/*" @change="pickAvatar($event, 'panel')">
    </label>
    <button v-if="charForm.avatar" class="ghost-btn" @click="clearAvatar('panel')">移除头像</button>
  </div>
</div>
<p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
<div class="bg-pick">
  <div class="bg-pick-head">
    <span class="field-label">对话背景</span>
    <span class="hint">{{ (charForm.backgrounds || []).length }} / {{ bgMax }}</span>
  </div>
  <div class="bg-thumbs">
    <div v-for="(bg, i) in charForm.backgrounds" :key="i" class="bg-thumb"
         :class="{ dragging: bgDragging('panel', i), over: bgDropTarget('panel', i) }"
         draggable="true" v-hint="'拖动可调整顺序'"
         @dragstart="bgDragStart($event, 'panel', i)"
         @dragover.prevent="bgDragOver($event, 'panel', i)"
         @drop.prevent="bgDrop($event, 'panel', i)"
         @dragend="bgDragEnd">
      <img :src="bg" alt="" draggable="false">
      <span class="bg-num">{{ i + 1 }}</span>
      <button type="button" class="bg-del" v-hint="'移除这张'" aria-label="移除这张" @click="removeBackground('panel', i)">×</button>
      <div class="bg-move">
        <button type="button" :disabled="i === 0" v-hint="'前移'" aria-label="前移"
                @click="moveBackground('panel', i, i - 1)">‹</button>
        <button type="button" :disabled="i === (charForm.backgrounds || []).length - 1" v-hint="'后移'" aria-label="后移"
                @click="moveBackground('panel', i, i + 1)">›</button>
      </div>
    </div>
    <label v-if="(charForm.backgrounds || []).length < bgMax"
           class="bg-add" :class="{disabled: bgBusy}">
      {{ bgBusy ? "处理中…" : "＋" }}
      <input type="file" accept="image/*" multiple :disabled="bgBusy"
             @change="addBackgrounds($event, 'panel')">
    </label>
  </div>
  <p v-if="bgError" class="avatar-error">{{ bgError }}</p>
</div>
<label class="field">姓名
  <div class="counted">
    <input v-model="charForm.name" type="text" :maxlength="limits.name">
    <span class="char-count inline" :class="{near: isNear(charForm.name, limits.name)}">{{ len(charForm.name) }}/{{ limits.name }}</span>
  </div>
</label>
<label class="field">外观
  <div class="counted">
    <textarea v-model="charForm.appearance" rows="3" :maxlength="limits.appearance"
              placeholder="年龄、身形、衣着、标志性特征"></textarea>
    <span class="char-count" :class="{near: isNear(charForm.appearance, limits.appearance)}">{{ len(charForm.appearance) }}/{{ limits.appearance }}</span>
  </div>
</label>
<template v-if="!charLocked">
  <label class="field">性格
    <div class="counted">
      <textarea v-model="charForm.personality" rows="3" :maxlength="limits.personality"></textarea>
      <span class="char-count" :class="{near: isNear(charForm.personality, limits.personality)}">{{ len(charForm.personality) }}/{{ limits.personality }}</span>
    </div>
  </label>
  <label class="field">语言风格
    <div class="counted">
      <textarea v-model="charForm.speech_style" rows="3" :maxlength="limits.speech_style"
                placeholder="口癖、语气、用词习惯"></textarea>
      <span class="char-count" :class="{near: isNear(charForm.speech_style, limits.speech_style)}">{{ len(charForm.speech_style) }}/{{ limits.speech_style }}</span>
    </div>
  </label>
  <label class="field">背景故事
    <div class="counted">
      <textarea v-model="charForm.backstory" rows="4" :maxlength="limits.backstory"></textarea>
      <span class="char-count" :class="{near: isNear(charForm.backstory, limits.backstory)}">{{ len(charForm.backstory) }}/{{ limits.backstory }}</span>
    </div>
  </label>
</template>
<div v-else class="locked-box">
  <div class="locked-title">🔒 性格 / 语言风格 / 背景故事 已锁定</div>
  <p class="hint">这三项照常参与生成，但不会显示，可以在对话中慢慢了解。</p>
  <button class="ghost-btn" @click="unlockCharacter('panel')">公开角色设定</button>
</div>
<!-- 附加属性定义（见 DEVELOPMENT §2.6）：锁定的角色也能有——锁的是那三项隐藏设定 -->
<AttrEditor :form="charForm" />
</template>

<script setup>
import AttrEditor from "../AttrEditor.vue";
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  avatarError,
  bgBusy,
  bgError,
  bgMax,
  charForm,
  charLocked,
  limits,
} = toRefs(store);

const {
  addBackgrounds,
  bgDragEnd,
  bgDragOver,
  bgDragStart,
  bgDragging,
  bgDrop,
  bgDropTarget,
  clearAvatar,
  isNear,
  len,
  moveBackground,
  pickAvatar,
  removeBackground,
  unlockCharacter,
} = store;
</script>
