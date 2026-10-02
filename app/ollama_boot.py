"""Ollama 没在跑就顺手拉起来（见 DEVELOPMENT §3.4 启动流程）。

放在启动器里而不是各个 .bat 里各写一遍：桌面端外壳也是 spawn `run.py`，于是
**bat / 命令行 / 桌面端**三条入口共用同一份实现，行为不会走偏。

为什么用"探端口 + 按需启动"而不是每次都起：Ollama 是台共享服务（用户可能还在别处用它），
已经在跑就什么都不做；启动起来也**不跟着本进程退出**（DETACHED），关掉应用不影响它。

起不来时要说清**为什么**（见 `report()`）：`ollama serve` 的输出会写进 `log_path`，
端口被别的进程占着、或它刚起来就退出，都从那份输出里认出来，而不是笼统地说"启动超时"。
"""
import logging
import os
import shutil
import subprocess
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("wonder_realm")

# 只有本机地址才由我们去拉起来：base_url 指向别的机器时，那不是我们能启动的
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
START_TIMEOUT = 30.0  # 冷启动留够时间（首次加载模型前，服务本身通常几秒就绪）
# 就绪探测的间隔：由密到疏（后面的探测都取最后一档）。冷启动那几秒它在读模型目录，
# 探得再密也不会更快就绪，只是在空刷请求——Ollama 每次请求都会在自己日志里留一行。
PROBE_DELAYS = (1.0, 1.5, 2.0, 3.0)
# `ollama serve` 起不来时最常见的两种输出特征（Windows 上是第一句，POSIX 上后两句）
PORT_BUSY_HINTS = (
    "only one usage of each socket address",   # Windows: bind 失败
    "address already in use",
    "bind: ",
)


def _is_local(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "") in LOCAL_HOSTS


def _ping_urls(base_url: str) -> list[str]:
    """要探的地址：就是 base_url；另外 base_url 写的是 localhost 时**再探一次 127.0.0.1** ——
    有些环境里 localhost 先解析到 ::1，而 Ollama 只听 IPv4，于是"明明在跑"却被判成没在跑。"""
    urls = [f"{base_url.rstrip('/')}/api/tags"]
    parsed = urlparse(base_url)
    if parsed.hostname == "localhost":
        urls.append(f"http://127.0.0.1:{parsed.port or 11434}/api/tags")
    return urls


def ping(base_url: str, timeout: float = 1.5) -> bool:
    """`/api/tags` 能返回 200 就算在跑——正是应用随后要用的接口。"""
    for url in _ping_urls(base_url):
        try:
            if httpx.get(url, timeout=timeout).status_code == 200:
                return True
        except httpx.HTTPError:
            continue
    return False


def _read_tail(path, limit: int = 4000) -> str:
    """读日志尾巴（起不来时原因就在最后几行）。读不到就返回空串。"""
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            data = f.read()[-limit:]
        return data.decode("utf-8", "replace").lower()
    except OSError:
        return ""


def _models_dir(exe: str | None = None) -> str | None:
    """拉起的 `ollama serve` 该用哪个模型目录。

    默认是 `%USERPROFILE%\\.ollama\\models`；但**装在别处的 Ollama（例如 D:\\Ollama）会把 models
    放在自己旁边**，托盘应用知道这件事、我们 spawn 出来的 serve 不知道 —— 于是就会出现
    "服务起来了、模型列表却是空的"，用户看着就是"Ollama 没启动 / 没有可用模型"。
    （真踩过：测试时拉起的实例占着 11434 用空目录，而用户真正的模型在 `D:\\Ollama\\models`。）

    顺序：环境变量 `OLLAMA_MODELS` > exe 旁边的 `models`（且里面真有 manifests）> 不动它。
    返回 None 表示"别设，让 ollama 用默认"。
    """
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return env
    exe = exe or shutil.which("ollama")
    if exe:
        cand = os.path.join(os.path.dirname(os.path.abspath(exe)), "models")
        manifests = os.path.join(cand, "manifests")
        try:
            if os.path.isdir(manifests) and os.listdir(manifests):
                return cand
        except OSError:
            pass
    return None


def _spawn_serve(log_path=None):
    """后台拉起 `ollama serve`。找不到可执行文件时抛 FileNotFoundError，由调用方决定怎么说。

    输出（含出错原因）追加进 `log_path`：起不来时那一行就是答案。
    """
    out = None
    if log_path:
        try:
            out = open(log_path, "ab")
        except OSError:
            out = None
    env = dict(os.environ)
    models = _models_dir()
    if models:
        env["OLLAMA_MODELS"] = models   # 让拉起来的服务看到用户真正的模型（见 _models_dir）
        log.info("拉起 ollama serve 时使用模型目录：%s", models)
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):  # Windows：脱离本进程与它的控制台
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(
            ["ollama", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=out or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if out else subprocess.DEVNULL,
            env=env,
            creationflags=flags,
            start_new_session=not flags,  # POSIX：另开会话，同样脱离父进程
            close_fds=True,
        )
    finally:
        if out:
            out.close()   # 子进程自己持有这个句柄，父进程这份可以关掉


def ensure_ollama(
    base_url: str,
    auto_start: bool = True,
    timeout: float = START_TIMEOUT,
    probe=ping,
    spawn=None,
    log_path=None,
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
    spawn = spawn or (lambda: _spawn_serve(log_path))
    try:
        proc = spawn()
    except FileNotFoundError:
        return "skipped-missing"
    except OSError as e:  # 权限/被拦等：不该让整个启动失败，界面里还会照常提示连不上
        log.warning("拉起 ollama serve 失败：%s", e)
        return "skipped-missing"
    deadline = time.monotonic() + timeout
    step = 0
    while True:
        # 剩下的时间不够下一档间隔时，就把最后一觉缩短到刚好用满，别越过 deadline
        delay = PROBE_DELAYS[min(step, len(PROBE_DELAYS) - 1)]
        left = deadline - time.monotonic()
        if left <= 0:
            return "started-timeout"
        time.sleep(min(delay, left))
        step += 1
        if probe(base_url):
            return "started"
        # 进程中途退出就别再空等一轮超时了：端口被占 / 立刻报错，都从它的输出里认出来
        if proc is not None and proc.poll() is not None:
            return "blocked-port" if _looks_like_port_busy(log_path) else "serve-exited"


def _looks_like_port_busy(log_path) -> bool:
    tail = _read_tail(log_path)
    return any(h in tail for h in PORT_BUSY_HINTS)


def report(status: str, base_url: str) -> str:
    """把状态翻成一句打印给人看的话（同一个状态只在这里定义文案）。"""
    return {
        "running": f"Ollama 已在运行（{base_url}）",
        "started": f"Ollama 之前没在运行，已顺手启动（{base_url}）",
        "started-timeout": "已尝试启动 Ollama，但它还没就绪；界面里若提示连不上，稍等片刻或手动执行 ollama serve",
        "blocked-port": "11434 端口被占着但连不上（Ollama 多半卡住了）：请在托盘里退出 Ollama，"
                        "再从开始菜单重新打开；详细原因见 data/ollama-serve.log",
        "serve-exited": "ollama serve 刚起来就退出了，没起来：原因见 data/ollama-serve.log，"
                        "也可以自己执行 ollama serve 看它报什么",
        "skipped-disabled": "按配置跳过了 Ollama 自启（ollama.auto_start: false）",
        "skipped-remote": f"Ollama 不在本机（{base_url}），不自启",
        "skipped-missing": "没找到 ollama 命令，无法自启：请先安装 Ollama（https://ollama.com/download），装好后重开应用即可",
    }.get(status, status)
