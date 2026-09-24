@echo off
chcp 936 >nul
rem 双击启动电脑端（Electron 外壳）。首次使用前先在项目根目录执行一次：
rem   npm install --prefix desktop
rem 依赖装好后，这个窗口会一直开着；关掉它等于关掉应用（后端与窗口一起退出）。
cd /d "%~dp0"
rem 本文件是 GBK 编码 + CRLF，前面用 chcp 936：这样下面这些中文提示在本机控制台显示正常。
rem 但 Electron 的输出是 UTF-8 字节，936 控制台会显示成乱码 —— 所以启动前会再切到 65001（见文件末尾）。

rem 依赖检查：npm 说"装好了"不等于真装好 —— electron 的 postinstall 还要另下 110MB，
rem 国内直连 GitHub 常卡住或被打断，结果就是 node_modules 在、dist\electron.exe 不在。
rem 所以这里查的是那个可执行文件本身，缺了就分两种情况给出各自该跑的命令。
if not exist "desktop\node_modules\electron\dist\electron.exe" (
  if exist "desktop\node_modules" (
    echo [X] 依赖目录在，但 electron 本体缺失：postinstall 没跑完或中途被打断。
  ) else (
    echo [X] 还没有安装电脑端依赖。
  )
  echo.
  echo     在本目录执行这两条（第二条是国内镜像，省掉卡在 GitHub 上）：
  echo         set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
  echo         npm install --prefix desktop
  echo.
  echo     装完先确认这条能打印版本号，再双击本文件：
  echo         desktop\node_modules\electron\dist\electron.exe --version
  echo.
  echo     （安装时出现 allow-scripts 警告可以忽略，脚本仍会执行。）
  pause
  exit /b 1
)

rem 前端是 Vue 3 + Vite 构建的：装了 Node 且 npm install 过就顺手重建一次（约 1 秒），
rem 否则直接用仓库里已提交的构建产物 —— 没装 Node 也能照常启动。
rem 判断与 start.bat 完全一致，改完前端直接双击这个就能看到效果。
if exist "frontend\node_modules" (
  where node >nul 2>nul
  if not errorlevel 1 (
    echo 正在重建前端 ...
    pushd frontend
    call npm run build
    popd
  )
)

echo 启动电脑端…
rem 下面一行把控制台切到 UTF-8：Electron 的输出是 UTF-8 字节，在 936 控制台里会显示成
rem "鍚姩鍚庣"这种乱码（真踩过；日志文件本身是好的，乱的只是终端显示）。
rem 注意：**从这里往下，本文件余下的行必须全是 ASCII** —— cmd 在 65001 代码页下读多字节
rem 内容会按字节偏移错位解析、把半行中文当命令执行（也踩过），所以中文只能写在它前面。
chcp 65001 >nul
"desktop\node_modules\electron\dist\electron.exe" desktop
if errorlevel 1 pause
