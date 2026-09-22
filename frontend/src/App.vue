<template>

<SideBar />

<div class="main">
  <TopBar />

  <!-- 顶栏横跨"对话区 + 右侧面板"这一整行：这样顶栏最右那个"配置"键的右边缘就是
       **窗口右边缘**，面板开、关都不移动（面板只是下面这一行里的一列）。
       顶部这份宽度不受面板影响，是"点开→看一眼→点关"不用挪鼠标的前提（见 DEVELOPMENT §9.6 界面约定） -->
  <div class="work">
  <div class="work-main">
  <ChatArea />

  <InputBar />
  </div><!-- /.work-main -->

<Panel />

  </div><!-- /.work：对话区 + 面板这一行（顶栏在它上面，横跨整行） -->
</div><!-- /.main -->

<CharacterModal />
<NewSessionModal />
<ConfirmModal />
<EditMessageModal />
<CropModal />

<!-- 悬停提示的浮层：全局只有这一个，由 v-hint 指令驱动（文本与位置都从指令那边来），
     这样提示的样式与行为在整页统一。放在最后，层级高于弹窗遮罩，弹窗里的提示也能看见 -->
<div v-if="hintText" class="hint-tip" role="tooltip" :style="hintStyle">{{ hintText }}</div>
</template>

<script setup>
// 根组件只负责布局骨架与生命周期：三栏容器（.main / .work / .work-main）留在这里，
// 其余整块（左栏、顶栏、对话区、输入区、面板、5 个弹窗）各自成组件。
// 业务逻辑全在 store.js 里，这里没有一条自己的数据。
import { onBeforeUnmount, onMounted } from "vue";

import { disposeApp, initApp, registerWatchers } from "./store.js";
import { hintStyle, hintText } from "./composables/hint.js";
import SideBar from "./components/SideBar.vue";
import TopBar from "./components/TopBar.vue";
import ChatArea from "./components/ChatArea.vue";
import InputBar from "./components/InputBar.vue";
import Panel from "./components/Panel.vue";
import CharacterModal from "./components/modals/CharacterModal.vue";
import NewSessionModal from "./components/modals/NewSessionModal.vue";
import ConfirmModal from "./components/modals/ConfirmModal.vue";
import EditMessageModal from "./components/modals/EditMessageModal.vue";
import CropModal from "./components/modals/CropModal.vue";

registerWatchers();

onMounted(initApp);
onBeforeUnmount(disposeApp);
</script>
