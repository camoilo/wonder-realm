@echo off
title 多模式对话机器人
cd /d "%~dp0"

REM 前端是 Vue 3 + Vite 构建的：装了 Node 且 npm install 过就顺手重建一次（约 1 秒），
REM 否则直接用仓库里已提交的构建产物 —— 没装 Node 也能照常启动。
if exist "frontend\node_modules" (
    where node >nul 2>nul
    if not errorlevel 1 (
        echo 正在重建前端 ...
        pushd frontend
        call npm run build
        popd
    )
)

uv run run.py

if errorlevel 1 (
    echo.
    echo 服务已退出，上方为最后输出的日志。
    echo 如果是因为报错退出，请根据上面的信息排查。
    pause
)
