"""我的设定：预设库（复用 user_profiles，id=1 是当前设定、id>1 是预设）与"没选模型"的行为。

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
    "SELECT COUNT(*) FROM user_profiles").fetchone()[0], 1)
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
r = client.put("/api/profile", json={"name": "小林", "call_name": "小林林",
                                     "identity": "见习侦探", "appearance": "短发", "avatar": AV})
check("保存当前设定", r.json()["name"], "小林")
# 名字只给自己看、称呼才是给模型用的（见 DEVELOPMENT §2.3）：两个字段都要存得住
check("称呼与名字分开存", r.json()["call_name"], "小林林")

r = client.post("/api/profile/presets", json={"name": "阿澈", "call_name": "澈哥",
                                              "identity": "游侠",
                                              "appearance": "青衫", "avatar": AV})
check("存为预设 200", r.status_code, 200)
p1 = r.json()
check("预设带 id 与头像", (p1["id"] > 1, p1["avatar"] == AV), (True, True))
check("预设也带称呼", p1["call_name"], "澈哥")
p2 = client.post("/api/profile/presets", json={"name": "小满", "identity": "学生"}).json()

presets = client.get("/api/profile/presets").json()
check("列表里两条", len(presets), 2)
check("新的排前面", [p["name"] for p in presets][:1], ["小满"])
check("当前设定不在预设里", "小林" in [p["name"] for p in presets], False)
check("存预设不影响当前设定", client.get("/api/profile").json()["name"], "小林")
check("当前设定仍只有一行", database.connect().execute(
    "SELECT COUNT(*) FROM user_profiles WHERE id=1").fetchone()[0], 1)

check("名字为空拒绝存预设", client.post("/api/profile/presets", json={"name": "  "}).status_code, 400)

# ---- 2b. 老库迁移：user_profiles 本来没有 call_name 这一列（见 database._COLUMN_MIGRATIONS） ----
# 这一步必须单独验：老用户升级时走的就是"建表语句是 IF NOT EXISTS、新列靠迁移补"这条路，
# 迁移漏了的话应用一起来就报 no such column（真踩过这类）。
import sqlite3  # noqa: E402

old = Path(".test_profile_old").resolve()
shutil.rmtree(old, ignore_errors=True)
old.mkdir()
old_db = old / "chatbot.db"
con = sqlite3.connect(old_db)
con.execute(
    "CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', "
    "identity TEXT NOT NULL DEFAULT '', appearance TEXT NOT NULL DEFAULT '', "
    "avatar TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)"
)
con.execute("INSERT INTO user_profiles(id, name, identity, appearance, avatar, updated_at) "
            "VALUES(1, '旧名字', '旧身份', '', '', '2020-01-01')")
con.commit()
con.close()
database.init_db(str(old), "", "")
cols = [r[1] for r in database.connect().execute("PRAGMA table_info(user_profiles)")]
check("老库补上了 call_name 列", "call_name" in cols, True)
check("老库的 name 保持原样（不当成称呼）",
      database.read_profile()["name"], "旧名字")
check("老库的称呼留空（由用户自己填）", database.read_profile()["call_name"], "")
shutil.rmtree(old, ignore_errors=True)
# 迁移检查把 DB_PATH 指到了老库上，这里**指回前面那个临时库**，后面的用例继续跑
database.init_db(str(tmp), cfg["ollama"]["model"], "")

# ---- 3b. 覆盖保存已有预设（面板上选中某条后按钮变成「保存预设」）----
r = client.put(f"/api/profile/presets/{p2['id']}",
               json={"name": "小满", "identity": "转学生", "appearance": "短发", "avatar": AV})
check("覆盖保存 200", r.status_code, 200)
check("覆盖后内容变了", (r.json()["identity"], r.json()["appearance"]), ("转学生", "短发"))
check("覆盖后头像也换", r.json()["avatar"], AV)
check("覆盖不新增条目", len(client.get("/api/profile/presets").json()), 2)
check("覆盖保持同一条 id", [p["id"] for p in client.get("/api/profile/presets").json()
                          if p["name"] == "小满"], [p2["id"]])
check("覆盖预设不影响当前设定", client.get("/api/profile").json()["identity"], "见习侦探")
check("覆盖时名字为空被拒",
      client.put(f"/api/profile/presets/{p2['id']}", json={"name": " "}).status_code, 400)
check("覆盖不存在的预设 404",
      client.put("/api/profile/presets/999", json={"name": "x"}).status_code, 404)
check("覆盖 id=1（当前设定）被拒",
      client.put("/api/profile/presets/1", json={"name": "x"}).status_code, 404)
check("覆盖仍受名字上限约束",
      client.put(f"/api/profile/presets/{p2['id']}",
                 json={"name": "字" * 21}).status_code, 422)

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
con.execute("DELETE FROM user_profiles WHERE id>1")
con.commit()
con.close()
check("没有预设时列表为空", client.get("/api/profile/presets").json(), [])

# ---- 5. 预设绑定角色（characters.profile_id）----
# 一份预设可以给多个角色用，绑定记在角色那侧；读法是"身份跟着角色走"（DEVELOPMENT §2.3）
from app.routes import characters as character_routes  # noqa: E402

app.include_router(character_routes.router)

p_a = client.post("/api/profile/presets", json={"name": "侠客", "identity": "行走江湖"}).json()
p_b = client.post("/api/profile/presets", json={"name": "学生", "identity": "高二"}).json()
c1 = client.post("/api/characters", json={"name": "阿岚"}).json()
c2 = client.post("/api/characters", json={"name": "小满"}).json()
check("新建角色默认不绑定", (c1["profile_id"], c2["profile_id"]), (None, None))

r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚", "profile_id": p_a["id"]})
check("给角色绑定预设", r.json()["profile_id"], p_a["id"])
client.put(f"/api/characters/{c2['id']}", json={"name": "小满", "profile_id": p_a["id"]})

by_id = {p["id"]: p for p in client.get("/api/profile/presets").json()}
check("一条预设可以绑多个角色",
      [c["name"] for c in by_id[p_a["id"]]["characters"]], ["阿岚", "小满"])
check("没被绑的预设显示为空", by_id[p_b["id"]]["characters"], [])
check("角色列表也带绑定",
      {c["name"]: c["profile_id"] for c in client.get("/api/characters").json()},
      {"阿岚": p_a["id"], "小满": p_a["id"]})

# 面板保存角色设定时提交的是面板表单（不含 profile_id）——那不能被当成"解绑"
r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚改", "appearance": "黑衣"})
check("不改绑定就不动它（列表表单没带这一项）", r.json()["profile_id"], p_a["id"])
r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚改", "profile_id": None})
check("显式传 null 才是解绑", r.json()["profile_id"], None)

check("绑定不存在的预设被拒",
      client.put(f"/api/characters/{c1['id']}",
                 json={"name": "阿岚", "profile_id": 999}).status_code, 400)
check("不能绑到 id=1（那是当前设定，不是预设）",
      client.put(f"/api/characters/{c1['id']}",
                 json={"name": "阿岚", "profile_id": 1}).status_code, 400)
# 锁定只锁角色的隐藏设定，不影响"我用哪份身份"（直接把角色置为锁定的探索模式）
con = database.connect()
con.execute("UPDATE characters SET locked=1 WHERE id=?", (c2["id"],))
con.commit()
con.close()
r = client.put(f"/api/characters/{c2['id']}",
               json={"name": "小满", "profile_id": p_b["id"], "personality": "不该被写进去"})
check("锁定状态也能改绑定", r.json()["profile_id"], p_b["id"])
check("锁定状态仍然不写隐藏字段", r.json().get("personality"), None)

# 删掉预设：引用了它的角色要一起解绑，不能留下悬空 id
check("删除被引用的预设 200", client.delete(f"/api/profile/presets/{p_b['id']}").status_code, 200)
check("删预设后角色自动解绑",
      [c["profile_id"] for c in client.get("/api/characters").json() if c["id"] == c2["id"]],
      [None])
check("删预设后绑定列表也清空",
      {p["id"]: p["characters"] for p in client.get("/api/profile/presets").json()},
      {p_a["id"]: []})

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("我的设定预设与未选模型用例全部通过")
