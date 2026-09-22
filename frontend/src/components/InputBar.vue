<template>
<footer class="inputbar" v-if="activeSession">
      <div class="input-inner">
        <div v-if="orphanActive" class="notice">该会话绑定的角色已删除，仅可查看历史记录</div>
        <div v-if="error" class="error">
          <span class="error-text">{{ error }}</span>
          <button v-if="lastFailedUser" class="retry-btn" @click="retryFailed">重试</button>
          <button class="dismiss" @click="error = ''">&times;</button>
        </div>
        <div class="input-row">
          <!-- 沉浸模式：情境（可选）与话语（必选）分两栏并排，与消息编辑弹窗同一套概念。
               情境那栏只在沉浸模式出现，其它模式保持原来的单框 -->
          <div v-if="isImmersiveMode" class="input-field scenario-field">
            <span class="input-field-label">情境说明（可选）</span>
            <div class="counted">
              <textarea
                v-model="inputScenario"
                :disabled="orphanActive"
                rows="3"
                :maxlength="limits.scenario"
                placeholder="场景、动作、心理等，可留空"
                @keydown.enter.exact.prevent="send"
              ></textarea>
              <span class="char-count" :class="{near: isNear(inputScenario, limits.scenario)}">{{ len(inputScenario) }}/{{ limits.scenario }}</span>
            </div>
          </div>
          <div class="input-field">
            <span v-if="isImmersiveMode" class="input-field-label">话语</span>
            <div class="counted">
              <textarea
                v-model="input"
                :disabled="orphanActive"
                rows="3"
                :maxlength="limits.message"
                :placeholder="isImmersiveMode ? '这一幕里说出的话（必填）' : '输入消息，Enter 发送（Shift+Enter 换行）'"
                @keydown.enter.exact.prevent="send"
              ></textarea>
              <span class="char-count" :class="{near: isNear(input, limits.message)}">{{ len(input) }}/{{ limits.message }}</span>
            </div>
          </div>
          <div class="send-col">
            <!-- 背景切换与"继续"互斥：前者只在聊天与沉浸两种模式出现，后者只在导演模式出现，
                 所以它们共用发送键上方这个位置，样式也用同一套（次级按钮）。
                 有关闭键，所以只要有一张背景就出现（单张时翻页键置灰） -->
            <div v-if="showBgBar" class="bg-switch">
              <button type="button" title="上一张背景" :disabled="bgImages.length < 2" @click="prevBg">‹</button>
              <span class="bg-switch-count">{{ bgIndex + 1 }}/{{ bgImages.length }}</span>
              <button type="button" title="下一张背景" :disabled="bgImages.length < 2" @click="nextBg">›</button>
              <button type="button" class="bg-close" :class="{off: bgHidden}"
                      :title="bgHidden ? '重新显示这个角色的对话背景' : '暂时不显示背景（切会话或刷新后恢复）'"
                      @click="bgHidden = !bgHidden">{{ bgHidden ? "显示背景" : "关闭背景" }}</button>
            </div>
            <button v-if="isDirectorMode" class="continue-btn" :disabled="!canContinue"
                    title="基于上一条回复继续生成（相当于发送“继续”）"
                    @click="continueGeneration">继续</button>
            <div class="send-row">
              <button v-if="streaming" class="stop-btn" @click="stop">
                <span class="stop-square"></span>停止
              </button>
              <button v-else class="send-btn" :disabled="!input.trim() || orphanActive" @click="send">发送</button>
              <!-- 消息很长、往上翻过之后，一键回到最新：不用一路拖滚动条 -->
              <button class="jump-btn" title="回到页面底部（最新消息）" @click="jumpToBottom">↓</button>
            </div>
          </div>
        </div>
      </div>
    </footer>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  bgHidden,
  bgImages,
  bgIndex,
  canContinue,
  error,
  input,
  inputScenario,
  isDirectorMode,
  isImmersiveMode,
  lastFailedUser,
  limits,
  orphanActive,
  showBgBar,
  streaming,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  continueGeneration,
  isNear,
  jumpToBottom,
  len,
  nextBg,
  prevBg,
  retryFailed,
  send,
  stop,
} = store;
</script>
