// 多模式对话机器人的电脑端外壳（Electron），见 DEVELOPMENT §3.3。
//
// 职责就三件：
//   1. 起后端：spawn 项目里的 run.py --no-browser（**不重新实现任何业务**）；
//   2. 开窗口：加载 http://127.0.0.1:<port>/ —— 与浏览器里那份**完全同一个页面**；
//   3. 壳才能做的事：把窗口缩成手机尺寸（手机视图）、算局域网地址给页面复制。
//
// 局域网推送的开关**不在壳里**：它是后端 `app_settings.lan_enabled`（默认关），
// 页面上的「配置」按钮直接 PUT /api/settings，立即生效、不重启后端。
const { app, BrowserWindow, Menu, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");           // 项目根目录（后端在它下面）
const PORT = Number(process.env.DSH_PORT || 17800);
const URL = `http://127.0.0.1:${PORT}/`;
// 手机视图：**宽度锁死**（一拖宽就跳出手机单栏布局），**高度留给用户拖**（看长内容方便）。
// 做法是 min==max==PHONE_WIDTH：边框还能拖，但尺寸被钳住，比 setResizable(false) 更符合预期。
const PHONE_WIDTH = 390;
const PHONE_DEFAULT_H = 844;                          // 没存过就用常见手机高度
const PHONE_MIN_H = 480;
const PHONE_MAX_H = 1400;
const DESKTOP_MIN = { width: 380, height: 520 };      // 与 createWindow 的 minWidth/minHeight 一致
const SELFTEST = process.argv.includes("--selftest");

let win = null;
let backend = null;
let phoneView = false;
let desktopBounds = null; // 进手机视图前的窗口 bounds，退出时恢复

const clampHeight = (h) => Math.min(PHONE_MAX_H, Math.max(PHONE_MIN_H, Math.round(Number(h) || PHONE_DEFAULT_H)));

// ---- 壳的本地偏好（窗口尺寸 / 上次是不是手机视图）：放 userData，不进数据库 ----
const prefsFile = () => path.join(app.getPath("userData"), "desktop.json");

function readPrefs() {
  try {
    return JSON.parse(fs.readFileSync(prefsFile(), "utf8"));
  } catch (e) {
    return {};
  }
}

function writePrefs(patch) {
  const next = { ...readPrefs(), ...patch };
  try {
    fs.mkdirSync(path.dirname(prefsFile()), { recursive: true });
    fs.writeFileSync(prefsFile(), JSON.stringify(next, null, 2), "utf8");
  } catch (e) {
    log(`偏好写不进去：${e.message}`);
  }
}

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
// 偏好里**桌面尺寸与手机高度分开存**：早先把手机尺寸当 bounds 存过，结果"在手机视图下退出应用"
// 会让下次启动的窗口只有 390 宽、且退出手机视图也回不到大尺寸（桌面尺寸被覆盖掉了）。
function persistWindowState() {
  if (SELFTEST || !win) return;   // 自检只是量尺寸，不该改用户的偏好
  if (phoneView) {
    writePrefs({ phoneView: true, phoneHeight: win.getContentSize()[1] });
  } else {
    writePrefs({ phoneView: false, bounds: win.getBounds() });
  }
}

function setPhoneView(on) {
  phoneView = !!on;
  if (!win) return phoneView;
  if (phoneView) {
    if (!desktopBounds) desktopBounds = win.getBounds();
    // min/max 说的是**窗口**尺寸，setContentSize 说的是**内容**尺寸，两者差一个边框宽度：
    // 直接拿 PHONE_WIDTH 当上限会得到 378 内容宽（实测），所以先量出边框差再补上。
    const frameW = Math.max(0, win.getBounds().width - win.getContentSize()[0]);
    win.setMinimumSize(PHONE_WIDTH + frameW, PHONE_MIN_H);   // 先 min 后 max，避免 min > max 的瞬态
    win.setMaximumSize(PHONE_WIDTH + frameW, PHONE_MAX_H);
    win.setContentSize(PHONE_WIDTH, clampHeight(readPrefs().phoneHeight));
  } else {
    win.setMinimumSize(DESKTOP_MIN.width, DESKTOP_MIN.height);
    win.setMaximumSize(0, 0);                       // 0 = 不限（回到普通窗口）
    if (desktopBounds) win.setBounds(desktopBounds);
  }
  win.webContents.send("desktop:phone-view", phoneView);
  persistWindowState();
  return phoneView;
}

function createWindow() {
  const prefs = readPrefs();
  const bounds = prefs.bounds || {};
  win = new BrowserWindow({
    width: bounds.width || 1280,
    height: bounds.height || 860,
    x: bounds.x,
    y: bounds.y,
    minWidth: 380,
    minHeight: 520,
    backgroundColor: "#f4f5f7",
    title: "多模式对话机器人",
    autoHideMenuBar: true,
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
  win.on("close", () => {
    // 手机视图下**不写 bounds**：那是手机尺寸，不是用户想要的桌面尺寸（写进去就再也回不去了）
    persistWindowState();
  });
  win.on("closed", () => { win = null; });
  if (prefs.phoneView) setPhoneView(true); // 上次退出时就是手机视图，这次接着用
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
  // 等首屏数据到位（角色列表是异步拉的），再展开角色、打开它下面的第一个会话
  await until(() => document.querySelector('.char-row') || document.querySelector('.session-row'), 6000);
  const ch = document.querySelector('.char-row');
  if (ch) { ch.click(); await tick(); }
  const row = await until(() => document.querySelector('.session-row'), 4000);
  if (row) { row.click(); await tick(); await tick(); }

  const rail = await until(() => document.querySelector('.rail-config'), 5000);
  const railBottom = rail ? (() => {
    const r = rail.getBoundingClientRect();
    const p = rail.parentElement.getBoundingClientRect();
    return Math.round(p.bottom - r.bottom);   // 距图标列底边多远：越小越靠底
  })() : -1;
  if (rail) { rail.click(); await tick(); await tick(); }

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
  const pb = top.querySelector('[aria-label*="手机"]');
  const pr = pb ? pb.getBoundingClientRect() : null;
  const hit = pr ? document.elementFromPoint(Math.round(pr.x + pr.width / 2), Math.round(pr.y + pr.height / 2)) : null;
  return {
    railConfig: !!rail,
    railBottom,
    panelOpen: !!panel,
    panelRect: panel ? (() => { const r = panel.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; })() : null,
    phoneRect: pr ? [Math.round(pr.x), Math.round(pr.y), Math.round(pr.width), Math.round(pr.height)] : null,
    // 点中心命中的可能是按钮里的 svg，所以要看祖先链上有没有 .desktop-btn
    phoneHit: hit ? String(hit.tagName) : "",
    phoneHitOk: !!(hit && hit.closest && hit.closest(".desktop-btn")),
    labels: panel ? Array.from(panel.querySelectorAll('.dc-label')).map((e) => e.textContent.trim()) : [],
    qrInk,
    qrDim: !!(qr && qr.classList.contains('dim')),
    lanOn: !!(sw && sw.getAttribute('aria-checked') === 'true'),
    statusText: status ? status.textContent.replace(/\\s+/g, ' ').trim() : '',
    phoneBtnInTopBar: !!pb,
    themeBtn: !!document.querySelector('.theme-toggle'),
    noConfigInTopBar: !top.querySelector('[aria-label="配置"]'),
  };
})()`;

async function selftestWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 860,
    show: false,
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
  const phoneWidth = await win.webContents.executeJavaScript("window.innerWidth");
  const mobileLayout = await win.webContents.executeJavaScript(
    "window.matchMedia('(max-width: 640px)').matches"
  );
  win.setContentSize(500, 900);            // 往宽里拖：宽度应当被钳住
  const clampedWidth = win.getContentSize()[0];
  win.setContentSize(PHONE_WIDTH, 1000);   // 高度应当能改
  const tallerHeight = win.getContentSize()[1];

  setPhoneView(false);
  await new Promise((r) => setTimeout(r, 300));
  const back = win.getContentSize();
  return {
    bridge, desktopWidth, ui,
    phoneSize: { width: phoneSize[0], height: phoneSize[1] },
    phoneWidth, mobileLayout, clampedWidth, tallerHeight,
    backWidth: back[0], backHeight: back[1],
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
if (!app.requestSingleInstanceLock()) {
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
    ipcMain.handle("desktop:open-log", () => {
      const f = path.join(app.getPath("userData"), "desktop.log");
      if (!fs.existsSync(f)) return false;
      shell.openPath(f);           // 交给系统默认程序（记事本），排查时不用自己去翻 %APPDATA%
      return true;
    });

    startBackend();
    if (SELFTEST) {
      // 自检：起后端 → 开一个**隐藏**窗口 → 确认 preload 桥接通、手机视图真把页面缩到 390px。
      // 全程不显示窗口，所以自检不会在用户屏幕上弹东西出来。
      try {
        await waitForBackend();
        log(`后端就绪 ${URL} | 局域网地址 ${lanUrl() || "（没取到网卡）"}`);
        const probe = await selftestWindow();
        const u = probe.ui;
        log(`selftest ok | 桥接 ${probe.bridge} | 桌面宽 ${probe.desktopWidth}px | `
          + `手机视图 ${probe.phoneSize.width}x${probe.phoneSize.height} 页面宽 ${probe.phoneWidth}px `
          + `手机布局 ${probe.mobileLayout} | 拖到 500 宽实测 ${probe.clampedWidth}px `
          + `高度改 1000 实测 ${probe.tallerHeight}px 退出后 ${probe.backWidth}x${probe.backHeight}px`);
        log(`selftest 界面 | 配置键在图标列 ${u.railConfig} 距底 ${u.railBottom}px 面板打开 ${u.panelOpen} `
          + `顶栏手机键 ${u.phoneBtnInTopBar} 主题键 ${u.themeBtn} 顶栏已无配置键 ${u.noConfigInTopBar} | `
          + `二维码暗点 ${u.qrInk} 置灰 ${u.qrDim} 局域网 ${u.lanOn} | 行 ${u.labels.join("/")} | 状态 ${u.statusText}`);
        log(`selftest 尺寸 | 面板 ${u.panelRect} 手机键 ${u.phoneRect} 该点最上层 ${u.phoneHit}`);

        // 自检是要当闸门用的：不满足就非零退出，别让它"跑完就算过"
        const bad = [];
        if (!probe.bridge) bad.push("preload 桥接没通");
        if (u.railConfig !== true) bad.push("配置键不在右侧图标列");
        if (!(u.railBottom >= 0 && u.railBottom <= 24)) bad.push(`配置键不在图标列最低栏（距底 ${u.railBottom}px）`);
        if (u.panelOpen !== true) bad.push("配置面板点不开");
        if (!(u.qrInk > 50)) bad.push(`二维码没画出来（暗点 ${u.qrInk}）`);
        if (u.qrDim === u.lanOn) bad.push(`二维码置灰状态与局域网开关不一致（置灰 ${u.qrDim} 开关 ${u.lanOn}）`);
        if (u.phoneBtnInTopBar !== true) bad.push("顶栏没有手机视图键");
        if (!u.phoneRect || u.phoneRect[2] < 24 || u.phoneRect[3] < 24) bad.push(`顶栏手机键尺寸不对（${u.phoneRect}）`);
        if (u.phoneHitOk !== true) bad.push(`顶栏手机键被挡住了（该点最上层 ${u.phoneHit}）`);
        if (u.themeBtn !== true) bad.push("顶栏主题键不见了");
        if (u.noConfigInTopBar !== true) bad.push("有会话时顶栏还留着配置键");
        if (u.labels.indexOf("推送局域网") < 0) bad.push("面板缺推送局域网行");
        if (u.labels.indexOf("手机视图") < 0) bad.push("面板缺手机视图行");
        if (!/端口 \d+/.test(u.statusText)) bad.push(`面板状态行没有端口（${u.statusText}）`);
        if (!/Ollama/.test(u.statusText)) bad.push("面板状态行没有 Ollama 状态");
        // 宽高都留 2px 余量：min/max 按窗口算、内容尺寸差一圈边框，实测会有 1px 级抖动
        if (Math.abs(probe.clampedWidth - PHONE_WIDTH) > 2) bad.push(`手机视图宽度没锁住（${probe.clampedWidth}）`);
        if (probe.tallerHeight < 950) bad.push(`手机视图高度改不动（${probe.tallerHeight}）`);
        if (!probe.mobileLayout) bad.push("手机布局没生效");
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
    // 端口已在监听（例如用户自己用 start.bat 起过）也照样开窗口——后端探测会立刻通过
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
