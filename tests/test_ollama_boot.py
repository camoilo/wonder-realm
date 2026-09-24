"""Ollama 自启：只在"没在跑 + 是本机 + 允许自启"时才拉起来，且不跟着应用退出。

跑法：uv run python tests/test_ollama_boot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shutil  # noqa: E402

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
          "running", "started", "started-timeout", "blocked-port", "serve-exited",
          "skipped-disabled", "skipped-remote", "skipped-missing")], [True] * 8)
check("没装 Ollama 的提示里给出下载地址",
      "ollama.com/download" in ollama_boot.report("skipped-missing", "http://localhost:11434"), True)
check("端口被占 / 起不来时指向那份日志",
      all("ollama-serve.log" in ollama_boot.report(s, "http://localhost:11434")
          for s in ("blocked-port", "serve-exited")), True)
check("配置默认开启自启", load_config()["ollama"]["auto_start"], True)

# ---- 8. 探针地址：localhost 要再探一次 127.0.0.1 ----
# （有些环境 localhost 先解析到 ::1，而 Ollama 只听 IPv4 —— 那时会"明明在跑却被判成没跑"，
#   于是白白去拉一次、还撞上端口占用）
check("localhost 会补探 IPv4",
      ollama_boot._ping_urls("http://localhost:11434"),
      ["http://localhost:11434/api/tags", "http://127.0.0.1:11434/api/tags"])
check("非 localhost 不补",
      ollama_boot._ping_urls("http://192.168.1.50:11434"),
      ["http://192.168.1.50:11434/api/tags"])
check("自定端口的 localhost 也按端口补",
      ollama_boot._ping_urls("http://localhost:11499")[1], "http://127.0.0.1:11499/api/tags")

# ---- 9. serve 刚起就退出：从它的输出认出"端口被占"，给出能照做的提示 ----
class DeadProc:
    """假装是个立刻退出的子进程（poll() 返回退出码）。"""

    def poll(self):
        return 1


def spawn_dead():
    return DeadProc()


tmp = Path(__file__).resolve().parent / ".test_ollama_tmp"
tmp.mkdir(exist_ok=True)
busy_log = tmp / "busy.log"
busy_log.write_text(
    "Error: listen tcp 127.0.0.1:11434: bind: Only one usage of each socket address "
    "is normally permitted.\n", encoding="utf-8")
quiet_log = tmp / "quiet.log"
quiet_log.write_text("panic: something else\n", encoding="utf-8")

check("端口被占：认得出 blocked-port",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=lambda *a, **k: False,
                                spawn=spawn_dead, timeout=5, log_path=busy_log),
      "blocked-port")
check("输出里没有端口线索：算 serve-exited",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=lambda *a, **k: False,
                                spawn=spawn_dead, timeout=5, log_path=quiet_log),
      "serve-exited")
check("进程活着就继续等（不会误判成退出）",
      ollama_boot.ensure_ollama("http://localhost:11434", probe=seq_probe(False, True),
                                spawn=lambda: type("P", (), {"poll": lambda self: None})(),
                                timeout=5, log_path=busy_log),
      "started")
for f in (busy_log, quiet_log):
    f.unlink(missing_ok=True)
tmp.rmdir()

# ---- 10. 模型目录：拉起的 serve 必须看到用户真正的模型 ----
# 踩过的坑：Ollama 装在 D:\Ollama（模型在 D:\Ollama\models），而默认目录 %USERPROFILE%\.ollama\models
# 是空的 —— 自动拉起的服务于是"起来了但没有模型"，用户看着就是"Ollama 没启动"。
import os  # noqa: E402
import tempfile  # noqa: E402

# 临时目录放仓库里的 .test_*_tmp（.gitignore 已忽略）：系统临时目录在沙箱里写不进去
tmp_models = Path(__file__).resolve().parent / ".test_ollama_tmp_models"
tmp_models.mkdir(exist_ok=True)
# 不必真叫 .exe：_models_dir 只看它所在的目录
fake_exe = tmp_models / "fake-ollama"
fake_exe.write_bytes(b"")
# 情况 A：exe 旁边有 models/manifests 且有内容 → 认它
(tmp_models / "models" / "manifests" / "library").mkdir(parents=True)
(tmp_models / "models" / "manifests" / "library" / "x").write_bytes(b"")
saved = os.environ.pop("OLLAMA_MODELS", None)
check("认 exe 旁边的 models 目录",
      ollama_boot._models_dir(str(fake_exe)), str(tmp_models / "models"))
# 情况 B：环境变量优先
os.environ["OLLAMA_MODELS"] = r"E:\somewhere\models"
check("环境变量优先", ollama_boot._models_dir(str(fake_exe)), r"E:\somewhere\models")
if saved is not None:
    os.environ["OLLAMA_MODELS"] = saved
else:
    os.environ.pop("OLLAMA_MODELS", None)
# 情况 C：exe 旁边没有 models → 不设（用 ollama 自己的默认）。注意要用**另一个**目录，
# 否则会看到情况 A 建出来的 models
empty_dir = tmp_models / "empty"
empty_dir.mkdir(exist_ok=True)
check("没有旁挂 models 时返回 None", ollama_boot._models_dir(str(empty_dir / "nope-ollama")), None)

# ---- 11. 界面那个"重试"键要有后端接口兜着 ----
# 自启只在 run.py 启动时做一次；后端本来就在跑（端口被占、run.py 直接退出）而 Ollama 后来挂了时，
# 只有这个接口能把它再拉起来。这里只查路由在不在（调用会真去 ping Ollama，不适合放进用例）。
# 注意：这一版 FastAPI 把 include_router 的结果包成 _IncludedRouter，app.routes 里看不到具体路径，
# 所以从 OpenAPI schema 查（那就是接口清单本身）。
from app.main import app  # noqa: E402

check("有「再确保一次 Ollama」的接口",
      "post" in app.openapi().get("paths", {}).get("/api/ollama/ensure", {}), True)

# ---- 12. 真探针在本机跑一遍（只读：Ollama 在跑就该返回 True）----
check("真探针不会误报（拿一个必然连不上的端口）",
      ollama_boot.ping("http://127.0.0.1:1", timeout=0.5), False)
shutil.rmtree(tmp_models, ignore_errors=True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("Ollama 自启用例全部通过")
