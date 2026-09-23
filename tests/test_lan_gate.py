"""局域网闸门：开关关掉时非本机来源一律 403，本机永远放行；开关只有本机能改。

用临时库 + TestClient，绝不碰 data/ 下的真实库。
TestClient 的默认来源是 "testclient"（不是回环），所以它天然扮演"局域网来客"；
扮演本机时用 `client=("127.0.0.1", 12345)` 这个 TestClient 参数。

跑法：uv run python tests/test_lan_gate.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.config import load_config  # noqa: E402
from app.main import _lan_forbidden, is_loopback  # noqa: E402
from app.net import LOOPBACK  # noqa: E402
from app.routes import settings as settings_routes  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


class FakeClient:
    def __init__(self, host):
        self.host = host


# ---- 1. 回环判定 ----
check("回环地址都认", [is_loopback(FakeClient(h)) for h in sorted(LOOPBACK)], [True] * len(LOOPBACK))
check("局域网地址不算本机",
      [is_loopback(FakeClient(h)) for h in ("192.168.1.23", "10.0.0.5", "172.17.0.1")], [False] * 3)
check("拿不到来源时按“不是本机”处理（保守）", is_loopback(None), False)

# ---- 2. 配置里的首次默认值 ----
check("config 里 lan 默认关", load_config()["server"]["lan"], False)

tmp = Path(".test_lan_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), "", "")

# ---- 3. 新库默认关；可以在建库时给默认值 ----
check("新库默认不推送局域网", database.read_settings()["lan_enabled"], False)
check("读设置里带这个开关", "lan_enabled" in database.read_settings(), True)

tmp2 = Path(".test_lan_tmp2").resolve()
shutil.rmtree(tmp2, ignore_errors=True)
tmp2.mkdir()
database.init_db(str(tmp2), "", "", default_lan=True)
check("建库时可以指定首次默认值（config 里 lan: true 的路径）",
      database.read_settings()["lan_enabled"], True)

# ---- 4. 闸门：本机放行、局域网看开关 ----
database.init_db(str(tmp), "", "")  # 切回默认关的库
database.write_lan_enabled(False)
gate = FastAPI()


@gate.middleware("http")
async def lan_gate(request, call_next):
    """与 app.main 里那道闸门同一套判据（这里只装它，不装整个应用）。"""
    from app.database import lan_enabled

    if not lan_enabled() and not is_loopback(request.client):
        return _lan_forbidden(request.url.path)
    return await call_next(request)


@gate.get("/api/ping")
def ping():
    return {"ok": True}


@gate.get("/")
def page():
    return {"page": True}


lan_client = TestClient(gate)                       # 默认来源 "testclient" = 局域网来客
local_client = TestClient(gate, client=("127.0.0.1", 12345))

r = lan_client.get("/api/ping")
check("开关关掉：局域网来客拿 403（接口回 JSON）",
      (r.status_code, r.json()["detail"].startswith("电脑端当前没有开启局域网访问")), (403, True))
r = lan_client.get("/")
check("开关关掉：局域网来客打开页面拿到一段人话，而不是一串 JSON",
      (r.status_code, "未开启局域网访问" in r.text, r.headers["content-type"].startswith("text/html")),
      (403, True, True))
check("开关关掉：本机照样能用", local_client.get("/api/ping").json(), {"ok": True})

database.write_lan_enabled(True)
check("开关打开：局域网来客放行", lan_client.get("/api/ping").json(), {"ok": True})
check("开关打开：页面也放行", lan_client.get("/").json(), {"page": True})
database.write_lan_enabled(False)
check("再关回去：立刻 403（不用重启）", lan_client.get("/api/ping").status_code, 403)

# ---- 5. 设置接口：开关只有本机能改 ----
app = FastAPI()
app.include_router(settings_routes.router)
app.state.database_url = tmp
lan = TestClient(app)
local = TestClient(app, client=("127.0.0.1", 12345))

r = lan.put("/api/settings", json={"lan_enabled": True})
check("局域网来客改不了这个开关（403）", (r.status_code, "只有这台电脑" in r.json()["detail"]), (403, True))
check("局域网来客改不成，库里仍是关", database.read_settings()["lan_enabled"], False)

r = local.put("/api/settings", json={"lan_enabled": True})
check("本机可以打开它", (r.status_code, r.json()["lan_enabled"]), (200, True))
r = local.put("/api/settings", json={"lan_enabled": False})
check("本机可以关掉它", r.json()["lan_enabled"], False)
check("切开关不误伤别的偏好",
      local.put("/api/settings", json={"disable_thinking": True}).json(),
      {"model": "", "memory_model": "", "disable_thinking": True, "lan_enabled": False})
check("什么都不传仍然 400", local.put("/api/settings", json={}).status_code, 400)

# ---- 6. 老库补列：老库没有 lan_enabled 时补上并默认关 ----
tmp3 = Path(".test_lan_tmp3").resolve()
shutil.rmtree(tmp3, ignore_errors=True)
tmp3.mkdir()
database.init_db(str(tmp3), "", "")
con = database.connect()
con.execute("ALTER TABLE app_settings DROP COLUMN lan_enabled")  # 造一个"老库"
con.commit()
con.close()
database.init_db(str(tmp3), "", "")
check("老库补列后默认关", database.read_settings()["lan_enabled"], False)
con = database.connect()
check("补出来的列确实在表里",
      "lan_enabled" in {r[1] for r in con.execute("PRAGMA table_info(app_settings)")}, True)
con.close()

for path in (tmp, tmp2, tmp3):
    shutil.rmtree(path, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("局域网闸门用例全部通过")
