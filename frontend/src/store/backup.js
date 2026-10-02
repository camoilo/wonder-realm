// 手动备份（见 DEVELOPMENT §5.7）。
//
// 自动备份只在**启动时**留一份（`chatbot-<时间戳>.db`，按天数轮转）；这里给的是"现在就来一份"，
// 后端把它写成 `manual-<时间戳>.db`，并且**不参与那套轮转**（点名要的备份被自动删掉才是意外）。
// 双端入口：电脑端在 ⚙ 配置面板，手机端在顶栏 ⋮ 菜单里。
import { store } from "./state.js";

Object.assign(store, {
  async runBackup() {
    if (store.backupBusy) return;
    store.backupBusy = true;
    store.backupNote = "";
    try {
      const r = await store.api("/api/backup", { method: "POST" });
      const kb = Math.max(1, Math.round((r.size || 0) / 1024));
      store.backupNote = `已备份 ${r.file}（${kb} KB）`;
    } catch (e) {
      store.error = `备份失败：${e.message}`;
    } finally {
      store.backupBusy = false;
    }
  },
});
