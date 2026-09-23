// 多模式对话机器人的电脑端外壳（Electron），见 DEVELOPMENT §7.4。
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
const PHONE = { width: 390, height: 844 };            // 手机视图的窗口内容尺寸（CSS px）
const SELFTEST = process.argv.includes("--selftest");

let win = null;
let backend = null;
let phoneView = false;
let desktopBounds = null; // 进手机视图前的窗口尺寸，退出时恢复

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
  const line = `[desktop] ${new Date().toISOString()} ${msg}`;
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

function waitForBackend(timeoutMs = 30000) {
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

// ---- 手机视图：缩窗口 + 告诉页面（页面据此隐藏桌面专属键） ----
function setPhoneView(on) {
  phoneView = !!on;
  if (!win) return phoneView;
  if (phoneView) {
    if (!desktopBounds) desktopBounds = win.getBounds();
    win.setResizable(true);              // 先允许改，再锁死，避免某些平台改不动
    win.setContentSize(PHONE.width, PHONE.height);
    win.setResizable(false);             // 手机视图下不让拖大小：一拖就跳出手机布局
  } else {
    win.setResizable(true);
    if (desktopBounds) win.setBounds(desktopBounds);
  }
  win.webContents.send("desktop:phone-view", phoneView);
  writePrefs({ phoneView, bounds: win.getBounds() });
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
  // 外链走系统浏览器：应用里的链接不该把整个壳导航走
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.on("close", () => {
    if (!phoneView) writePrefs({ bounds: win.getBounds() });
  });
  win.on("closed", () => { win = null; });
  if (prefs.phoneView) setPhoneView(true); // 上次退出时就是手机视图，这次接着用
  return win;
}

// 自检专用：隐藏窗口跑一遍关键路径，返回实测值（不弹窗、不动用户的偏好文件）
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
  const bridge = await win.webContents.executeJavaScript(
    "!!(window.dshDesktop && window.dshDesktop.isDesktop)"
  );
  const desktopWidth = await win.webContents.executeJavaScript("window.innerWidth");
  setPhoneView(true);
  await new Promise((r) => setTimeout(r, 700)); // 等窗口尺寸与媒体查询生效
  const phoneSize = win.getContentSize();
  const phoneWidth = await win.webContents.executeJavaScript("window.innerWidth");
  const mobileLayout = await win.webContents.executeJavaScript(
    "window.matchMedia('(max-width: 640px)').matches"
  );
  return { bridge, desktopWidth, phoneSize: { width: phoneSize[0], height: phoneSize[1] },
           phoneWidth, mobileLayout };
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

    startBackend();
    if (SELFTEST) {
      // 自检：起后端 → 开一个**隐藏**窗口 → 确认 preload 桥接通、手机视图真把页面缩到 390px。
      // 全程不显示窗口，所以自检不会在用户屏幕上弹东西出来。
      try {
        await waitForBackend();
        log(`后端就绪 ${URL} | 局域网地址 ${lanUrl() || "（没取到网卡）"}`);
        const probe = await selftestWindow();
        log(`selftest ok | 桥接 ${probe.bridge} | 桌面宽 ${probe.desktopWidth}px | `
          + `手机视图 ${probe.phoneSize.width}x${probe.phoneSize.height} 页面宽 ${probe.phoneWidth}px `
          + `手机布局 ${probe.mobileLayout}`);
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
