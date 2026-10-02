<template>
  <!-- 桌面端（Electron 壳）的「配置」小面板。挂在右侧图标列最低栏那个 ⚙ 上（见 Panel.vue），
       网页端与手机浏览器没有 window.dshDesktop，所以这份内容压根不会渲染（DEVELOPMENT §3.3）。

       内容分四块：局域网开关与状态、手机扫码用的二维码、壳相关动作（手机视图 / 日志）、
       防火墙命令。二维码只在局域网开着、且真取到地址时才画——没地址时给一句说明，
       不画一个扫不出东西的空码。 -->
  <div class="desktop-config">
    <div class="dc-row">
      <span class="dc-label">推送局域网</span>
      <button class="dc-switch" :class="{on: lanEnabled}" :disabled="lanBusy"
              role="switch" :aria-checked="lanEnabled" aria-label="推送局域网" @click="toggleLan">
        <span class="dc-knob"></span>
      </button>
    </div>
    <p class="dc-status">{{ statusText }}</p>

    <!-- 二维码**只在局域网开着时才画**：关着时什么都不显示——
         界面是给用户用的，不用介绍"打开开关后会怎样"。
         码与地址里都带着访问码（`?k=`）：非本机来源要带对它才放行（见 DEVELOPMENT §8.3） -->
    <template v-if="lanUrl && lanEnabled">
      <canvas ref="qrEl" class="dc-qr" width="232" height="232" aria-label="手机访问二维码"></canvas>
      <div class="dc-row">
        <span class="dc-url">{{ lanLink }}</span>
        <button class="ghost-btn dc-copy" @click="copyLanUrl">{{ lanCopied ? "已复制" : "复制" }}</button>
      </div>
      <div class="dc-row">
        <span class="dc-label">访问码</span>
        <span class="dc-code">{{ lanToken }}</span>
        <button class="ghost-btn dc-copy" :disabled="lanBusy" @click="regenerateLanCode">重新生成</button>
      </div>
      <p class="hint">手机连同一个 WiFi，扫上面的码就能进；换一台设备要重新扫（地址里带着访问码，
        别把它发给别人）。</p>
    </template>
    <!-- 关着（或没地址）时这里**什么都不显示**：不做"打开后会怎样"的介绍 -->
    <p v-else-if="!lanUrl" class="hint">没取到局域网地址（用 ipconfig 看一眼本机 IPv4，确认连着 WiFi/网线）。</p>

    <div class="dc-actions">
      <button class="ghost-btn dc-act" @click="stopAllGenerations">停止所有生成</button>
      <button class="ghost-btn dc-act" :disabled="backupBusy" @click="runBackup">
        {{ backupBusy ? "备份中…" : "手动备份" }}
      </button>
      <button class="ghost-btn dc-act" @click="copyFirewallCmd">{{ firewallCopied ? "已复制命令" : "复制防火墙命令" }}</button>
      <button class="ghost-btn dc-act" @click="openLog">打开日志文件</button>
    </div>
    <!-- 备份结果就显示在键下面：文件名是 manual-…，与启动时自动备份的 chatbot-… 分开 -->
    <p v-if="backupNote" class="hint">{{ backupNote }}</p>
    <p class="hint">防火墙命令要在<strong>管理员</strong>权限的 PowerShell 里执行，只需一次。</p>
    <p class="hint">启动时自动备份的留在 <code>backups/</code> 里、只保留最近 7 天；上面这个手动备份不会被自动清理。</p>
    <p class="hint">局域网开着时只有带访问码的设备能访问；传输没有加密，同一 WiFi 里抓包仍可能拿到访问码，
      公共网络里建议直接关掉。</p>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, toRefs, watch } from "vue";
import QRCode from "qrcode";
import { store } from "../store.js";

const {
  backupBusy,
  backupNote,
  firewallCopied,
  lanBusy,
  lanCopied,
  lanEnabled,
  lanLink,
  lanToken,
  lanUrl,
} = toRefs(store);

const {
  copyFirewallCmd,
  stopAllGenerations,
  copyLanUrl,
  openLog,
  regenerateLanCode,
  runBackup,
  toggleLan,
} = store;

// 状态行：端口 / Ollama / 局域网。数据都是界面本来就在用的，不额外发请求。
const statusText = computed(() => {
  const port = window.location.port || "17800";
  const ollama = store.modelWarning
    ? "Ollama 未连接"
    : `Ollama 已连接 · ${store.models.length} 个模型`;
  return `端口 ${port} · ${ollama} · 局域网${lanEnabled.value ? "已开启" : "已关闭"}`;
});

// 二维码：232px 画布 + CSS 116px，高分屏下也不糊
const qrEl = ref(null);
async function paint() {
  if (!qrEl.value || !lanLink.value) return;
  try {
    await QRCode.toCanvas(qrEl.value, lanLink.value, {
      width: 232, margin: 1, errorCorrectionLevel: "M",
    });
  } catch (e) {
    store.error = `二维码生成失败：${e.message}`;
  }
}
onMounted(() => { if (lanLink.value && lanEnabled.value) paint(); });
watch([lanLink, lanEnabled], async () => {
  await nextTick();          // 等 v-if 里的 canvas 真的挂上再画（开关一开才挂载）
  if (lanLink.value && lanEnabled.value) paint();
});
</script>
