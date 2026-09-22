<template>
<div v-for="m in displayMessages" :key="m.id" class="msg" :class="[m.role, {archived: m.archived}]">
            <div v-if="m.role === 'assistant' && activeChar" class="msg-side">
              <span class="avatar lg">
                <img v-if="activeChar.avatar" :src="activeChar.avatar" :alt="activeChar.name">
                <template v-else>{{ activeChar.name.slice(0, 1) }}</template>
              </span>
            </div>
            <div class="bubble-wrap">
              <!-- 气泡上方那一行：说话人名字 + 发送时间。自由情境模式两边都没有名字，
                   这一行就只剩时间 -->
              <div v-if="msgName(m) || timeOf(m)" class="msg-head">
                <span v-if="msgName(m)" class="msg-name">{{ msgName(m) }}</span>
                <span v-if="timeOf(m)" class="msg-time" :title="fullTimeOf(m)">{{ timeOf(m) }}</span>
              </div>
              <div class="bubble" title="双击可编辑这条消息" @dblclick="startEdit(m)">
                <!-- 消息正文按"块"渲染：情境块与话语块。搜索时命中的字词用 <mark> 包起来
                     （仍然全部是文本节点，不走 v-html：模型输出永远不当 HTML 解释） -->
                <div v-for="(part, pi) in partsOf(m)" :key="pi"
                     :class="part.kind === 'scenario' ? 'scenario' : 'text'">
                  <span v-if="part.kind === 'scenario'" class="scenario-label">情境</span><template
                    v-for="(piece, ci) in part.pieces" :key="ci"><mark
                      v-if="piece.hit" class="search-hit"
                      :class="{current: piece.index === searchIndex}">{{ piece.text }}</mark><template
                      v-else>{{ piece.text }}</template></template>
                </div>
                <span v-if="m.archived" class="archived-flag">已归档</span>
              </div>
              <div class="msg-actions" v-show="!streaming">
                <button title="复制" @click="copyText(m)">复制</button>
                <button title="编辑" @click="startEdit(m)">编辑</button>
                <button title="删除" @click.stop="deleteMenuId = deleteMenuId === m.id ? null : m.id">删除</button>
                <button v-if="!orphanActive" title="重新生成" @click="regenerate(m)">重新生成</button>
              </div>
              <div v-if="deleteMenuId === m.id" class="delete-menu" @click.stop>
                <button @click="removeMessage(m, false)">删除这条</button>
                <button @click="removeMessage(m, true)">删除这里之后</button>
              </div>
            </div>
            <!-- 用户自己的头像在气泡右侧（角色两模式才有；自由情境模式不显示用户的
                 头像与名字，见 10.35）。还没设名字也没传头像时整列不渲染 -->
            <div v-if="m.role === 'user' && showUserSide" class="msg-side">
              <span class="avatar lg">
                <img v-if="profile.avatar" :src="profile.avatar" :alt="profile.name">
                <template v-else>{{ (profile.name || "我").slice(0, 1) }}</template>
              </span>
            </div>
          </div>
</template>

<script setup>
import { toRefs } from "vue";
import { store } from "../store.js";

const props = defineProps({ m: { type: Object, required: true } });

// 模板用到的状态与计算属性（toRefs 后模板里仍是裸名字，读写都保持响应式）
const {
  activeChar,
  deleteMenuId,
  displayMessages,
  orphanActive,
  profile,
  searchIndex,
  showUserSide,
  streaming,
} = toRefs(store);

// 模板用到的方法（函数不是响应式的，直接解构）
const {
  copyText,
  fullTimeOf,
  msgName,
  partsOf,
  regenerate,
  removeMessage,
  startEdit,
  timeOf,
} = store;
</script>
