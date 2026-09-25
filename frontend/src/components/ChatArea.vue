<template>
<div class="chat-area">
      <!-- 背景层放在滚动容器外面，这样滚动消息时背景是静止的 -->
      <div v-if="chatBgUrl" class="chat-bg" :style="{ backgroundImage: `url(${chatBgUrl})` }"></div>
      <main class="chat" ref="chatBox">
      <div class="chat-inner">
        <!-- 附加属性不在这里：它的入口与下拉都搬到顶栏了（顶栏搜索键右边那颗图标键，见 AttrPanel.vue） -->
        <div v-if="!activeSession" class="empty">
          <div class="empty-icon">&#9998;</div>
          <p>从左侧选择或创建一个会话</p>
        </div>
        <template v-else>
          <div v-if="archivedCount" class="archived-fold" @click="showArchived = !showArchived">
            已归档 {{ archivedCount }} 条（已存入记忆）
            <span class="fold-toggle">{{ showArchived ? "收起" : "展开" }}</span>
          </div>
                    <MessageItem v-for="m in displayMessages" :key="m.id" :m="m" />
          <div v-if="streaming" class="msg assistant">
            <div v-if="activeChar" class="msg-side">
              <span class="avatar lg">
                <img v-if="activeChar.avatar" :src="activeChar.avatar" :alt="activeChar.name">
                <template v-else>{{ activeChar.name.slice(0, 1) }}</template>
              </span>
            </div>
            <div class="bubble-wrap">
              <div v-if="activeChar" class="msg-name">{{ activeChar.name }}</div>
              <div class="bubble streaming-bubble">
                <div v-if="thinkPhase" class="phase">思考中<span class="dots"><i></i><i></i><i></i></span></div>
                <div v-else-if="streamText" class="text">{{ streamText }}</div>
                <div v-else class="phase">生成中<span class="dots"><i></i><i></i><i></i></span></div>
              </div>
            </div>
          </div>
        </template>
      </div>
      </main>
    </div>
</template>

<script setup>
import { onMounted, ref, toRefs } from "vue";
import { setChatBox, store } from "../store.js";
import MessageItem from "./MessageItem.vue";

// 对话滚动容器交给 store（滚动/回底那些方法在那边用）
const chatBox = ref(null);
onMounted(() => setChatBox(chatBox.value));

const {
  activeChar,
  activeSession,
  archivedCount,
  chatBgUrl,
  displayMessages,
  showArchived,
  streamText,
  streaming,
  thinkPhase,
} = toRefs(store);
</script>
