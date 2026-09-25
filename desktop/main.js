// Wonder Realm（奇想界域）的电脑端外壳（Electron），见 DEVELOPMENT §3.3。
//
// 职责就三件：
//   1. 起后端：spawn 项目里的 run.py --no-browser（**不重新实现任何业务**）；
//   2. 开窗口：加载 http://127.0.0.1:<port>/ —— 与浏览器里那份**完全同一个页面**；
//   3. 壳才能做的事：把窗口缩成手机尺寸（手机视图）、算局域网地址给页面复制。
//
// 局域网推送的开关**不在壳里**：它是后端 `app_settings.lan_enabled`（默认关），
// 页面上的「配置」按钮直接 PUT /api/settings，立即生效、不重启后端。
const { app, BrowserWindow, Menu, ipcMain, screen, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");           // 项目根目录（后端在它下面）

// 后端端口：壳必须和后端用同一个端口，而"换端口"是用户在 config.yaml 的 server.port 里做的，
// 所以这里也读它（只要未注释的 `port:` 行——配置文件里那些默认值都是注释掉的）。
// 环境变量 DSH_PORT 优先（临时换端口/多实例用），都拿不到就回默认 17800。
function backendPort() {
  const env = Number(process.env.DSH_PORT);
  if (env > 0) return env;
  try {
    const m = fs.readFileSync(path.join(ROOT, "config.yaml"), "utf8").match(/^\s*port:\s*(\d+)/m);
    const n = m ? Number(m[1]) : 0;
    if (n > 0) return n;
  } catch (e) { /* 配置读不到就用默认值，不能让壳因此起不来 */ }
  return 17800;
}
const PORT = backendPort();
const URL = `http://127.0.0.1:${PORT}/`;
// 手机视图：**宽度锁死**（一拖宽就跳出手机单栏布局），**高度留给用户拖**（看长内容方便）。
// 做法是 min==max==PHONE_WIDTH：边框还能拖，但尺寸被钳住，比 setResizable(false) 更符合预期。
// 尺寸取**传统手机比例 9:16**（375×667，iPhone 8 那一代）：用户明确要"不是现在的全面屏比例"。
const PHONE_WIDTH = 375;
const PHONE_DEFAULT_H = 667;                          // 9:16；每次启动都用它（仍会按工作区收一下）
const PHONE_MIN_H = 480;
const PHONE_MAX_H = 1400;
const DEFAULT_SIZE = { width: 1180, height: 780 };   // 每次启动都用它，还会按工作区收一下
const DESKTOP_MIN = { width: 380, height: 520 };      // 与 createWindow 的 minWidth/minHeight 一致
// 自绘标题栏（Window Controls Overlay）：把系统标题栏让给页面画，好让「配置 / 手机视图」这两个键
// 跟最小化 / 最大化 / 关闭排在同一行（见 DEVELOPMENT 3.3）。只有 Windows 支持得完整。
// TITLEBAR_H 必须与 CSS 的 --titlebar-h 一致，否则系统那三个按钮会跟页面按钮错开半个身位。
const WCO = process.platform === "win32";
const TITLEBAR_H = 32;   // 与 Windows 原生标题栏同高，系统那三个按钮就落在这一行里
const TITLEBAR_LIGHT = { color: "#f4f5f7", symbolColor: "#3a3f4a" };   // 与 --bg / 文字色同源
const TITLEBAR_DARK = { color: "#171a21", symbolColor: "#e6e8ec" };
const SELFTEST = process.argv.includes("--selftest");

// 自检用**独立的 userData**（临时目录）：否则"应用开着时跑自检"会撞 Chromium 的 profile 单例，
// 第二个进程静默退出、什么都测不到；顺带也不会往用户自己的偏好/日志里掺东西。
if (SELFTEST) {
  try {
    const dir = path.join(os.tmpdir(), "wonder-realm-selftest");
    fs.mkdirSync(dir, { recursive: true });
    app.setPath("userData", dir);
  } catch (e) { /* 换不了就照常用默认目录 */ }
}

let win = null;
let backend = null;
let phoneView = false;
// 窗口尺寸**只在这一趟运行里记着**（用户要求：启动用默认，自己调过的在本次运行内切来切去要记住，
// 下次启动又回到默认）。所以纯内存，不落盘：desktopBounds = 当前桌面视图的 bounds，
// phoneContentH = 手机视图的高度（内容区，用户拖过就用拖后的）。
let desktopBounds = null;
let phoneContentH = 0;

const clampHeight = (h) => Math.min(PHONE_MAX_H, Math.max(PHONE_MIN_H, Math.round(Number(h) || PHONE_DEFAULT_H)));

function log(msg) {
  // 本地时间，跟后端那些日志一个口径；带 [desktop] 前缀以便和"后端: …"区分开
  const stamp = new Date().toLocaleString("zh-CN", { hour12: false });
  const line = `[desktop] ${stamp} ${msg}`;
  console.log(line);
  try {
    fs.appendFileSync(path.join(app.getPath("userData"), "desktop.log"), line + "\n");
  } catch (e) {
    /* 日志失败不值得再抛错 */
  }
}

// ---- 局域网地址：手机要打开的那个 http://<本机IP>:<port> ----
function lanUrl() {
  const nets = os.networkInterfaces();
  const candidates = [];
  for (const [name, list] of Object.entries(nets)) {
    for (const net of list || []) {
      // 只认真实的 IPv4 局域网地址：跳过回环、内网虚拟网卡常见名字留着也无妨（都可用）
      if (net.family !== "IPv4" || net.internal) continue;
      candidates.push({ name, address: net.address });
    }
  }
  // 优先 192.168./10./172.16-31. 这些"真的像局域网"的地址
  const pick = candidates.find((c) => /^192\.168\./.test(c.address))
    || candidates.find((c) => /^10\./.test(c.address))
    || candidates.find((c) => /^172\.(1[6-9]|2\d|3[01])\./.test(c.address))
    || candidates[0];
  return pick ? `http://${pick.address}:${PORT}` : "";
}

// ---- 后端 ----
function pythonExe() {
  const venv = process.platform === "win32"
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  if (fs.existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3"; // 退回 PATH 上的 Python
}

function startBackend() {
  const exe = pythonExe();
  log(`启动后端：${exe} run.py --no-browser（端口 ${PORT}）`);
  backend = spawn(exe, ["run.py", "--no-browser"], {
    cwd: ROOT,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    // 后端输出走的是**管道**，Python 会按控制台代码页编码它（bat 里控制台设成了 936，
    // 于是吐出来是 GBK 字节），而 Node 读管道拿到 Buffer 后按 UTF-8 解 ——
    // 不做这一步，日志里后端那些中文就是一片"��"（踩过）。这里明确让 Python 输出 UTF-8。
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  backend.stdout.on("data", (b) => log(`后端: ${String(b).trim()}`));
  backend.stderr.on("data", (b) => log(`后端(err): ${String(b).trim()}`));
  backend.on("exit", (code) => {
    log(`后端退出，code=${code}`);
    backend = null;
    // 后端自己挂了就把窗口关掉：留一个点不动的界面比直接退出更让人困惑
    if (!SELFTEST && code !== 0 && !app.isQuiting) app.quit();
  });
}

function waitForBackend(timeoutMs = 120000) {
  // 给得宽：后端起服务前会先确保 Ollama 可用（见 app/ollama_boot.py），
  // 冷启动 Ollama 可能要几十秒——等不到就开窗口只会看到"打不开"
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${URL}api/limits`, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve(true);
        retry();
      });
      req.on("error", retry);
      req.setTimeout(1500, () => req.destroy());
    };
    const retry = () => {
      if (Date.now() > deadline) return reject(new Error("后端启动超时"));
      setTimeout(tick, 400);
    };
    tick();
  });
}

// ---- 手机视图：宽度锁死、高度可调 + 告诉页面（页面据此隐藏桌面专属键） ----
//
// 尺寸的口径（用户 2026-09-25 明确要求）：
//   · **每次启动两个视图都用默认**：桌面 1180×780（按工作区收），手机 375×667（9:16）
//   · **同一次运行内记住用户调过的大小**：桌面调过 -> 切去手机再回来还是那个大小；
//     手机高度拖过 -> 再进手机视图还是拖后的高度
//   · 所以尺寸**只放内存**，不落盘（早先存 desktop.json，结果"启动了却是上次那个大小/上次那个高度"，
//     用户看到的就是"默认值不起作用"）。启动一律桌面视图。
//
// 退出手机视图时恢复到多大：用这一趟记着的桌面 bounds；没有（或明显是手机尺寸那种脏值——
// 早先版本存过 405x882）就回默认。
function desktopRestoreBounds() {
  if (desktopBounds && desktopBounds.width > PHONE_WIDTH + 60) return desktopBounds;
  return { width: DEFAULT_SIZE.width, height: DEFAULT_SIZE.height };
}

// 窗口尺寸一变就记下来（内存）。自检里不记：它自己会把窗口拖来拖去量断言，
// 记进去会让后面的断言互相污染。
function rememberCurrentSize() {
  if (!win || SELFTEST) return;
  if (phoneView) phoneContentH = win.getContentSize()[1];
  else desktopBounds = win.getBounds();
}

// ---- 尺寸都往当前显示器的工作区里放 ----
// 默认 1280x860 在 1366x768 这类屏幕上会顶到任务栏甚至超出屏幕（用户报过"电脑端视图太大、
// 手机端太长"），所以建窗与进手机视图时都按工作区收一下，留点边距。
function fitInWorkArea(width, height, margin = 80, ref = null) {
  let wa = null;
  try {
    wa = (ref ? screen.getDisplayMatching(ref) : screen.getPrimaryDisplay()).workArea;
  } catch (e) { /* 拿不到工作区就不缩，别因此起不来 */ }
  if (!wa) return { width, height };
  return {
    width: Math.min(width, Math.max(360, wa.width - margin)),
    height: Math.min(height, Math.max(420, wa.height - margin)),
  };
}

// 按"中心不动"改窗口尺寸：切视图时看起来是围绕中心缩/涨，而不是从左上角缩/涨
// （用户要求"切视图前后位置不变，居中扩展或者收缩"）。贴边时再夹一次，别把窗口推出屏幕。
function setBoundsCentered(width, height) {
  const b = win.getBounds();
  const wa = (() => {
    try { return screen.getDisplayMatching(b).workArea; } catch (e) { return null; }
  })();
  let x = Math.round(b.x + (b.width - width) / 2);
  let y = Math.round(b.y + (b.height - height) / 2);
  if (wa) {
    x = Math.min(Math.max(x, wa.x), Math.max(wa.x, wa.x + wa.width - width));
    y = Math.min(Math.max(y, wa.y), Math.max(wa.y, wa.y + wa.height - height));
  }
  win.setBounds({ x, y, width, height });
}

function setPhoneView(on) {
  phoneView = !!on;
  if (!win) return phoneView;
  const frameW = Math.max(0, win.getBounds().width - win.getContentSize()[0]);
  const frameH = Math.max(0, win.getBounds().height - win.getContentSize()[1]);
  if (phoneView) {
    // 每次进手机视图都重新抓一次桌面尺寸：早先只在第一次抓，于是"在桌面调好大小 →
    // 进一趟手机视图再回来"会退回进手机视图之前的旧尺寸（用户报过"调整过的大小没记住"）
    if (!SELFTEST) desktopBounds = win.getBounds();
    // 高度用这一趟记着的（用户拖过就按拖的），没有就用 9:16 默认，再按工作区收一下
    const want = clampHeight(phoneContentH || PHONE_DEFAULT_H);
    const h = fitInWorkArea(PHONE_WIDTH, want, 120).height;
    win.setMinimumSize(PHONE_WIDTH + frameW, PHONE_MIN_H + frameH);   // 先 min 后 max，避免瞬态 min > max
    win.setMaximumSize(PHONE_WIDTH + frameW, PHONE_MAX_H + frameH);
    setBoundsCentered(PHONE_WIDTH + frameW, h + frameH);
    if (!SELFTEST) phoneContentH = win.getContentSize()[1];
    // 手机视图是"预览 / 收纳"用的：置顶，免得被别的窗口压住（用户要求；普通桌面视图不这样）
    win.setAlwaysOnTop(true);
  } else {
    win.setMinimumSize(DESKTOP_MIN.width, DESKTOP_MIN.height);
    win.setMaximumSize(0, 0);                       // 0 = 不限（回到普通窗口）
    win.setAlwaysOnTop(false);
    const b = desktopRestoreBounds();
    setBoundsCentered(b.width, b.height);
    if (!SELFTEST) desktopBounds = win.getBounds();
  }
  win.webContents.send("desktop:phone-view", phoneView);
  return phoneView;
}

// 自绘标题栏：把系统标题栏交给页面画（那三个系统按钮仍由系统画在右上角）。
// 页面据此给右上角留出宽度、把顶栏变成拖拽区；非 Windows 就退回系统标题栏。
function wcoOptions() {
  if (!WCO) return {};
  return {
    titleBarStyle: "hidden",
    titleBarOverlay: { ...TITLEBAR_LIGHT, height: TITLEBAR_H },
  };
}

// 右上角那三个系统按钮是**壳**画的，主题一变要告诉它，否则深色页面顶着一条浅色带
function setTitleBarTheme(dark) {
  if (!WCO || !win) return false;
  try {
    win.setTitleBarOverlay({ ...(dark ? TITLEBAR_DARK : TITLEBAR_LIGHT), height: TITLEBAR_H });
    return true;
  } catch (e) {
    log(`标题栏配色没换上：${e.message}`);
    return false;
  }
}

function createWindow() {
  // **启动一律用默认尺寸**（按工作区收一下，矮屏上不会顶到任务栏），不恢复上次的大小：
  // 用户要的是"启动回默认，自己调过的只在本次运行内记住"（见上面 rememberCurrentSize 那段）
  const size = fitInWorkArea(DEFAULT_SIZE.width, DEFAULT_SIZE.height);
  win = new BrowserWindow({
    width: size.width,
    height: size.height,
    minWidth: 380,
    minHeight: 520,
    backgroundColor: "#f4f5f7",
    title: "Wonder Realm（奇想界域）",
    autoHideMenuBar: true,
    ...wcoOptions(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadURL(URL);
  // 打开成功/失败都留一行日志：界面出问题时，"窗口到底加载到没有"是最先要确认的
  win.webContents.on("did-finish-load", () => log(`窗口已打开：${URL}`));
  win.webContents.on("did-fail-load", (_e, code, desc, url) => {
    log(`页面加载失败：${code} ${desc} ${url || ""}`);
  });
  // 外链走系统浏览器：应用里的链接不该把整个壳导航走
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  // 用户自己把窗口拖大/拖动 → 记进内存（切视图时用得上；下次启动不用，见上面那段说明）
  win.on("resize", rememberCurrentSize);
  win.on("move", rememberCurrentSize);
  win.on("closed", () => { win = null; });
  return win;
}

// 自检专用：隐藏窗口跑一遍关键路径，返回实测值（不弹窗、不动用户的偏好文件）
//
// 页面侧探针：在**真实壳**里打开一个会话（右侧图标列只在该会话下存在）→ 点开最低栏的「配置」
// → 把要验证的东西读回来。二维码没法在这里解码，就数暗点：全白说明压根没画出来
// （正确性由 tests/test_qr.mjs 往返验证）。
const PAGE_PROBE = `(async () => {
  const tick = () => new Promise((r) => setTimeout(r, 160));
  const until = async (fn, ms) => {
    const t = Date.now();
    for (;;) {
      const v = fn();
      if (v) return v;
      if (Date.now() - t > ms) return null;
      await tick();
    }
  };
  // 图标列：没有会话时**一个按钮都不该有**（空按钮会冒悬浮提示、第一个还会带"当前页"的紫底），
  // 有会话时才按模式渲染那几个；内容区同理（.panel-box 按 activeSession 挂载）。
  // 会话是不是自动打开的不一定，所以不做绝对断言，而是查两者自洽：
  // 「有图标按钮」⇔「内容区已挂载」。
  // 「配置」键在**窗口标题栏那一行**（.titlebar），它必须任何时候都在——没会话时也点得到。
  const titlebarEl = document.querySelector('.titlebar');
  const cfgBtnNoSession = !!document.querySelector('.titlebar [aria-label="配置"]');
  const tabBtns = Array.from(document.querySelectorAll('.panel-rail .rail-btn'));
  const boxMounted = !!document.querySelector('.panel-box');
  const tabCount = tabBtns.length;
  // 自绘标题栏：那一行要有 .wco（拖拽区 + 给系统按钮留宽度），留出来的宽度得够放那三个按钮；
  // 拖拽没法交互测，只能看计算样式：行是 drag、里面的窗口键是 no-drag
  const wcoOnTitlebar = !!document.querySelector('.titlebar.wco');
  const titlebarText = titlebarEl ? titlebarEl.textContent.replace(/\\s+/g, ' ').trim() : "";
  const dragRegion = wcoOnTitlebar ? getComputedStyle(titlebarEl).webkitAppRegion : "";
  const winBtnEl = document.querySelector('.titlebar .win-btn');
  const noDragBtn = wcoOnTitlebar && winBtnEl ? getComputedStyle(winBtnEl).webkitAppRegion : "";
  const reservedRight = wcoOnTitlebar
    ? Math.round(parseFloat(getComputedStyle(titlebarEl).paddingRight) || 0)
    : 0;
  // 第二行（页面自己的工具条）里不该再出现窗口键：会话名/搜索/模型/思考才是它的内容
  const topbar = document.querySelector('.topbar');
  const topbarHasKeys = !!(topbar && topbar.querySelector('[aria-label="配置"], [aria-label*="手机"]'));
  // 等首屏数据到位（角色列表是异步拉的），再展开角色、打开它下面的第一个会话
  await until(() => document.querySelector('.char-row') || document.querySelector('.session-row'), 6000);
  const ch = document.querySelector('.char-row');
  if (ch) { ch.click(); await tick(); }
  const row = await until(() => document.querySelector('.session-row'), 4000);
  if (row) { row.click(); await tick(); await tick(); }

  // 模式介绍浮层：桌面端要弹在按钮**右侧**、且不能被标题栏压住（用户报过"被顶部状态栏遮挡"）。
  // 它靠 mouseenter 出现，这里手动派发一次事件再量位置。
  const modeBtn = document.querySelector('.mode-tab');
  let tipRect = null, modeRect = null;
  if (modeBtn) {
    modeRect = modeBtn.getBoundingClientRect();
    modeBtn.dispatchEvent(new MouseEvent("mouseenter", { bubbles: false }));
    await tick();
    await tick();
    const tip = document.querySelector('.mode-tip');
    if (tip) {
      const r = tip.getBoundingClientRect();
      tipRect = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
    }
    modeBtn.dispatchEvent(new MouseEvent("mouseleave", { bubbles: false }));
  }
  const titlebarBottom = titlebarEl ? Math.round(titlebarEl.getBoundingClientRect().bottom) : 0;

  // 点标题栏里那个 ⚙ 开配置面板
  const rail = await until(() => document.querySelector('.titlebar [aria-label="配置"]'), 5000);
  if (rail) { rail.click(); await tick(); await tick(); }
  const cfgRect = rail ? rail.getBoundingClientRect() : null;

  const panel = await until(() => document.querySelector('.desktop-config'), 3000);
  const qr = panel && panel.querySelector('canvas.dc-qr');
  let qrInk = 0;
  if (qr) {
    await until(() => qr.width > 0, 2000);
    const d = qr.getContext('2d').getImageData(0, 0, qr.width, qr.height).data;
    for (let i = 0; i < d.length; i += 4) if (d[i] < 128) qrInk++;
  }
  const sw = panel && panel.querySelector('.dc-switch');
  const top = document.querySelector('.topbar') || document.body;
  const status = panel && panel.querySelector('.dc-status');
  // 顶栏那两颗新键（用户要求：搜索改成"点图标才弹输入框"、附加属性键搬到搜索键右边）：
  // 点开量一下——搜索条要真的弹出来、属性下拉要贴在这颗键正下方且右边缘对齐。
  // 量完**不关掉**：紧接着的自检截图正好能让人眼看一眼这两个浮层。
  const searchBtn = document.querySelector('.topbar .search-btn');
  let searchBtnRect = null, popRect = null;
  if (searchBtn) {
    searchBtnRect = searchBtn.getBoundingClientRect();
    searchBtn.click();
    await tick();
    const pop = await until(() => document.querySelector('.search-pop'), 2000);
    if (pop) {
      const r = pop.getBoundingClientRect();
      popRect = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
    }
  }
  const attrBtn = document.querySelector('.topbar .attr-btn');
  let attrBtnRect = null, attrPanelRect = null;
  if (attrBtn) {
    attrBtnRect = attrBtn.getBoundingClientRect();
    attrBtn.click();
    await tick();
    const ap = await until(() => document.querySelector('.attr-panel'), 2000);
    if (ap) {
      const r = ap.getBoundingClientRect();
      attrPanelRect = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
    }
  }
  const rect4 = (r) => r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null;
  // 面板的「世界设定」页（用户要求：内容来自绑定的预设 -> 这一页只读，改内容只能去「编辑预设…」）：
  // 点那排图标里的第二个（railTabs 顺序：生成要求 / 世界设定 / …）-> 量绑定入口、只读框与底部保存键
  let worldPage = null;
  const railBtns = Array.from(document.querySelectorAll('.panel-rail .rail-btn'));
  // 点"别处"（这里就是面板图标）要把顶栏那两个浮层收起来：手机上点会话/点按钮时它们不能继续压着内容
  const hadSearchPop = !!document.querySelector('.search-pop');
  const hadAttrPanel = !!document.querySelector('.attr-panel');
  if (railBtns.length > 1) {
    railBtns[1].click();
    await tick();
    await tick();
    const pane = document.querySelector('.panel-tab-pane[data-tab="world"]');
    if (pane) {
      const boxes = Array.from(pane.querySelectorAll('input, textarea'));
      const foot = document.querySelector('.panel-footer');
      const texts = Array.from(pane.querySelectorAll('button')).map((b) => b.textContent);
      worldPage = {
        hasCurrent: !!pane.querySelector('.preset-current'),
        bindBtn: texts.some((t) => /选择预设|更换预设/.test(t)),
        editBtn: texts.some((t) => /编辑预设/.test(t)),
        // 所有框都只读（只读框不接受输入），且这一页底部**没有保存键**
        boxesReadonly: boxes.length > 0 && boxes.every((b) => b.readOnly),
        boxCount: boxes.length,
        noSaveBtn: !(foot && foot.querySelector('.primary-btn.full')),
        footHint: !!(foot && /只读/.test(foot.textContent)),
        // 点过面板图标之后，刚才还开着的搜索条 / 属性下拉都该收起来了（本来就没开 -> null，不判）
        searchClosedOnOutside: hadSearchPop ? !document.querySelector('.search-pop') : null,
        attrClosedOnOutside: hadAttrPanel ? !document.querySelector('.attr-panel') : null,
      };
    }
  }
  const pb = document.querySelector('.titlebar [aria-label*="手机"]');   // 窗口键在标题栏那一行
  const pr = pb ? pb.getBoundingClientRect() : null;
  const hit = pr ? document.elementFromPoint(Math.round(pr.x + pr.width / 2), Math.round(pr.y + pr.height / 2)) : null;
  return {
    panelOpen: !!panel,
    searchBtnRect: rect4(searchBtnRect),
    searchPopRect: popRect,
    // 搜索条要挂在放大镜正下方（顶栏下沿再往下一点），不是 0 高的空壳
    searchPopBelowBtn: !!(popRect && searchBtnRect && popRect[1] >= Math.round(searchBtnRect.bottom)),
    attrBtnRect: rect4(attrBtnRect),
    attrPanelRect,
    // 下拉要在键的正下方、右边缘与键对齐（用户："移到当前位置的右边"）
    attrPanelAligned: !!(attrPanelRect && attrBtnRect
      && attrPanelRect[1] >= Math.round(attrBtnRect.bottom)
      && Math.abs((attrPanelRect[0] + attrPanelRect[2]) - Math.round(attrBtnRect.right)) <= 1),
    attrBtnRightOfSearch: !!(searchBtnRect && attrBtnRect
      && Math.round(attrBtnRect.x) >= Math.round(searchBtnRect.right) - 1),
    worldPage,
    panelRect: panel ? (() => { const r = panel.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; })() : null,
    phoneRect: pr ? [Math.round(pr.x), Math.round(pr.y), Math.round(pr.width), Math.round(pr.height)] : null,
    // 点中心命中的可能是按钮里的 svg，所以要看祖先链上有没有窗口键
    phoneHit: hit ? String(hit.tagName) : "",
    phoneHitOk: !!(hit && hit.closest && hit.closest(".win-btn")),
    labels: panel ? Array.from(panel.querySelectorAll('.dc-label')).map((e) => e.textContent.trim()) : [],
    qrInk,
    qrDim: !!(qr && qr.classList.contains('dim')),
    lanOn: !!(sw && sw.getAttribute('aria-checked') === 'true'),
    statusText: status ? status.textContent.replace(/\\s+/g, ' ').trim() : '',
    phoneBtnInTitlebar: !!pb,
    titlebarTheme: !!document.querySelector('.titlebar .win-btn[class*="theme-"]'),
    themeInTopbar: !!(top && top.querySelector('.theme-toggle')),
    topbarHasKeys,
    titlebarText,
    configBtnInTitlebar: !!document.querySelector('.titlebar [aria-label="配置"]'),
    // 点中心的命中链上要有窗口键（里面是 svg，直接比 className 会拿到 SVGAnimatedString）
    cfgHitOk: !!(cfgRect && (() => {
      const h = document.elementFromPoint(Math.round(cfgRect.x + cfgRect.width / 2), Math.round(cfgRect.y + cfgRect.height / 2));
      return h && h.closest && h.closest(".win-btn");
    })()),
    cfgRect: cfgRect ? [Math.round(cfgRect.x), Math.round(cfgRect.y), Math.round(cfgRect.width), Math.round(cfgRect.height)] : null,
    cfgBtnNoSession,
    wcoOnTitlebar,
    dragRegion,
    noDragBtn,
    reservedRight,
    boxMounted,
    tabCount,
    railTabs: tabCount,
    tipRect,
    modeRect: modeRect ? [Math.round(modeRect.x), Math.round(modeRect.y),
                          Math.round(modeRect.width), Math.round(modeRect.height)] : null,
    titlebarBottom,
    viewW: window.innerWidth,
    viewH: window.innerHeight,
  };
})()`;

// 手机视图下的探针：这时候页面走手机单栏、桌面键大多隐藏，**但"退出手机视图"那个键必须还在**
// （否则用户进了手机视图就没有看得见的出路）——所以单独量一次它的存在、尺寸与可点性。
const PHONE_PROBE = `(async () => {
  const tick = () => new Promise((r) => setTimeout(r, 160));
  const until = async (fn, ms) => {
    const t = Date.now();
    for (;;) {
      const v = fn();
      if (v) return v;
      if (Date.now() - t > ms) return null;
      await tick();
    }
  };
  const btn = await until(() => document.querySelector('[aria-label*="手机"]'), 3000);
  const r = btn ? btn.getBoundingClientRect() : null;
  const desc = (el) => (el ? el.tagName + "." + String((el.getAttribute && el.getAttribute("class")) || "") : "");
  const side = document.querySelector(".sidebar");
  // 手机断点下左侧栏是抽屉：默认 translateX(-100%) 藏在屏外，只有 .mobile-open 才滑出来。
  // **但隐藏窗口的 CSS 过渡不会自己推进**（没有帧），一读样式才前进一格——所以这里轮询到它
  // 真的滑出屏外再量下面的命中，否则量到的是"过渡半途横在屏幕左边"的假象（踩过一次）。
  const settled = await until(() => {
    if (!side) return true;
    return side.getBoundingClientRect().x < -100;
  }, 4000);
  const hit = r ? document.elementFromPoint(Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)) : null;
  const all = Array.from(document.querySelectorAll('[aria-label*="手机"]')).map((el) => {
    const b = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const h = document.elementFromPoint(Math.round(b.x + b.width / 2), Math.round(b.y + b.height / 2));
    return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height),
            cs.display, cs.pointerEvents, desc(h)].join("/");
  });
  const sr = side ? side.getBoundingClientRect() : null;
  return {
    exitBtn: !!btn,
    exitLabel: btn ? String(btn.getAttribute("aria-label")) : "",
    rect: r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null,
    hitOk: !!(hit && hit.closest && hit.closest(".win-btn")),
    hit: desc(hit),
    all,
    sideRect: sr ? [Math.round(sr.x), Math.round(sr.width)] : null,
    sideOpen: !!(side && side.classList.contains("mobile-open")),
    sideSettled: !!settled,
    innerWidth: window.innerWidth,
  };
})()`;

async function selftestWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 860,
    show: false,
    ...wcoOptions(),          // 自检窗口也用自绘标题栏，量的才是用户看到的那套布局
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await win.loadURL(URL);
  // 要截图就得让窗口真显示一下：隐藏窗口的 capturePage 拿到的是首帧缓存，
  // 后续 Vue 更新根本没进合成器（截出来还是"未选择会话"的空状态）。
  if (process.env.DSH_SHOT) win.showInactive();
  const bridge = await win.webContents.executeJavaScript(
    "!!(window.dshDesktop && window.dshDesktop.isDesktop)"
  );
  const desktopWidth = await win.webContents.executeJavaScript("window.innerWidth");
  const ui = await win.webContents.executeJavaScript(PAGE_PROBE);
  const beforeBounds = win.getBounds();   // 切视图前后的"中心"要对得上（用户要求位置不变）

  if (process.env.DSH_SHOT) {
    // 给人眼看一眼配置面板长什么样（自检平时不截图，避免留垃圾文件）
    try {
      fs.writeFileSync(process.env.DSH_SHOT, (await win.webContents.capturePage()).toPNG());
    } catch (e) {
      log(`截图失败：${e.message}`);
    }
    win.hide();
  }

  setPhoneView(true);
  await new Promise((r) => setTimeout(r, 700)); // 等窗口尺寸与媒体查询生效
  const phoneSize = win.getContentSize();
  const phoneBounds = win.getBounds();
  const workArea = (() => {
    try { return screen.getPrimaryDisplay().workArea; } catch (e) { return null; }
  })();
  const phoneWidth = await win.webContents.executeJavaScript("window.innerWidth");
  const mobileLayout = await win.webContents.executeJavaScript(
    "window.matchMedia('(max-width: 640px)').matches"
  );
  const pv = await win.webContents.executeJavaScript(PHONE_PROBE);   // 手机视图下必须还有"退出"键
  const onTopInPhone = win.isAlwaysOnTop();                          // 手机视图要置顶（见 setPhoneView）
  if (process.env.DSH_SHOT_PHONE) {
    // 手机视图也留一张图：顶栏那个"退出"键到底有没有被别的东西盖住，看图最快
    if (!win.isVisible()) win.showInactive();
    await new Promise((r) => setTimeout(r, 400));
    try {
      fs.writeFileSync(process.env.DSH_SHOT_PHONE, (await win.webContents.capturePage()).toPNG());
    } catch (e) {
      log(`手机视图截图失败：${e.message}`);
    }
    win.hide();
  }
  win.setContentSize(500, 900);            // 往宽里拖：宽度应当被钳住
  const clampedWidth = win.getContentSize()[0];
  win.setContentSize(PHONE_WIDTH, 1000);   // 高度应当能改
  const tallerHeight = win.getContentSize()[1];
  win.setContentSize(PHONE_WIDTH, phoneSize[1]);   // 还原：下面要量"切一圈中心偏没偏"

  setPhoneView(false);
  await new Promise((r) => setTimeout(r, 300));
  const back = win.getContentSize();
  const onTopInDesktop = win.isAlwaysOnTop();   // 退回桌面视图要取消置顶
  const afterBounds = win.getBounds();
  // 切一圈回来，窗口中心应该还在原处（"居中扩展或者收缩"，不是从左上角缩/涨）
  const centerShift = [
    Math.round(Math.abs((beforeBounds.x + beforeBounds.width / 2) - (afterBounds.x + afterBounds.width / 2))),
    Math.round(Math.abs((beforeBounds.y + beforeBounds.height / 2) - (afterBounds.y + afterBounds.height / 2))),
  ];

  // 被污染的"桌面尺寸"（跟手机一样宽，早期版本存进去过）不该被恢复成那个小尺寸
  win.setContentSize(400, 860);
  desktopBounds = null;
  setPhoneView(true);
  setPhoneView(false);
  await new Promise((r) => setTimeout(r, 300));
  const repaired = win.getContentSize();
  return {
    bridge, desktopWidth, ui, pv,
    phoneSize: { width: phoneSize[0], height: phoneSize[1] },
    phoneBounds: { width: phoneBounds.width, height: phoneBounds.height },
    workArea: workArea ? { width: workArea.width, height: workArea.height } : null,
    phoneWidth, mobileLayout, clampedWidth, tallerHeight, centerShift,
    onTopInPhone, onTopInDesktop,
    backWidth: back[0], backHeight: back[1],
    repairedWidth: repaired[0],
  };
}

// ---- 菜单：默认菜单是英文的、还带一堆用不到的东西，这里只留几项常用的 ----
function buildMenu() {
  const template = [
    {
      label: "视图",
      submenu: [
        { label: "刷新", accelerator: "F5", click: () => win && win.reload() },
        { label: "手机视图", accelerator: "F9", click: () => setPhoneView(!phoneView) },
        { type: "separator" },
        { role: "zoomIn", label: "放大" },
        { role: "zoomOut", label: "缩小" },
        { role: "resetZoom", label: "实际大小" },
        { type: "separator" },
        { role: "toggleDevTools", label: "开发者工具" },
      ],
    },
    {
      label: "窗口",
      submenu: [
        { role: "minimize", label: "最小化" },
        { role: "close", label: "关闭" },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---- 单实例：第二次双击只把已有窗口叫到前面，而不是又起一个后端 ----
// 自检**不抢这把锁**：应用开着的时候也要能跑自检（它只开一个隐藏窗口，后端若已被占就直接用现成的，
// 见 waitBackend 的"端口已被别的实例占用也算就绪"）。否则应用一开着，自检就静默退出、什么都测不到。
if (!SELFTEST && !app.requestSingleInstanceLock()) {
  log("已有实例在运行：这次只把它的窗口叫到前面");
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(async () => {
    buildMenu();
    ipcMain.on("desktop:phone-view-state", (e) => { e.returnValue = phoneView; });
    ipcMain.handle("desktop:toggle-phone-view", () => setPhoneView(!phoneView));
    ipcMain.handle("desktop:lan-url", () => lanUrl());
    ipcMain.on("desktop:titlebar-state", (e) => { e.returnValue = WCO; });
    ipcMain.handle("desktop:set-titlebar-theme", (_e, dark) => setTitleBarTheme(!!dark));
    ipcMain.handle("desktop:open-log", () => {
      const f = path.join(app.getPath("userData"), "desktop.log");
      if (!fs.existsSync(f)) return false;
      shell.openPath(f);           // 交给系统默认程序（记事本），排查时不用自己去翻 %APPDATA%
      return true;
    });

    startBackend();
    if (SELFTEST) {
      // 自检：起后端 → 开一个**隐藏**窗口 → 确认 preload 桥接通、手机视图真把页面缩到 375px。
      // 全程不显示窗口，所以自检不会在用户屏幕上弹东西出来。
      try {
        await waitForBackend();
        log(`后端就绪 ${URL} | 局域网地址 ${lanUrl() || "（没取到网卡）"}`);
        const probe = await selftestWindow();
        const u = probe.ui;
        log(`selftest ok | 桥接 ${probe.bridge} | 桌面宽 ${probe.desktopWidth}px | `
          + `手机视图 ${probe.phoneSize.width}x${probe.phoneSize.height} 页面宽 ${probe.phoneWidth}px `
          + `手机布局 ${probe.mobileLayout} | 拖到 500 宽实测 ${probe.clampedWidth}px `
          + `高度改 1000 实测 ${probe.tallerHeight}px 退出后 ${probe.backWidth}x${probe.backHeight}px | `
          + `切一圈中心偏移 ${probe.centerShift}px 置顶（手机 ${probe.onTopInPhone} / 桌面 ${probe.onTopInDesktop}）`
          + ` 手机窗口 ${probe.phoneBounds.width}x${probe.phoneBounds.height} `
          + `工作区 ${probe.workArea ? probe.workArea.width + "x" + probe.workArea.height : "未知"}`);
        log(`selftest 标题栏 | 配置键 ${u.configBtnInTitlebar} 可点 ${u.cfgHitOk} 主题键 ${u.titlebarTheme} `
          + `窗口手机键 ${u.phoneBtnInTitlebar} 那一行文字「${u.titlebarText}」 | 面板打开 ${u.panelOpen} | `
          + `自绘 ${u.wcoOnTitlebar} 右上留白 ${u.reservedRight}px 拖拽 ${u.dragRegion}/${u.noDragBtn} | `
          + `第二行还有窗口键 ${u.topbarHasKeys} 第二行有主题键 ${u.themeInTopbar} | `
          + `图标列标签 ${u.railTabs} 个 无会话时配置键仍在 ${u.cfgBtnNoSession} `
          + `没会话时图标列按钮 ${u.tabCount} 个 内容区未挂载 ${!u.boxMounted} | `
          + `二维码暗点 ${u.qrInk} 置灰 ${u.qrDim} 局域网 ${u.lanOn} | 行 ${u.labels.join("/")} | 状态 ${u.statusText}`);
        log(`selftest 浮层 | 模式按钮 ${u.modeRect} 介绍浮层 ${u.tipRect} 标题栏下沿 ${u.titlebarBottom}`);
        log(`selftest 尺寸 | 面板 ${u.panelRect} 窗口手机键 ${u.phoneRect} 该点最上层 ${u.phoneHit}`);
        log(`selftest 顶栏键 | 搜索键 ${u.searchBtnRect} 搜索条 ${u.searchPopRect} 挂在键下 ${u.searchPopBelowBtn} | `
          + `属性键 ${u.attrBtnRect}（在搜索键右边 ${u.attrBtnRightOfSearch}）`
          + ` 下拉 ${u.attrPanelRect} 对齐 ${u.attrPanelAligned}`);
        log(`selftest 只读页 | 世界设定 ${JSON.stringify(u.worldPage)}`);
        log(`selftest 手机视图 | 退出键 ${probe.pv.exitBtn} 文案「${probe.pv.exitLabel}」 `
          + `位置尺寸 ${probe.pv.rect} 可点 ${probe.pv.hitOk} 命中 ${probe.pv.hit} 其父 ${probe.pv.hitParent} `
          + `页面宽 ${probe.pv.innerWidth}px | 污染尺寸恢复实测宽 ${probe.repairedWidth}px`);
        log(`selftest 手机键全量 | ${probe.pv.all.join(" ; ")} | `
          + `抽屉 x=${probe.pv.sideRect} open=${probe.pv.sideOpen} 已归位=${probe.pv.sideSettled}`);

        // 自检是要当闸门用的：不满足就非零退出，别让它"跑完就算过"
        const bad = [];
        if (!probe.bridge) bad.push("preload 桥接没通");
        // 「配置」键在**窗口标题栏**那一行：必须在、必须点得到、且**没会话时也在**
        if (u.configBtnInTitlebar !== true) bad.push("标题栏没有配置键");
        if (u.cfgHitOk !== true) bad.push("标题栏配置键点不到（被别的元素盖住）");
        if (u.cfgBtnNoSession !== true) bad.push("没有会话时配置键不见了");
        if (u.titlebarTheme !== true) bad.push("壳里的主题键不在标题栏上");
        if (u.panelOpen !== true) bad.push("配置面板点不开");
        // 图标列按钮数由"有没有会话"决定（见上面那条自洽断言），这里不再单独要求 ≥1
        // 第二行是页面自己的工具条：窗口键与主题键都不该再出现在那里
        if (u.topbarHasKeys === true) bad.push("页面工具条里还留着窗口键");
        if (u.themeInTopbar === true) bad.push("壳里第二行还留着主题键（浏览器才有它）");
        // 自绘标题栏：那一行要有 .wco、右上要真的给系统三个按钮留出宽度，且拖拽/非拖拽写对了
        if (WCO) {
          if (u.wcoOnTitlebar !== true) bad.push("标题栏没进自绘模式（.wco）");
          if (u.dragRegion !== "drag") bad.push(`标题栏不是拖拽区（${u.dragRegion}）`);
          if (u.noDragBtn !== "no-drag") bad.push(`标题栏上的窗口键没排除拖拽区（${u.noDragBtn}）`);
          // 留白靠 env(titlebar-area-*) 算，而这套变量只在窗口真的显示时才给值
          // （隐藏窗口里取到的是兜底 100vw → 0px）。所以只在设了截图、窗口显示着的时候量它，
          // 平时由 test_app_js 的静态守卫盯着那条 CSS 表达式。
          if (win.isVisible() && !(u.reservedRight > 100)) {
            bad.push(`右上角没给系统按钮留出宽度（${u.reservedRight}px）`);
          }
        }
        if (!(u.qrInk > 50)) bad.push(`二维码没画出来（暗点 ${u.qrInk}）`);
        if (u.qrDim === u.lanOn) bad.push(`二维码置灰状态与局域网开关不一致（置灰 ${u.qrDim} 开关 ${u.lanOn}）`);
        // 顶栏那两颗新键：搜索键点开要弹出搜索条（且贴在顶栏下沿）、属性下拉要贴在键下方且右边缘对齐
        if (u.searchBtnRect && !u.searchPopRect) bad.push("点搜索键没弹出搜索条");
        if (u.searchPopRect && u.searchPopBelowBtn !== true) bad.push(`搜索条没挂在放大镜下方（${u.searchPopRect}）`);
        // 桌面端搜索条只能是一小条：早先是整行铺开，右侧那排竖排图标被它盖住（用户报过）
        if (u.searchPopRect && !(u.searchPopRect[2] <= 340)) {
          bad.push(`搜索条太宽（${u.searchPopRect[2]}px，应当 ≤340）`);
        }
        if (u.searchPopRect && !((u.searchPopRect[0] + u.searchPopRect[2]) <= u.viewW - 60)) {
          bad.push(`搜索条盖住了右侧图标列（${u.searchPopRect}，视口宽 ${u.viewW}）`);
        }
        if (u.attrBtnRect && u.searchBtnRect && u.attrBtnRightOfSearch !== true) {
          bad.push(`属性键不在搜索键右边（${u.attrBtnRect} vs ${u.searchBtnRect}）`);
        }
        // 属性下拉只在"这个会话真有属性"时才渲染，所以这里按"键在就要求下拉在"来判（自检会话已配了属性）
        if (u.attrBtnRect && !u.attrPanelRect) bad.push("点属性键没弹出下拉");
        if (u.attrPanelRect && u.attrPanelAligned !== true) {
          bad.push(`属性下拉没对齐属性键下方（下拉 ${u.attrPanelRect} 键 ${u.attrBtnRect}）`);
        }
        // 世界设定页只读：要有绑定/编辑预设入口、框全只读、底部没有保存键
        if (!u.worldPage) bad.push("世界设定页没量到（面板图标点了没切过去？）");
        else {
          if (!u.worldPage.hasCurrent) bad.push("世界设定页没有“当前世界预设”那行");
          if (!u.worldPage.bindBtn) bad.push("世界设定页没有绑定入口");
          if (!u.worldPage.editBtn) bad.push("世界设定页没有「编辑预设…」入口");
          if (u.worldPage.boxesReadonly !== true) bad.push(`世界设定页的框不是只读的（${u.worldPage.boxCount} 个）`);
          if (u.worldPage.noSaveBtn !== true) bad.push("只读页底部还挂着保存键");
          if (u.worldPage.footHint !== true) bad.push("只读页底部没给出说明");
          // 点别处（面板图标）要把顶栏那两个浮层收起来（手机端遮挡问题）
          if (u.worldPage.searchClosedOnOutside === false) bad.push("点别处没收起搜索条");
          if (u.worldPage.attrClosedOnOutside === false) bad.push("点别处没收起属性下拉");
        }
        // 配置面板必须真的落在视口里（它曾经因为父级没有定位上下文被摆到视口外面：
        // "按钮点了没反应"其实就是面板开在屏幕外 —— 实测踩到）
        const _pr = u.panelRect;
        if (!(_pr && _pr[0] >= 0 && _pr[1] >= 0
              && _pr[0] + _pr[2] <= u.viewW + 1 && _pr[1] + _pr[3] <= u.viewH + 1)) {
          bad.push(`配置面板不在视口里（${_pr}，视口 ${u.viewW}x${u.viewH}）`);
        }
        // 切视图前后中心要对得上；手机视图不能超出屏幕（用户报过"切回来变默认了""手机端太长"）
        if (probe.centerShift[0] > 4 || probe.centerShift[1] > 4) {
          bad.push(`切一圈回来窗口中心偏了 ${probe.centerShift}`);
        }
        // 手机视图要置顶（不然被别的窗口压住），退回桌面视图要取消置顶
        if (probe.onTopInPhone !== true) bad.push("手机视图没有置顶");
        if (probe.onTopInDesktop !== false) bad.push("退回桌面视图后还置顶着");
        if (probe.workArea
            && (probe.phoneBounds.height > probe.workArea.height
                || probe.phoneBounds.width > probe.workArea.width)) {
          bad.push(`手机视图超出屏幕（窗口 ${probe.phoneBounds} 工作区 ${probe.workArea}）`);
        }
        // 默认尺寸也得能装进屏幕（矮屏上 1280x860 会顶到任务栏，用户报过"视图太大"）
        if (probe.workArea) {
          const fitted = fitInWorkArea(DEFAULT_SIZE.width, DEFAULT_SIZE.height);
          if (fitted.height > probe.workArea.height || fitted.width > probe.workArea.width) {
            bad.push(`默认窗口尺寸超出屏幕（${fitted.width}x${fitted.height} 工作区 ${probe.workArea}）`);
          }
        }
        if (u.phoneBtnInTitlebar !== true) bad.push("标题栏没有手机视图键");
        if (!u.phoneRect || u.phoneRect[2] < 24 || u.phoneRect[3] < 24) bad.push(`手机视图键尺寸不对（${u.phoneRect}）`);
        if (u.phoneHitOk !== true) bad.push(`手机视图键被挡住了（该点最上层 ${u.phoneHit}）`);
        // "内容区没挂载"与"图标列标签禁用"必须一致（没会话时前者不挂载、后者禁用）
        // 有会话才有图标按钮；没会话时按钮、悬浮提示、那个紫底当前页都不该出现
        if ((u.tabCount > 0) !== u.boxMounted) {
          bad.push(`图标列按钮数(${u.tabCount})与内容区挂载(${u.boxMounted})不一致`);
        }
        if (u.labels.indexOf("推送局域网") < 0) bad.push("面板缺推送局域网行");
        // 模式介绍浮层：桌面端要弹在按钮右侧，且不能跟标题栏重叠（原来朝上弹，被标题栏挡住）
        if (u.modeRect && u.tipRect) {
          if (u.tipRect[0] < u.modeRect[0] + u.modeRect[2]) {
            bad.push(`模式介绍没弹在按钮右侧（提示 ${u.tipRect} 按钮 ${u.modeRect}）`);
          }
          if (u.tipRect[1] < u.titlebarBottom) {
            bad.push(`模式介绍被标题栏压住（提示 y=${u.tipRect[1]} 标题栏下沿 ${u.titlebarBottom}）`);
          }
          if (u.tipRect[0] + u.tipRect[2] > u.viewW + 1) bad.push(`模式介绍超出右边缘（${u.tipRect}）`);
        } else {
          bad.push("模式介绍浮层没出来（派发 mouseenter 后仍没有 .mode-tip）");
        }
        if (!/端口 \d+/.test(u.statusText)) bad.push(`面板状态行没有端口（${u.statusText}）`);
        if (!/Ollama/.test(u.statusText)) bad.push("面板状态行没有 Ollama 状态");
        // 宽高都留 2px 余量：min/max 按窗口算、内容尺寸差一圈边框，实测会有 1px 级抖动
        if (Math.abs(probe.clampedWidth - PHONE_WIDTH) > 2) bad.push(`手机视图宽度没锁住（${probe.clampedWidth}）`);
        if (probe.tallerHeight < 950) bad.push(`手机视图高度改不动（${probe.tallerHeight}）`);
        if (!probe.mobileLayout) bad.push("手机布局没生效");
        // 手机视图下必须还有看得见的出路，且它得真的能点
        if (probe.pv.exitBtn !== true) bad.push("手机视图下没有退出键");
        if (probe.pv.exitLabel.indexOf("退出") < 0) bad.push(`手机视图下退出键文案不对（${probe.pv.exitLabel}）`);
        if (!probe.pv.rect || probe.pv.rect[2] < 24 || probe.pv.rect[3] < 24) {
          bad.push(`手机视图下退出键尺寸不对（${probe.pv.rect}）`);
        }
        if (probe.pv.hitOk !== true) bad.push(`手机视图下退出键被挡住（命中 ${probe.pv.hit}，抽屉 ${probe.pv.sideRect} 已归位 ${probe.pv.sideSettled}）`);
        // 存档里被污染的"桌面尺寸"（跟手机一样宽）不该被当成恢复目标
        if (!(probe.repairedWidth > 800)) bad.push(`污染尺寸没被纠正（恢复成 ${probe.repairedWidth}px）`);
        if (bad.length) {
          log(`selftest 断言失败：${bad.join("、")}`);
          app.isQuiting = true;
          if (backend) backend.kill();
          app.exit(1);
          return;
        }
        app.isQuiting = true;
        if (backend) backend.kill();
        app.exit(0);
      } catch (e) {
        log(`selftest 失败：${e.message}`);
        app.isQuiting = true;
        if (backend) backend.kill();
        app.exit(1);
      }
      return;
    }
    // 端口已在监听（例如用户自己用 `uv run run.py` 起过）也照样开窗口——后端探测会立刻通过
    try {
      await waitForBackend();
    } catch (e) {
      log(`后端没起来：${e.message}`);
    }
    createWindow();
  });

  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => {
    app.isQuiting = true;
    if (backend) {
      log("关闭后端进程");
      backend.kill();
    }
  });
}
