<template>
<footer class="inputbar" :class="{'aux-open': auxOpen}" v-if="activeSession">
      <div class="input-inner">
        <div v-if="orphanActive" class="notice">该会话绑定的角色已删除，仅可查看历史记录</div>
        <div v-if="error" class="error">
          <span class="error-text">{{ error }}</span>
          <button v-if="lastFailedUser" class="retry-btn" @click="retryFailed">重试</button>
          <button class="dismiss" @click="error = ''">&times;</button>
        </div>
        <!-- 第一行：辅助按键。左边一排（手机端由 ⋯ 收纳，可横向滚动，以后加键也不会挤坏布局），
             右边"回到最新"钉在行尾、不参与滚动。桌面端没有收纳键，这一排常显。 -->
        <div class="aux-row">
          <div class="aux-scroll">
            <!-- 手机端：背景切换/继续/跳底/情境（沉浸）这些辅助内容收进"⋯"里，桌面断点该按钮隐藏 -->
            <button class="aux-toggle" :class="{on: auxOpen}" v-hint="auxOpen ? '收起辅助操作' : '展开辅助操作'"
                    :aria-label="auxOpen ? '收起辅助操作' : '展开辅助操作'" :aria-pressed="auxOpen" @click="auxOpen = !auxOpen">&#8943;</button>
            <!-- 背景切换与"继续"互斥：前者只在聊天与沉浸两种模式出现，后者只在导演模式出现，
                 所以它们共用这个位置，样式也用同一套（次级按钮）。
                 有关闭键，所以只要有一张背景就出现（单张时翻页键置灰） -->
            <div v-if="showBgBar" class="bg-switch">
              <button type="button" v-hint="'上一张背景'" aria-label="上一张背景" :disabled="bgImages.length < 2" @click="prevBg">‹</button>
              <span class="bg-switch-count">{{ bgIndex + 1 }}/{{ bgImages.length }}</span>
              <button type="button" v-hint="'下一张背景'" aria-label="下一张背景" :disabled="bgImages.length < 2" @click="nextBg">›</button>
              <button type="button" class="bg-close" :class="{off: bgHidden}"
                      v-hint="bgHidden ? '重新显示这个角色的对话背景' : '暂时不显示背景（切会话或刷新后恢复）'"
                      @click="bgHidden = !bgHidden">{{ bgHidden ? "显示背景" : "关闭背景" }}</button>
            </div>
            <button v-if="isDirectorMode" class="continue-btn" :disabled="!canContinue"
                    v-hint="'基于上一条回复继续生成（相当于发送“继续”）'"
                    @click="continueGeneration">继续</button>
            <!-- 隐藏对话：把消息流整块藏起来、只留背景（三个模式都有），方便看背景图/截图 -->
            <button class="aux-btn" v-hint="chatHidden ? '显示对话内容' : '隐藏对话内容，只留背景'"
                    @click="chatHidden = !chatHidden">{{ chatHidden ? "显示对话" : "隐藏对话" }}</button>
          </div>
          <!-- 消息很长、往上翻过之后，一键回到最新：不用一路拖滚动条 -->
          <button class="jump-btn" v-hint="'回到页面底部（最新消息）'" aria-label="回到页面底部（最新消息）" @click="jumpToBottom">↓</button>
        </div>
        <!-- 第二、三行：情境（可选）与话语（必填）上下各占一行，与消息编辑弹窗同一套概念。
             两框都不带标题——靠框内提示（placeholder）说明各自该填什么，省下一行高度。
             每行右侧都留出与发送键同宽的一格（情境那行是空的 .send-spacer），
             所以情境框与话语框左右边界严格对齐；情境只在沉浸模式出现，其它模式只有话语一行。
             手机断点情境行由统一收纳键（⋯）控制显隐：收起来时只留话语框＋发送键
             （见手机断点的 .inputbar:not(.aux-open) .scenario-field 规则） -->
        <div class="input-main">
          <div v-if="isImmersiveMode" class="field-row">
            <div class="input-field scenario-field">
              <div class="counted">
                <textarea
                  v-model="inputScenario"
                  :disabled="orphanActive"
                  rows="2"
                  :maxlength="limits.scenario"
                  placeholder="请输入情境，如动作、场景、心理等"
                  @keydown.enter.exact.prevent="send"
                ></textarea>
                <span class="char-count" :class="{near: isNear(inputScenario, limits.scenario)}">{{ len(inputScenario) }}/{{ limits.scenario }}</span>
              </div>
            </div>
            <span class="send-spacer" aria-hidden="true"></span>
          </div>
          <div class="field-row">
            <div class="input-field">
              <div class="counted">
                <textarea
                  v-model="input"
                  :disabled="orphanActive"
                  rows="2"
                  :maxlength="limits.message"
                  :placeholder="isImmersiveMode ? '请输入话语' : '输入消息，Enter 发送'"
                  @keydown.enter.exact.prevent="send"
                ></textarea>
                <span class="char-count" :class="{near: isNear(input, limits.message)}">{{ len(input) }}/{{ limits.message }}</span>
              </div>
            </div>
            <button v-if="streaming" class="stop-btn" @click="stop">
              <span class="stop-square"></span>停止
            </button>
            <button v-else class="send-btn" :disabled="!canSend" @click="send">发送</button>
          </div>
        </div>
      </div>
    </footer>
</template>

<script setup>
import { ref, toRefs } from "vue";
import { store } from "../store.js";

// 手机端辅助操作（背景切换/继续/情境）的收纳开关：**默认展开**；桌面断点该按钮被 CSS 隐藏，此值无副作用
const auxOpen = ref(true);

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeSession,
  bgHidden,
  bgImages,
  bgIndex,
  canContinue,
  canSend,
  chatHidden,
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
