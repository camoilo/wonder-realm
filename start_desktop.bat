@echo off
chcp 65001 >nul
rem 双击启动电脑端（Electron 外壳）。首次使用前先在项目根目录执行一次：
rem   npm install --prefix desktop
rem 依赖装好后，这个窗口会一直开着；关掉它等于关掉应用（后端与窗口一起退出）。
cd /d "%~dp0"
if not exist "desktop\node_modules\electron\dist\electron.exe" (
  echo 还没有安装电脑端依赖，请先在本目录执行：
  echo     npm install --prefix desktop
  pause
  exit /b 1
)
echo 启动电脑端…
"desktop\node_modules\electron\dist\electron.exe" desktop
if errorlevel 1 pause
