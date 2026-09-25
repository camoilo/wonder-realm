<template>
<!-- 世界设定（见 DEVELOPMENT §2.4）：**这一页只读** —— 显示的是选中的那条世界预设的内容。
     改内容去「编辑预设」，启用/换一份去「选择预设」；未选择就是不启用（不注入世界设定）。
     绑定在角色侧（聊天/沉浸）或会话侧（导演模式），所以这一页对两种模式是同一套操作。 -->
<div class="preset-current">当前世界预设：<b>{{ currentWorldPresetLabel }}</b></div>
<div class="preset-row preset-actions">
  <button class="ghost-btn" :disabled="!worldPresets.length"
          v-hint="boundWorldId ? '换一份世界预设' : '给这个角色/会话选一份世界'"
          @click="openBindModal('world')">{{ boundWorldId ? "更换预设" : "选择预设" }}</button>
  <button class="ghost-btn" v-hint="'新建或修改预设内容'"
          @click="openPresetModal('world')">编辑预设</button>
  <button v-if="boundWorldId" class="ghost-btn" v-hint="'不再使用世界设定'"
          @click="unbindPreset('world')">解除绑定</button>
</div>
<p v-if="presetError" class="avatar-error">{{ presetError }}</p>
<p v-if="!worldPresets.length" class="hint">还没有世界预设：点「编辑预设」→「添加预设」新建一条。</p>
<p v-else-if="!boundWorldId" class="hint">未选择 = 不启用：不注入世界设定。</p>
<label class="field">世界名称
  <div class="counted">
    <input :value="worldForm.name" type="text" readonly>
  </div>
</label>
<label class="field">描述
  <div class="counted">
    <textarea :value="worldForm.description" rows="4" readonly></textarea>
  </div>
</label>
<label class="field">规则
  <div class="counted">
    <textarea :value="worldForm.rules" rows="4" readonly></textarea>
  </div>
</label>
<TermEditor :form="worldForm" readonly />
<p class="hint">名称只给自己看；描述、规则、词库会进提示词。</p>
</template>

<script setup>
import TermEditor from "../TermEditor.vue";
import { toRefs } from "vue";
import { store } from "../../store.js";

const {
  boundWorldId,
  currentWorldPresetLabel,
  presetError,
  worldForm,
  worldPresets,
} = toRefs(store);

const {
  openBindModal,
  openPresetModal,
  unbindPreset,
} = store;
</script>
