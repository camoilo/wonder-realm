@echo off
title 多模式对话机器人
cd /d "%~dp0"

uv run run.py

if errorlevel 1 (
    echo.
    echo 服务已退出，上方为最后输出的日志。
    echo 如果是因为报错退出，请根据上面的信息排查。
    pause
)
