"""Ollama 自启：只在"没在跑 + 是本机 + 允许自启"时才拉起来，且不跟着应用退出。

跑法：uv run python tests/test_ollama_boot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ollama_boot  # noqa: E402
from app.config import load_config  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


def seq_probe(*answers):
    """按顺序返回答案的假探针，用来模拟"启动后过一会儿才就绪"。"""
    box = list(answers)

    def probe(base_url, timeout=1.5):
        return box.pop(0) if box else False

    return probe


class Spy:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


# ---- 1. 已经在跑：什么都不做 ----
spy = Spy()
check("已经在运行就不去启动",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=lambda *a, **k: True, spawn=spy),
      "running")
check("没有多余地起进程", spy.calls, 0)

# ---- 2. 没在跑：拉起来并等它就绪 ----
spy = Spy()
check("没在跑就拉起来，就绪后返回 started",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=seq_probe(False, False, True),
                                spawn=spy, timeout=5),
      "started")
check("只起了一次", spy.calls, 1)

# ---- 3. 起了但一直没就绪：给个超时状态，而不是永远等 ----
check("起不来就超时返回",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=lambda *a, **k: False,
                                spawn=Spy(), timeout=0.2),
      "started-timeout")

# ---- 4. 没装 Ollama：不该抛出去，交给人话提示 ----
def missing():
    raise FileNotFoundError("ollama")


check("没装 ollama 时返回 skipped-missing（不炸启动）",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=lambda *a, **k: False,
                                spawn=missing),
      "skipped-missing")

# ---- 5. 不该自启的两种情形 ----
spy = Spy()
check("配置里关掉自启就不管它",
      ollama_boot.ensure_ollama("http://localhost:11434", auto_start=False,
                                probe=lambda *a, **k: False, spawn=spy),
      "skipped-disabled")
check("关掉时一次都没起", spy.calls, 0)
spy = Spy()
check("远端 Ollama 不由本机自启",
      ollama_boot.ensure_ollama("http://192.168.1.50:11434", probe=lambda *a, **k: False, spawn=spy),
      "skipped-remote")
check("远端时也没起进程", spy.calls, 0)

# ---- 6. 本机地址判定（只有这些才自启）----
check("本机地址认得全",
      [ollama_boot._is_local(u) for u in (
          "http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434",
          "http://0.0.0.0:11434")], [True] * 4)
check("非本机地址不认",
      [ollama_boot._is_local(u) for u in (
          "http://192.168.1.50:11434", "http://ollama.lan:11434", "http://10.0.0.9:11434")],
      [False] * 3)

# ---- 7. 文案与配置 ----
check("每种状态都有给人看的文案",
      [bool(ollama_boot.report(s, "http://localhost:11434")) for s in (
          "running", "started", "started-timeout", "skipped-disabled", "skipped-remote",
          "skipped-missing")], [True] * 6)
check("没装 Ollama 的提示里给出下载地址",
      "ollama.com/download" in ollama_boot.report("skipped-missing", "http://localhost:11434"), True)
check("配置默认开启自启", load_config()["ollama"]["auto_start"], True)

# ---- 8. 真探针在本机跑一遍（只读：Ollama 在跑就该返回 True）----
check("真探针不会误报（拿一个必然连不上的端口）",
      ollama_boot.ping("http://127.0.0.1:1", timeout=0.5), False)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("Ollama 自启用例全部通过")
