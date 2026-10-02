# -*- mode: python ; coding: utf-8 -*-
"""后端打包（PyInstaller，见 DEVELOPMENT §8.4）。

跑法（仓库根）：
    uv run --group dev pyinstaller packaging/wonder-realm-backend.spec --noconfirm

产出：`dist/backend/wonder-realm-backend.exe` + `dist/backend/_internal/`（依赖与前端产物）。
electron-builder 把整个 `dist/backend` 目录放进安装包的 `resources/backend/`，壳再去 spawn 那个 exe。

几个要点：
- **一目录模式**（EXE + COLLECT）而不是 onefile：启动快得多，也不会每次解压到临时目录。
- `run.py` 里写的是 `uvicorn.run("app.main:app", ...)`——**导入字符串 PyInstaller 看不见**，
  所以整包 `app` 都要用 `collect_submodules` 显式收进来。
- uvicorn 的协议/循环/生命周期实现是按名字动态加载的，同样要显式列（只列装了的：h11 + asyncio）。
- `console=True`：壳 spawn 它时用管道收输出（windowsHide 不会弹窗），而绿色版直接双击时
  能看到日志；`icon` 让 exe 在资源管理器里也是我们的图标。
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent          # packaging/ 的上一级 = 仓库根
APP = ROOT / "app"

datas = [
    (str(APP / "static"), "app/static"),        # 前端构建产物（提交进仓库的那份）
    (str(ROOT / "config.yaml"), "."),           # 默认配置模板：数据根里没有 config.yaml 时用它
]
hiddenimports = (
    collect_submodules("app")                   # uvicorn.run 的导入字符串
    + collect_submodules("uvicorn")             # 协议 / 循环 / 生命周期按名字动态加载
    + ["yaml", "sqlite3"]
)

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 这些没被用到，排除掉能小一圈（tkinter 尤其大）
    excludes=["tkinter", "unittest", "pydoc", "doctest", "PIL", "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wonder-realm-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                                   # UPX 容易被杀软误报，不值得省那点体积
    console=True,
    disable_windowed_traceback=False,
    icon=str(ROOT / "desktop" / "build" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="backend",
)
