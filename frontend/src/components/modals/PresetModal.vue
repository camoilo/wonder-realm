<template>
<div class="modal-mask" v-if="presetModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal edit-modal preset-modal">
      <h2>编辑预设</h2>
      <!-- 预设是"另存的一份设定"：这里改的只是这一条，当前使用的设定不受影响 -->
      <div class="modal-body">
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
      </div>
      <div class="modal-actions">
        <button class="ghost-btn" @click="closePresetModal">取消</button>
        <button class="primary-btn" :disabled="!presetModal.form.name.trim()"
                @click="savePresetModal">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  avatarError,
  limits,
  presetModal,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  clearAvatar,
  closePresetModal,
  isNear,
  len,
  pickAvatar,
  savePresetModal,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(closePresetModal);
</script>
