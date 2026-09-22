"""我的设定：预设库（复用 user_profile，id=1 是当前设定、id>1 是预设）与"没选模型"的行为。

用临时库 + TestClient，绝不碰 data/ 下的真实库。

跑法：uv run python tests/test_profile.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import database
from app.config import get_config
from app.routes import profile as profile_routes

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


# ---- 1. 配置里不再有默认模型 ----
cfg = get_config()
check("配置默认模型为空", cfg["ollama"]["model"], "")
yaml_text = Path("config.yaml").read_text(encoding="utf-8")
check("config.yaml 里没有写死的模型名", "qwen2.5:3b" in yaml_text, False)

# ---- 2. 新库：模型为空；生成时给明确错误 ----
tmp = Path(".test_preset_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), cfg["ollama"]["model"], "")
check("新库模型为空", database.read_settings()["model"], "")
check("新库有一行当前设定", database.connect().execute(
    "SELECT COUNT(*) FROM user_profile").fetchone()[0], 1)
check("初始没有预设", database.list_presets(), [])

# prepare_generation 在没选模型时应抛 400 而不是把空模型名发出去
from app import generation  # noqa: E402

con = database.connect()
con.execute("INSERT INTO sessions(mode, title, gen_settings, created_at, updated_at) "
            "VALUES('director','t','{}','2026-01-01','2026-01-01')")
con.commit()
try:
    generation.prepare_generation(con, 1)
    check("没选模型时生成被拦下", "没报错", "400")
except HTTPException as e:
    check("没选模型时生成被拦下", (e.status_code, "选择模型" in e.detail), (400, True))
con.close()

# ---- 3. 预设：增 / 列 / 删，且不动 id=1 ----
app = FastAPI()
app.include_router(profile_routes.router)
client = TestClient(app)

AV = "data:image/jpeg;base64,AAAA"
r = client.put("/api/profile", json={"name": "小林", "identity": "见习侦探",
                                     "appearance": "短发", "avatar": AV})
check("保存当前设定", r.json()["name"], "小林")

r = client.post("/api/profile/presets", json={"name": "阿澈", "identity": "游侠",
                                              "appearance": "青衫", "avatar": AV})
check("存为预设 200", r.status_code, 200)
p1 = r.json()
check("预设带 id 与头像", (p1["id"] > 1, p1["avatar"] == AV), (True, True))
p2 = client.post("/api/profile/presets", json={"name": "小满", "identity": "学生"}).json()

presets = client.get("/api/profile/presets").json()
check("列表里两条", len(presets), 2)
check("新的排前面", [p["name"] for p in presets][:1], ["小满"])
check("当前设定不在预设里", "小林" in [p["name"] for p in presets], False)
check("存预设不影响当前设定", client.get("/api/profile").json()["name"], "小林")
check("当前设定仍只有一行", database.connect().execute(
    "SELECT COUNT(*) FROM user_profile WHERE id=1").fetchone()[0], 1)

check("名字为空拒绝存预设", client.post("/api/profile/presets", json={"name": "  "}).status_code, 400)
check("删除预设 200", client.delete(f"/api/profile/presets/{p1['id']}").status_code, 200)
check("删完剩一条", len(client.get("/api/profile/presets").json()), 1)
check("重复删除 404", client.delete(f"/api/profile/presets/{p1['id']}").status_code, 404)
check("删 id=1（当前设定）被拒", client.delete("/api/profile/presets/1").status_code, 404)
check("预设都删完也不影响当前设定", client.get("/api/profile").json()["name"], "小林")
check("预设超长仍受上限约束",
      client.post("/api/profile/presets", json={"name": "字" * 21}).status_code, 422)
check("预设头像仍走白名单",
      client.post("/api/profile/presets",
                  json={"name": "x", "avatar": "data:image/svg+xml;base64,AA"}).status_code, 422)

# ---- 4. 旧库兼容：只有 id=1 的库读起来一切正常 ----
con = database.connect()
con.execute("DELETE FROM user_profile WHERE id>1")
con.commit()
con.close()
check("没有预设时列表为空", client.get("/api/profile/presets").json(), [])

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("我的设定预设与未选模型用例全部通过")
