<template>
<div class="modal-mask" v-if="presetModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal edit-modal preset-modal">
      <h2>编辑预设</h2>
      <!-- 与「载入预设」同一套两栏骨架（左列表 / 右内容）：左边挑要改哪条，右边就是它的字段。
           预设是"另存的一份设定"：这里改的只是这一条，当前使用的设定不受影响；
           删除是不可逆操作，也收在这个弹窗里（面板上不放） -->
      <div class="modal-body preset-split">
        <div class="preset-list">
          <button v-for="p in profilePresets" :key="p.id" class="preset-item"
                  :class="{on: p.id === presetModal.id}"
                  @click="editPickPreset(p.id)">
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
        <div class="avatar-pick">
          <span class="avatar xl">
            <img v-if="presetModal.form.avatar" :src="presetModal.form.avatar" alt="">
            <template v-else>{{ (presetModal.form.name || "预").slice(0, 1) }}</template>
          </span>
          <div class="avatar-pick-actions">
            <label class="ghost-btn file-btn">{{ presetModal.form.avatar ? "更换头像" : "上传头像" }}
              <input type="file" accept="image/*" @change="pickAvatar($event, 'preset')">
            </label>
            <button v-if="presetModal.form.avatar" class="ghost-btn"
                    @click="clearAvatar('preset')">移除头像</button>
          </div>
        </div>
        <p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
        <label class="field">名字
          <div class="counted">
            <input v-model="presetModal.form.name" type="text" :maxlength="limits.user_name"
                   placeholder="下拉里显示的就是这个名字">
            <span class="char-count inline" :class="{near: isNear(presetModal.form.name, limits.user_name)}">{{ len(presetModal.form.name) }}/{{ limits.user_name }}</span>
          </div>
        </label>
        <label class="field">身份
          <div class="counted">
            <textarea v-model="presetModal.form.identity" rows="3" :maxlength="limits.identity"
                      placeholder="你是谁：如「被卷入事件的见习侦探」"></textarea>
            <span class="char-count" :class="{near: isNear(presetModal.form.identity, limits.identity)}">{{ len(presetModal.form.identity) }}/{{ limits.identity }}</span>
          </div>
        </label>
        <label class="field">外观
          <div class="counted">
            <textarea v-model="presetModal.form.appearance" rows="3" :maxlength="limits.user_appearance"
                      placeholder="年龄、身形、衣着等"></textarea>
            <span class="char-count" :class="{near: isNear(presetModal.form.appearance, limits.user_appearance)}">{{ len(presetModal.form.appearance) }}/{{ limits.user_appearance }}</span>
          </div>
        </label>
        <p v-if="presetModal.saveError" class="avatar-error">{{ presetModal.saveError }}</p>
        <!-- 绑定只能在角色那侧改：一份预设可以给多个角色用，所以"哪些角色用它"
             是角色的属性而不是预设的属性，这里只显示 -->
        <p class="hint">绑定角色：{{ presetBindLabel(picked) }}。在「编辑角色」里选这个角色用哪份预设。</p>
        </div>
      </div>
      <div class="modal-actions">
        <button class="danger-btn" v-hint="'删除这条预设（当前使用的设定不受影响）'"
                @click="deletePresetInModal">删除这条预设</button>
        <button class="ghost-btn" @click="closePresetModal">取消</button>
        <button class="primary-btn" :disabled="!presetModal.form.name.trim()"
                @click="savePresetModal">保存</button>
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
  avatarError,
  limits,
  presetModal,
  profilePresets,
} = toRefs(store);

// 正在编辑的这条（只用来显示它绑定了哪些角色）
const picked = computed(() =>
  store.profilePresets.find((p) => p.id === store.presetModal.id) || null
);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  clearAvatar,
  closePresetModal,
  deletePresetInModal,
  editPickPreset,
  isNear,
  len,
  pickAvatar,
  presetBindLabel,
  savePresetModal,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(closePresetModal);
</script>
