<template>
<div class="modal-mask" v-if="presetModal.visible"
     @mousedown="onMaskDown" @mouseup="onMaskUp" @click="onMaskClick">
    <div class="modal edit-modal preset-modal">
      <h2>{{ kind.editTitle }}</h2>
      <!-- 与「载入预设」同一套两栏骨架（左列表 / 右内容）：左边挑要改哪条，右边就是它的字段。
           预设是"另存的一份"：这里改的只是这一条，当前生效的那份不受影响；
           删除是不可逆操作，也收在这个弹窗里（面板上不放）。
           "我的设定"与"世界设定"共用这一对弹窗，右边字段按 kind 分支。 -->
      <div class="modal-body preset-split">
        <div class="preset-list">
          <!-- 「添加预设」= 先给一份**空白且还没落库**的表单（id=null），必须命名才保存得下去。
               这是新建预设的唯一入口（面板那两页已经不放「存为预设」了） -->
          <button class="preset-item preset-add" v-hint="'新建一条空白预设（要填名字才存得下）'"
                  @click="startNewPreset(presetModal.kind)">
            <span class="preset-item-text"><span class="preset-item-name">＋ 添加预设</span></span>
          </button>
          <button v-for="p in presets" :key="p.id" class="preset-item"
                  :class="{on: p.id === presetModal.id}"
                  @click="editPickPreset(p.id)">
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
        <template v-if="isProfile">
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
        </template>
        <template v-else>
        <label class="field">世界名称
          <div class="counted">
            <input v-model="presetModal.form.name" type="text" :maxlength="limits.world_name"
                   placeholder="列表里显示的就是这个名字，不发给模型">
            <span class="char-count inline" :class="{near: isNear(presetModal.form.name, limits.world_name)}">{{ len(presetModal.form.name) }}/{{ limits.world_name }}</span>
          </div>
        </label>
        <label class="field">描述
          <div class="counted">
            <textarea v-model="presetModal.form.description" rows="4" :maxlength="limits.world_description"
                      placeholder="这个世界的详细信息：地理、时代、势力、氛围…"></textarea>
            <span class="char-count" :class="{near: isNear(presetModal.form.description, limits.world_description)}">{{ len(presetModal.form.description) }}/{{ limits.world_description }}</span>
          </div>
        </label>
        <label class="field">规则
          <div class="counted">
            <textarea v-model="presetModal.form.rules" rows="4" :maxlength="limits.world_rules"
                      placeholder="独属于这个世界的规则：力量体系、禁忌、铁律…"></textarea>
            <span class="char-count" :class="{near: isNear(presetModal.form.rules, limits.world_rules)}">{{ len(presetModal.form.rules) }}/{{ limits.world_rules }}</span>
          </div>
        </label>
        <TermEditor :form="presetModal.form" />
        </template>
        <p v-if="presetModal.saveError" class="avatar-error">{{ presetModal.saveError }}</p>
        <!-- 一份预设可以给多个角色用，所以"哪些角色用它"是角色的属性而不是预设的属性，这里只显示 -->
        <p class="hint">绑定的角色：{{ presetBindLabel(picked) }}。选/解除预设在那两页上做。</p>
        </div>
      </div>
      <div class="modal-actions">
        <button class="danger-btn" :disabled="!presetModal.id"
                v-hint="presetModal.id ? '删除这条预设' : '还没保存，没得删'"
                @click="deletePresetInModal">删除这条预设</button>
        <button class="ghost-btn" @click="closePresetModal">取消</button>
        <button class="primary-btn" :disabled="!presetModal.form.name.trim()"
                @click="savePresetModal">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import TermEditor from "../TermEditor.vue";
import { computed, toRefs } from "vue";
import { store } from "../../store.js";
import { PRESET_KINDS } from "../../store/helpers.js";
import { useMaskClose } from "../../composables/maskClose.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  avatarError,
  limits,
  presetModal,
} = toRefs(store);

// 这次编辑的是哪种预设：标题、列表、右侧字段都由它决定
const kind = computed(() => PRESET_KINDS[store.presetModal.kind] || PRESET_KINDS.profile);
const isProfile = computed(() => store.presetModal.kind === "profile");
const presets = computed(() => store[kind.value.listKey]);
// 正在编辑的这条（只用来显示它绑定了哪些角色）
const picked = computed(() =>
  presets.value.find((p) => p.id === store.presetModal.id) || null
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
  startNewPreset,
} = store;

// 点窗口外 = 取消（判据是"按下"落在遮罩上，见 composables/maskClose.js）
const { onMaskDown, onMaskUp, onMaskClick } = useMaskClose(closePresetModal);
</script>
