<template>
<div class="modal-mask" v-if="charModal.visible" @click.self="charModal.visible = false">
    <div class="modal char-modal">
      <h2>{{ charModal.editingId ? "编辑角色" : "新建角色" }}</h2>
      <!-- 字段区：弹窗里唯一可滚动的部分（操作行在它外面，始终可见） -->
      <div class="modal-body">
        <!-- 让模型生成：只在新建时提供。编辑已有角色时，设定已经定了，再生成一次
             等于把角色换掉，不是"编辑"该做的事 -->
        <div v-if="!charModal.editingId" class="gen-box">
          <div class="gen-head">
            <span class="field-label">让模型生成角色</span>
            <span class="hint">用当前选中的模型，只出文字设定（不含头像与背景）</span>
          </div>
          <div class="counted">
            <input v-model="charModal.gen.hint" type="text" :maxlength="limits.hint"
                   placeholder="想要的设定，可留空让模型自由发挥（如：古风江湖的女剑客）">
            <span class="char-count inline" :class="{near: isNear(charModal.gen.hint, limits.hint)}">{{ len(charModal.gen.hint) }}/{{ limits.hint }}</span>
          </div>
          <div class="radio-row">
            <label class="radio-item" :class="{on: charModal.gen.mode === 'open'}">
              <input type="radio" value="open" v-model="charModal.gen.mode">开放模式
            </label>
            <label class="radio-item" :class="{on: charModal.gen.mode === 'explore'}">
              <input type="radio" value="explore" v-model="charModal.gen.mode">探索模式
            </label>
          </div>
          <p class="hint">{{ charModal.gen.mode === "open"
            ? "开放模式：生成的设定全部直接展示，可以随意修改。"
            : "探索模式：只公开姓名与外观，性格 / 语言风格 / 背景故事会上锁——它们照常参与生成，但不会显示，可以在对话里慢慢了解。" }}</p>
          <p class="hint">跟着顶栏的思考开关走：开着思考会明显更慢（常见一分钟以上），嫌久可以先关掉再生成。</p>
          <button class="ghost-btn" :disabled="charModal.gen.busy" @click="generateCharacter">
            {{ charModal.gen.busy ? "生成中…" : (charModal.gen.draftId ? "换一个" : "生成角色") }}
          </button>
          <p v-if="charModal.gen.error" class="avatar-error">{{ charModal.gen.error }}</p>
        </div>
        <div class="avatar-pick">
          <span class="avatar xl">
            <img v-if="charModal.form.avatar" :src="charModal.form.avatar" alt="">
            <template v-else>{{ (charModal.form.name || "?").slice(0, 1) }}</template>
          </span>
          <div class="avatar-pick-actions">
            <label class="ghost-btn file-btn">{{ charModal.form.avatar ? "更换头像" : "上传头像" }}
              <input type="file" accept="image/*" @change="pickAvatar($event, 'modal')">
            </label>
            <button v-if="charModal.form.avatar" class="ghost-btn" @click="clearAvatar('modal')">移除头像</button>
          </div>
        </div>
        <p v-if="avatarError" class="avatar-error">{{ avatarError }}</p>
        <div class="bg-pick">
          <div class="bg-pick-head">
            <span class="field-label">对话背景</span>
            <span class="hint">{{ (charModal.form.backgrounds || []).length }} / {{ bgMax }}</span>
          </div>
          <div class="bg-thumbs">
            <div v-for="(bg, i) in charModal.form.backgrounds" :key="i" class="bg-thumb"
                 :class="{ dragging: bgDragging('modal', i), over: bgDropTarget('modal', i) }"
                 draggable="true" title="拖动可调整顺序"
                 @dragstart="bgDragStart($event, 'modal', i)"
                 @dragover.prevent="bgDragOver($event, 'modal', i)"
                 @drop.prevent="bgDrop($event, 'modal', i)"
                 @dragend="bgDragEnd">
              <img :src="bg" alt="" draggable="false">
              <span class="bg-num">{{ i + 1 }}</span>
              <button type="button" class="bg-del" title="移除这张" @click="removeBackground('modal', i)">×</button>
              <div class="bg-move">
                <button type="button" :disabled="i === 0" title="前移"
                        @click="moveBackground('modal', i, i - 1)">‹</button>
                <button type="button" :disabled="i === (charModal.form.backgrounds || []).length - 1" title="后移"
                        @click="moveBackground('modal', i, i + 1)">›</button>
              </div>
            </div>
            <label v-if="(charModal.form.backgrounds || []).length < bgMax"
                   class="bg-add" :class="{disabled: bgBusy}">
              {{ bgBusy ? "处理中…" : "＋" }}
              <input type="file" accept="image/*" multiple :disabled="bgBusy"
                     @change="addBackgrounds($event, 'modal')">
            </label>
          </div>
          <p v-if="bgError" class="avatar-error">{{ bgError }}</p>
        </div>
        <label class="field">姓名 *
          <div class="counted">
            <input v-model="charModal.form.name" type="text" :maxlength="limits.name">
            <span class="char-count inline" :class="{near: isNear(charModal.form.name, limits.name)}">{{ len(charModal.form.name) }}/{{ limits.name }}</span>
          </div>
        </label>
        <label class="field">外观
          <div class="counted">
            <textarea v-model="charModal.form.appearance" rows="4" :maxlength="limits.appearance"
                      placeholder="年龄、身形、衣着、标志性特征"></textarea>
            <span class="char-count" :class="{near: isNear(charModal.form.appearance, limits.appearance)}">{{ len(charModal.form.appearance) }}/{{ limits.appearance }}</span>
          </div>
        </label>
        <template v-if="!charModal.locked">
          <label class="field">性格
            <div class="counted">
              <textarea v-model="charModal.form.personality" rows="4" :maxlength="limits.personality"></textarea>
              <span class="char-count" :class="{near: isNear(charModal.form.personality, limits.personality)}">{{ len(charModal.form.personality) }}/{{ limits.personality }}</span>
            </div>
          </label>
          <label class="field">语言风格
            <div class="counted">
              <textarea v-model="charModal.form.speech_style" rows="4" :maxlength="limits.speech_style"
                        placeholder="口癖、语气、用词习惯"></textarea>
              <span class="char-count" :class="{near: isNear(charModal.form.speech_style, limits.speech_style)}">{{ len(charModal.form.speech_style) }}/{{ limits.speech_style }}</span>
            </div>
          </label>
          <label class="field">背景故事
            <div class="counted">
              <textarea class="grow-lg" v-model="charModal.form.backstory" rows="6"
                        :maxlength="limits.backstory"></textarea>
              <span class="char-count" :class="{near: isNear(charModal.form.backstory, limits.backstory)}">{{ len(charModal.form.backstory) }}/{{ limits.backstory }}</span>
            </div>
          </label>
        </template>
        <div v-else class="locked-box">
          <div class="locked-title">🔒 性格 / 语言风格 / 背景故事 已锁定</div>
          <p class="hint">这三项照常参与生成，但不会显示，可以在对话中慢慢了解。</p>
          <button v-if="charModal.editingId" class="ghost-btn"
                  @click="unlockCharacter('modal')">公开角色设定</button>
          <p v-else class="hint">保存后可在右侧面板或这里点「公开角色设定」永久解锁。</p>
        </div>
      </div>
      <!-- 操作行钉在弹窗底部：它在 .modal-body（唯一可滚动区）之外，内容再长也不会
           跟着滚走。保存失败的那行提示也放在这里，与按钮一起始终可见 -->
      <p v-if="charModal.saveError" class="avatar-error">{{ charModal.saveError }}</p>
      <div class="modal-actions">
        <button v-if="charModal.editingId" class="danger-btn" @click="removeCharacterFromModal">删除角色</button>
        <span class="spacer"></span>
        <button class="ghost-btn" @click="charModal.visible = false">取消</button>
        <button class="primary-btn" :disabled="!charModal.form.name.trim()" @click="saveCharacterModal">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  avatarError,
  bgBusy,
  bgError,
  bgMax,
  charModal,
  limits,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  addBackgrounds,
  bgDragEnd,
  bgDragOver,
  bgDragStart,
  bgDragging,
  bgDrop,
  bgDropTarget,
  clearAvatar,
  generateCharacter,
  isNear,
  len,
  moveBackground,
  pickAvatar,
  removeBackground,
  removeCharacterFromModal,
  saveCharacterModal,
  unlockCharacter,
} = store;
</script>
