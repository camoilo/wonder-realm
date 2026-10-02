"""局域网安全：开关 + 访问码 + Host 校验（见 DEVELOPMENT §8.3）。

用临时库 + TestClient，绝不碰 data/ 下的真实库。
TestClient 的默认来源是 "testclient"（不是回环），所以它天然扮演"局域网来客"；
扮演本机时用 `client=("127.0.0.1", 12345)` 这个 TestClient 参数。

Host 头同理：TestClient 默认发 `testserver`（一个域名），会被 Host 校验挡下——
所以这里的请求都显式带 Host，与手机上打开 `http://<局域网IP>:17800` 时一致。

跑法：uv run python tests/test_lan_gate.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, lan_auth  # noqa: E402
from app.config import load_config  # noqa: E402
from app.lan_gate import after as gate_after  # noqa: E402
from app.lan_gate import before as gate_before  # noqa: E402
from app.net import LOOPBACK, host_ok, is_loopback, local_hosts  # noqa: E402
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

# ---- 2. Host 校验：只认本机自己的地址/名字（防 DNS rebinding）----
def _local_ipv4() -> str:
    """本机的一个真实 IPv4（手机就是用它访问的）；取不到就退回回环。"""
    for h in sorted(local_hosts()):
        if h.count(".") == 3 and h.replace(".", "").isdigit() and not h.startswith("127."):
            return h
    return "127.0.0.1"


LOCAL_HOST = "127.0.0.1:17800"
# 局域网来客的 Host：机器自己的地址（来源地址在 TestClient 里是 "testclient"，不是回环）
LAN_HOST = f"{_local_ipv4()}:17800"
check("回环写法都认", [host_ok(h) for h in
                     ("127.0.0.1:17800", "localhost:17800", "[::1]:17800", "localhost")],
      [True] * 4)
check("本机自己的地址与名字认（手机就是用局域网 IP 访问的）",
      [host_ok(LAN_HOST), host_ok(local_hosts() and f"{_local_ipv4()}:17800")], [True, True])
check("恶意域名挡下（rebinding 靠的就是它）",
      [host_ok(h) for h in ("evil.com:17800", "evil.com", "192.168.1.99:17800", "")],
      [False] * 4)

# ---- 3. 访问码本身：字母表、长度、宽容比对 ----
code = lan_auth.new_code()
check("访问码长度固定", len(code), lan_auth.CODE_LEN)
check("访问码不含易混字符（0 O 1 I L 都不出现）",
      any(c in code for c in "0O1IL"), False)
check("手输宽容：大小写 / 连字符 / 空格都不影响",
      lan_auth.matches("K7F2-9QX3", " k7f29qx3 "), True)
check("码不对就不认", lan_auth.matches("K7F29QX3", "K7F29QX4"), False)
check("库里没码时一律不认（关闸门时的状态）", lan_auth.matches("", ""), False)
for _ in range(lan_auth.FAIL_LIMIT):
    lan_auth.note_fail("1.2.3.4")
check("限速：错够次数后判为太多", lan_auth.too_many_fails("1.2.3.4"), True)
lan_auth.clear_fails("1.2.3.4")
check("清掉失败记录后又可以试", lan_auth.too_many_fails("1.2.3.4"), False)

# ---- 4. 配置里的首次默认值 ----
check("config 里 lan 默认关", load_config()["server"]["lan"], False)

tmp = Path(".test_lan_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), "", "")

# ---- 5. 新库默认关、没有访问码；可以在建库时给默认值 ----
check("新库默认不推送局域网", database.read_settings()["lan_enabled"], False)
check("读设置里带开关与访问码",
      [k in database.read_settings() for k in ("lan_enabled", "lan_token")], [True, True])
check("新库没有访问码（关着就不该有）", database.read_settings()["lan_token"], "")

tmp2 = Path(".test_lan_tmp2").resolve()
shutil.rmtree(tmp2, ignore_errors=True)
tmp2.mkdir()
database.init_db(str(tmp2), "", "", default_lan=True)
check("建库时可以指定首次默认值（config 里 lan: true 的路径）",
      database.read_settings()["lan_enabled"], True)

# ---- 6. 闸门：本机放行、局域网看开关与访问码 ----
database.init_db(str(tmp), "", "")  # 切回默认关的库
database.write_lan_enabled(False)
gate = FastAPI()


@gate.middleware("http")
async def lan_gate(request, call_next):
    """与 app.main 里那道闸门同一套判据（这里只装它，不装整个应用）。"""
    blocked = gate_before(request)
    if blocked is not None:
        return blocked
    return gate_after(request, await call_next(request))


@gate.get("/api/ping")
def ping():
    return {"ok": True}


@gate.get("/")
def page():
    return {"page": True}


H = {"host": LOCAL_HOST}
lan_client = TestClient(gate)                       # 默认来源 "testclient" = 局域网来客
local_client = TestClient(gate, client=("127.0.0.1", 12345))

r = lan_client.get("/api/ping", headers={"host": LAN_HOST})
check("开关关掉：局域网来客拿 403（接口回 JSON）",
      (r.status_code, r.json()["detail"].startswith("电脑端当前没有开启局域网访问")), (403, True))
r = lan_client.get("/", headers={"host": LAN_HOST})
check("开关关掉：局域网来客打开页面拿到一段人话，而不是一串 JSON",
      (r.status_code, "未开启局域网访问" in r.text, r.headers["content-type"].startswith("text/html")),
      (403, True, True))
check("开关关掉：本机照样能用", local_client.get("/api/ping", headers=H).json(), {"ok": True})
check("Host 不对：本机来源也被挡（这正是 rebinding 的样子）",
      local_client.get("/api/ping", headers={"host": "evil.com:17800"}).status_code, 403)
r = lan_client.get("/", headers={"host": "evil.com:17800"})
check("Host 不对：页面也给一段人话", (r.status_code, "Host" in r.text), (403, True))

database.write_lan_enabled(True)
database.write_lan_token("")
check("开了开关但库里没码：一律不放行（不给「空码」开后门）",
      lan_client.get("/api/ping", headers={"host": LAN_HOST}).status_code, 401)

good = lan_auth.new_code()
database.write_lan_token(good)
r = lan_client.get("/api/ping", headers={"host": LAN_HOST})
check("开着但没带码：接口 401", (r.status_code, r.json()["detail"].startswith("需要访问码")),
      (401, True))
r = lan_client.get("/", headers={"host": LAN_HOST})
check("开着但没带码：页面是「输入访问码」（含输入框，不加载外部资源）",
      (r.status_code, "/api/lan/claim" in r.text, "输入访问码" in r.text, "<link" not in r.text),
      (401, True, True, True))
check("带错码：还是 401",
      lan_client.get("/api/ping", headers={"host": LAN_HOST, "x-lan-token": "AAAA"}).status_code, 401)
check("带对码：放行", lan_client.get("/api/ping", headers={"host": LAN_HOST, "x-lan-token": good}).json(),
      {"ok": True})
check("Cookie 里的码也对（手机首次之后就靠它）",
      lan_client.get("/api/ping", headers={"host": LAN_HOST},
                     cookies={lan_auth.COOKIE_NAME: good}).json(), {"ok": True})

r = lan_client.get(f"/?k={good}", headers={"host": LAN_HOST}, follow_redirects=False)
check("页面带着码进来：换成 Cookie 并把 URL 里的码擦掉",
      (r.status_code, r.headers["location"].endswith("/"), "k=" not in r.headers["location"],
       lan_auth.COOKIE_NAME in r.headers.get("set-cookie", "")),
      (302, True, True, True))
r = lan_client.get(f"/api/ping?k={good}", headers={"host": LAN_HOST})
check("接口带着码进来：也顺手写进 Cookie",
      (r.json(), lan_auth.COOKIE_NAME in r.headers.get("set-cookie", "")), ({"ok": True}, True))
check("开关打开：本机当然还是放行", local_client.get("/api/ping", headers=H).json(), {"ok": True})

database.write_lan_enabled(False)
check("再关回去：立刻 401（不用重启，码还留着但闸门已关）",
      lan_client.get("/api/ping", headers={"host": LAN_HOST,
                                           "x-lan-token": good}).status_code, 403)
database.write_lan_token("")
check("关掉后码也清了：连带着旧 Cookie 一起作废",
      lan_client.get("/api/ping", headers={"host": LAN_HOST},
                     cookies={lan_auth.COOKIE_NAME: good}).status_code, 403)

# ---- 7. 领码与换码接口 ----
app = FastAPI()
app.include_router(settings_routes.router)
app.state.database_url = tmp


@app.middleware("http")
async def app_gate(request, call_next):
    blocked = gate_before(request)
    if blocked is not None:
        return blocked
    return gate_after(request, await call_next(request))


lan = TestClient(app)
local = TestClient(app, client=("127.0.0.1", 12345))

check("关着时局域网来客改不了这道闸门（在闸门那一步就被挡回去）",
      lan.put("/api/settings", json={"lan_enabled": True}, headers={"host": LAN_HOST}).status_code, 403)

r = local.put("/api/settings", json={"lan_enabled": True}, headers=H)
check("本机可以打开它（并顺手生成访问码）", (r.status_code, r.json()["lan_enabled"]), (200, True))
first = r.json()["lan_token"]
check("打开时生成的码是合格的", (len(first) == lan_auth.CODE_LEN, lan_auth.matches(first, first)),
      (True, True))
check("再打开一次（幂等）不会把手机踢下线",
      local.put("/api/settings", json={"lan_enabled": True}, headers=H).json()["lan_token"], first)

# 带着有效访问码进来（闸门放行）之后，路由自己那条判据还得挡住它：闸门开关只有本机能改
r = lan.put("/api/settings", json={"lan_enabled": False},
            headers={"host": LAN_HOST, "x-lan-token": first})
check("带码进来的局域网来客也改不了这道闸门（403）",
      (r.status_code, "只有这台电脑" in r.json()["detail"]), (403, True))
check("没被改掉，库里仍然是开", database.read_settings()["lan_enabled"], True)

r = lan.post("/api/lan/claim", json={"code": "AAAA"}, headers={"host": LAN_HOST})
check("手机输错码：401", (r.status_code, r.json()["detail"]), (401, "访问码不对"))
for _ in range(lan_auth.FAIL_LIMIT):
    lan.post("/api/lan/claim", json={"code": "BBBB"}, headers={"host": LAN_HOST})
r = lan.post("/api/lan/claim", json={"code": first}, headers={"host": LAN_HOST})
check("错太多次：连对的码也先拦下来（429）", r.status_code, 429)
lan_auth.clear_fails("testclient")

r = lan.post("/api/lan/claim", json={"code": f"{first[:4].lower()}-{first[4:].lower()}"},
             headers={"host": LAN_HOST})
check("对的码（大小写/连字符随便写）：发一张 Cookie",
      (r.status_code, r.json(), lan_auth.COOKIE_NAME in r.headers.get("set-cookie", "")),
      (200, {"ok": True}, True))

r = lan.post("/api/lan/regenerate", headers={"host": LAN_HOST})
check("局域网来客不能换码（换了就等于抢走钥匙）", r.status_code, 403)
r = local.post("/api/lan/regenerate", headers=H)
second = r.json()["lan_token"]
check("本机换码：换出一个新的", (r.status_code, second != first, len(second) == lan_auth.CODE_LEN),
      (200, True, True))
check("换码后旧码立刻失效",
      lan.get("/api/limits", headers={"host": LAN_HOST, "x-lan-token": first}).status_code, 401)

check("切开关不误伤别的偏好",
      local.put("/api/settings", json={"disable_thinking": True}, headers=H).json(),
      {"model": "", "memory_model": "", "disable_thinking": True, "lan_enabled": True,
       "lan_token": second})
r = local.put("/api/settings", json={"lan_enabled": False}, headers=H)
check("本机可以关掉它（并清掉访问码）", (r.json()["lan_enabled"], r.json()["lan_token"]),
      (False, ""))
check("什么都不传仍然 400", local.put("/api/settings", json={}, headers=H).status_code, 400)

# ---- 8. 老库补列：老库没有这两列时补上并给默认值 ----
tmp3 = Path(".test_lan_tmp3").resolve()
shutil.rmtree(tmp3, ignore_errors=True)
tmp3.mkdir()
database.init_db(str(tmp3), "", "")
con = database.connect()
con.execute("ALTER TABLE app_settings DROP COLUMN lan_enabled")  # 造一个"老库"
con.execute("ALTER TABLE app_settings DROP COLUMN lan_token")
con.commit()
con.close()
database.init_db(str(tmp3), "", "")
check("老库补列后默认关、也没有码",
      (database.read_settings()["lan_enabled"], database.read_settings()["lan_token"]), (False, ""))
con = database.connect()
have = {r[1] for r in con.execute("PRAGMA table_info(app_settings)")}
con.close()
check("补出来的列确实在表里", [c in have for c in ("lan_enabled", "lan_token")], [True, True])

for path in (tmp, tmp2, tmp3):
    shutil.rmtree(path, ignore_errors=True)

# ---- 9. 启动行为：每次启动都把开关写回"关闭"（见 DEVELOPMENT §8.3）----
run_src = (Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8")
check("启动时无条件写回局域网开关（不再只在带 --lan/--no-lan 时）",
      'if "--lan" in args or "--no-lan" in args:' not in run_src
      and 'database.write_lan_enabled("--lan" in args)' in run_src, True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("局域网安全用例全部通过")
