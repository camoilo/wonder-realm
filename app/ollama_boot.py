"""Ollama 没在跑就顺手拉起来（见 DEVELOPMENT §3.4 启动流程）。

放在启动器里而不是各个 .bat 里各写一遍：桌面端外壳也是 spawn `run.py`，于是
**bat / 命令行 / 桌面端**三条入口共用同一份实现，行为不会走偏。

为什么用"探端口 + 按需启动"而不是每次都起：Ollama 是台共享服务（用户可能还在别处用它），
已经在跑就什么都不做；启动起来也**不跟着本进程退出**（DETACHED），关掉应用不影响它。
"""
import logging
import subprocess
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("ollama_agent")

# 只有本机地址才由我们去拉起来：base_url 指向别的机器时，那不是我们能启动的
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
START_TIMEOUT = 30.0  # 冷启动留够时间（首次加载模型前，服务本身通常几秒就绪）
POLL_INTERVAL = 0.5


def _is_local(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "") in LOCAL_HOSTS


def ping(base_url: str, timeout: float = 1.5) -> bool:
    """`/api/tags` 能返回 200 就算在跑——正是应用随后要用的接口。"""
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _spawn_serve() -> None:
    """后台拉起 `ollama serve`。找不到可执行文件时抛 FileNotFoundError，由调用方决定怎么说。"""
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):  # Windows：脱离本进程与它的控制台
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["ollama", "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=not flags,  # POSIX：另开会话，同样脱离父进程
        close_fds=True,
    )


def ensure_ollama(
    base_url: str,
    auto_start: bool = True,
    timeout: float = START_TIMEOUT,
    probe=ping,
    spawn=None,
) -> str:
    """确保 Ollama 可用，返回一个状态字符串（由 `report()` 翻译成人话）。

    probe / spawn 可注入，测试里就不真的联网、不真的起进程。
    """
    if probe(base_url):
        return "running"
    if not auto_start:
        return "skipped-disabled"
    if not _is_local(base_url):
        return "skipped-remote"
    spawn = spawn or _spawn_serve
    try:
        spawn()
    except FileNotFoundError:
        return "skipped-missing"
    except OSError as e:  # 权限/被拦等：不该让整个启动失败，界面里还会照常提示连不上
        log.warning("拉起 ollama serve 失败：%s", e)
        return "skipped-missing"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        if probe(base_url):
            return "started"
    return "started-timeout"


def report(status: str, base_url: str) -> str:
    """把状态翻成一句打印给人看的话（同一个状态只在这里定义文案）。"""
    return {
        "running": f"Ollama 已在运行（{base_url}）",
        "started": f"Ollama 之前没在运行，已顺手启动（{base_url}）",
        "started-timeout": "已尝试启动 Ollama，但它还没就绪；界面里若提示连不上，稍等片刻或手动执行 ollama serve",
        "skipped-disabled": "按配置跳过了 Ollama 自启（ollama.auto_start: false）",
        "skipped-remote": f"Ollama 不在本机（{base_url}），不自启",
        "skipped-missing": "没找到 ollama 命令，无法自启：请先安装 Ollama（https://ollama.com/download），装好后重开应用即可",
    }.get(status, status)
