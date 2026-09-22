<template>
<aside class="panel" :class="{collapsed: panelCollapsed}" v-if="activeSession">
    <div class="panel-inner">
      <!-- 面板里没有标题行、也没有关闭键：开关只有一个，就在顶栏最右那一格，
           位置不随面板开合变化（见 DEVELOPMENT §9.6 界面约定）。所以标签栏是面板最上面的一行 -->
      <!-- 标签栏放在滚动容器**外面**：面板内容一长，滚轮往下滚时标签会被顶出视野、
           得再滚回顶部才能切标签。放在外面就永远贴在面板顶部。
           （整个 aside 本来就是 v-if="activeSession"，这里不必再判一次） -->
      <div class="panel-tabs">
        <button class="panel-tab" :class="{on: panelTab === 'gen'}"
                @click="panelTab = 'gen'">生成要求<span v-if="genDirty" class="tab-dot"></span></button>
        <!-- 世界设定是全局的，三种模式都用得上（导演模式也发生在某个世界里），所以不判模式 -->
        <button class="panel-tab" :class="{on: panelTab === 'world'}"
                @click="panelTab = 'world'">世界设定<span v-if="worldDirty" class="tab-dot"></span></button>
        <button v-if="activeSession.character" class="panel-tab" :class="{on: panelTab === 'char'}"
                @click="panelTab = 'char'">角色设定<span v-if="charDirty" class="tab-dot"></span></button>
        <button v-if="activeSession.character" class="panel-tab" :class="{on: panelTab === 'profile'}"
                @click="panelTab = 'profile'">我的设定<span v-if="profileDirty" class="tab-dot"></span></button>
        <button v-if="memoryScope" class="panel-tab" :class="{on: panelTab === 'memory'}"
                @click="panelTab = 'memory'">{{ memoryScope.label }}<span v-if="memoryDirty" class="tab-dot"></span></button>
      </div>
      <div class="panel-body">
        <div class="panel-tab-pane" v-show="panelTab === 'gen'">
        <GenPane />
      </div>
        <!-- 世界设定：全局一份，三种模式都注入。名称只给自己辨认、**不进提示词**；
             描述 / 规则 / 词库会写进提示词（位置在角色设定之前），所以都带限额与计数 -->
        <div class="panel-tab-pane" v-show="panelTab === 'world'">
        <WorldPane />
      </div>
        <div v-if="activeSession.character" class="panel-tab-pane"
             v-show="panelTab === 'char'">
        <CharPane />
      </div>
        <!-- 我的设定：用户本人。姓名与身份会进聊天与沉浸两种模式的提示词，头像与名字显示在
             自己消息的气泡旁；导演模式用不到它，所以那个模式下不出现这个标签 -->
        <div v-if="activeSession.character" class="panel-tab-pane" v-show="panelTab === 'profile'">
        <ProfilePane />
      </div>
        <div v-if="memoryScope" class="panel-tab-pane" v-show="panelTab === 'memory'">
        <MemoryPane />
      </div>
      </div>
      <!-- 保存与"未保存 / 还原"常驻在面板底部（滚动容器之外）：内容再长也不会跟着滚走，
           也不会被内容量挤位置。三个标签共用这一个按钮，保存谁由当前标签决定 -->
      <div class="panel-footer">
        <div v-if="activeTabDirty" class="panel-tab-actions">
          <span class="dirty-flag">未保存</span>
          <button class="revert-btn" :class="{armed: revertArm[panelTab]}"
                  :title="revertArm[panelTab] ? '再点一次即还原到上次保存的内容' : '还原到上次保存的内容'"
                  @click="armRevert(panelTab)">{{ revertArm[panelTab] ? "确认还原？" : "还原" }}</button>
        </div>
        <button class="primary-btn full" :disabled="saveDisabled" @click="saveCurrentTab">保存当前配置</button>
        <p class="hint">保存后立即生效，只影响后续生成</p>
      </div>
    </div>
  </aside>
</template>

<script setup>
import GenPane from "./panes/GenPane.vue";
import WorldPane from "./panes/WorldPane.vue";
import CharPane from "./panes/CharPane.vue";
import ProfilePane from "./panes/ProfilePane.vue";
import MemoryPane from "./panes/MemoryPane.vue";
import { toRefs } from "vue";
import { store } from "../store.js";

const {
  activeSession,
  activeTabDirty,
  charDirty,
  genDirty,
  memoryDirty,
  memoryScope,
  panelCollapsed,
  panelTab,
  profileDirty,
  revertArm,
  saveDisabled,
  worldDirty,
} = toRefs(store);

const {
  armRevert,
  saveCurrentTab,
} = store;
</script>
