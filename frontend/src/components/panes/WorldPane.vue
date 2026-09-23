<template>
<!-- 世界设定与"我的设定"同一套模型：id=1 是当前世界，预设是"另存的一份"（见 DEVELOPMENT §2.4）。
     面板只显示"当前世界预设是谁"，挑选 / 看详情 / 编辑 / 删除都在弹窗里做。 -->
<div class="preset-current">当前世界预设：<b>{{ currentWorldPresetLabel }}</b></div>
<div class="preset-row preset-actions">
  <button class="ghost-btn" :disabled="!worldPresets.length"
          v-hint="'在弹窗里挑一条世界预设，看清详情后载入（立即生效，覆盖当前世界）'"
          @click="openLoadModal('world')">载入预设…</button>
  <button class="ghost-btn" :disabled="!worldPresets.length"
          v-hint="'在弹窗里选一条世界预设来改，删除也在这里'"
          @click="openPresetModal('world')">编辑预设…</button>
  <button class="ghost-btn" :disabled="!worldForm.name.trim()"
          v-hint="'把下面的世界另存成一条新预设'"
          @click="savePreset('world')">存为预设</button>
</div>
<p v-if="presetError" class="avatar-error">{{ presetError }}</p>
<p v-if="!worldPresets.length" class="hint">
  还没有世界预设：填好下面几项后点「存为预设」，之后就能给角色或导演会话各选一份世界。
</p>
<!-- 导演模式没有角色，世界只能挂在会话上（见 §2.4 世界设定）：这一行就是改它的地方 -->
<label v-if="isDirectorMode" class="field">
  本会话的世界预设
  <select :value="activeSession && activeSession.world_id ? String(activeSession.world_id) : ''"
          @change="setSessionWorld($event.target.value ? Number($event.target.value) : null)">
    <option value="">不用世界</option>
    <option v-for="p in worldPresets" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
  </select>
  <span class="hint">导演会话各带一份世界；「不用世界」表示这个会话不注入世界设定。</span>
</label>
<label class="field">世界名称
  <div class="counted">
    <input v-model="worldForm.name" type="text" :maxlength="limits.world_name"
           placeholder="只用于自己辨认，不发给模型">
    <span class="char-count inline"
          :class="{near: isNear(worldForm.name, limits.world_name)}">{{ len(worldForm.name) }}/{{ limits.world_name }}</span>
  </div>
</label>
<label class="field">描述
  <div class="counted">
    <textarea v-model="worldForm.description" rows="4" :maxlength="limits.world_description"
              placeholder="这个世界的详细信息：地理、时代、势力、氛围…"></textarea>
    <span class="char-count"
          :class="{near: isNear(worldForm.description, limits.world_description)}">{{ len(worldForm.description) }}/{{ limits.world_description }}</span>
  </div>
</label>
<label class="field">规则
  <div class="counted">
    <textarea v-model="worldForm.rules" rows="4" :maxlength="limits.world_rules"
              placeholder="独属于这个世界的规则：力量体系、禁忌、铁律…"></textarea>
    <span class="char-count"
          :class="{near: isNear(worldForm.rules, limits.world_rules)}">{{ len(worldForm.rules) }}/{{ limits.world_rules }}</span>
  </div>
</label>
<TermEditor :form="worldForm" />
<p class="hint">名称只给自己看；描述、规则、词库会写进三种模式的提示词（在角色设定之前）。</p>
</template>

<script setup>
import TermEditor from "../TermEditor.vue";
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  activeSession,
  currentWorldPresetLabel,
  isDirectorMode,
  limits,
  presetError,
  worldForm,
  worldPresets,
} = toRefs(store);

const {
  isNear,
  len,
  openLoadModal,
  openPresetModal,
  savePreset,
  setSessionWorld,
} = store;
</script>
