<template>
<!-- 图标列（.panel-rail）**常驻**：没有会话时它也在这里，只是上面那排标签禁用 ——
     否则"配置"（局域网 / 手机扫码 / 日志）在空状态下就找不到了。
     内容区（.panel-box）仍只在该有内容时才挂载：里面的标签页会读 activeSession。 -->
<aside class="panel"
       :class="{collapsed: panelCollapsed, 'mobile-open': mobilePanelOpen, 'no-session': !activeSession}">
    <!-- 内容面板：点图标滑出/收起。滚动容器只包住标签内容，
         "未保存 / 还原" 与保存键在它外面（见 .panel-footer） -->
    <div class="panel-box" v-if="activeSession">
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
           也不会被内容量挤位置。所有页签共用这一个按钮，保存谁由当前页签决定 -->
      <div class="panel-footer">
        <div v-if="activeTabDirty" class="panel-tab-actions">
          <span class="dirty-flag">未保存</span>
          <button class="revert-btn" :class="{armed: revertArm[panelTab]}"
                  v-hint="revertArm[panelTab] ? '再点一次即还原到上次保存的内容' : '还原到上次保存的内容'"
                  @click="armRevert(panelTab)">{{ revertArm[panelTab] ? "确认还原？" : "还原" }}</button>
        </div>
        <button class="primary-btn full" :disabled="saveDisabled" @click="saveCurrentTab">保存当前配置</button>
        <p class="hint">保存后立即生效，只影响后续生成</p>
      </div>
    </div>

    <!-- 竖排图标栏（icon rail）：常驻最右——面板收起时也在，宽度也留着。
         **没打开会话时整排连按钮都不渲染**（只留这条空竖条）：否则那些空按钮还会冒悬浮提示、
         第一个还会带上"当前页"的紫色底，看着像坏了。选了会话才按模式显示该有的那几个图标
         （图标本来就按模式隔离，能出现的就会用到，所以不置灰）。「配置」不在这里，
         它在窗口标题栏（见 DEVELOPMENT 3.3）。 -->
    <div class="panel-rail">
      <template v-if="activeSession">
        <button v-for="t in railTabs" :key="t.key" class="rail-btn"
                :class="{on: !panelCollapsed && panelTab === t.key}"
                v-hint="tabLabel(t)" :aria-label="tabLabel(t)"
                :aria-pressed="!panelCollapsed && panelTab === t.key"
                @click="onRailClick(t.key)">
          <span class="rail-svg" v-html="t.icon"></span>
          <span v-if="tabDirty(t)" class="tab-dot"></span>
        </button>
      </template>
    </div>
  </aside>
</template>

<script setup>
import GenPane from "./panes/GenPane.vue";
import WorldPane from "./panes/WorldPane.vue";
import CharPane from "./panes/CharPane.vue";
import ProfilePane from "./panes/ProfilePane.vue";
import MemoryPane from "./panes/MemoryPane.vue";
import { computed, toRefs } from "vue";
import { store } from "../store.js";

// 图标统一 24px 线性风格，随按钮颜色走（currentColor）
const I = {
  // 生成要求：调谐/参数设置滑块
  gen: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/><circle cx="9" cy="7" r="2.5" fill="currentColor"/><circle cx="15" cy="12" r="2.5" fill="currentColor"/><circle cx="7" cy="17" r="2.5" fill="currentColor"/></svg>`,
  // 世界设定：地球
  world: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><line x1="3" y1="12" x2="21" y2="12"/></svg>`,
  // 角色设定：名片（头像 + 小字）——一张"角色卡"
  char: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="11" r="2.5"/><path d="M5.5 16.5c.6-1.4 1.8-2 3.5-2s2.9.6 3.5 2"/><path d="M15.5 10h2.5"/><path d="M15.5 14h2.5"/></svg>`,
  // 我的设定：人形（你自己）
  profile: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M5 20c0-3.9 3.1-6 7-6s7 2.1 7 6"/></svg>`,
  // 会话记忆：书/档案
  memory: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
};

const tabs = [
  { key: "gen", label: "生成要求", icon: I.gen },
  { key: "world", label: "世界设定", icon: I.world },
  { key: "char", label: "角色设定", icon: I.char },
  { key: "profile", label: "我的设定", icon: I.profile },
  { key: "memory", label: "会话记忆", icon: I.memory },
];

// 这一页在当前场景下用得上吗（图标按模式隔离：无角色就没有角色/我的设定，无记忆范围就没有记忆）。
// 用不到的直接不出现，不做"置灰"——能出现的就一定用得到
function tabAvailable(t) {
  if (t.key === "char" || t.key === "profile") return !!store.activeSession?.character;
  if (t.key === "memory") return !!store.memoryScope;
  return true;
}
// 只显示当前场景用得上的那几个（按钮只在有会话时渲染，见模板）
const railTabs = computed(() => tabs.filter(tabAvailable));
function tabLabel(t) {
  return t.key === "memory" ? (store.memoryScope?.label || "记忆") : t.label;
}
function tabDirty(t) {
  switch (t.key) {
    case "world": return store.worldDirty;
    case "char": return store.charDirty;
    case "profile": return store.profileDirty;
    case "memory": return store.memoryDirty;
    default: return store.genDirty;
  }
}

const {
  activeSession,
  activeTabDirty,
  memoryScope,
  mobilePanelOpen,
  panelCollapsed,
  panelTab,
  revertArm,
  saveDisabled,
} = toRefs(store);

const {
  armRevert,
  onRailClick,
  saveCurrentTab,
  togglePanel,
} = store;
</script>