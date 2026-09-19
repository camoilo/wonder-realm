"""角色生成与探索模式锁定（10.29）。

覆盖：锁定时接口真的不下发那三个字段、保存不会清空它们、解锁单向、生成草稿的取舍。
用临时库 + TestClient，绝不碰 data/ 下的真实库。
"""
import asyncio
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import character_gen, database, prompts
from app.routes import characters as char_routes
from app.routes import sessions as sess_routes

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


# 注意不能 import app.main：它在导入时就 create_app()，会按 config 重建真实库
tmp = Path(__file__).resolve().parent.parent / ".test_locked_tmp"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), "fake-model")
assert Path(database.DB_PATH).parent == tmp, database.DB_PATH

app = FastAPI()
app.include_router(char_routes.router)
app.include_router(sess_routes.router)
client = TestClient(app)

HIDDEN = character_gen.HIDDEN_FIELDS
FIELDS = {
    "name": "沈砚",
    "appearance": "二十六岁，青衫，左手有一道旧疤",
    "personality": "寡言但护短，讨厌被同情",
    "speech_style": "句子很短，常用反问",
    "backstory": "曾是镖师，一次失镖后隐居在渡口修船。",
}


async def fake_generate(hint=""):
    """替掉真实模型调用：这里要测的是流程与隐藏，不是模型文笔。"""
    fake_generate.hint = hint
    return dict(FIELDS)


character_gen.generate_character = fake_generate

# ---- 表结构 ----
con = database.connect()
cols = {r[1]: r for r in con.execute("PRAGMA table_info(characters)")}
con.close()
check("characters.locked 存在", "locked" in cols, True)
check("locked 默认 0", str(cols["locked"][4]), "0")

# ---- public_character 裁剪 ----
locked_row = dict(FIELDS, id=1, avatar="", locked=1)
open_row = dict(FIELDS, id=2, avatar="", locked=0)
pl = character_gen.public_character(locked_row)
po = character_gen.public_character(open_row)
check("锁定时隐藏三字段", [k for k in HIDDEN if k in pl], [])
check("锁定时保留姓名/外观", (pl["name"], pl["appearance"]), (FIELDS["name"], FIELDS["appearance"]))
check("锁定时带 locked=True", pl["locked"], True)
check("未锁定时不隐藏", [k for k in HIDDEN if k in po], list(HIDDEN))
check("未锁定时 locked=False", po["locked"], False)
check("裁剪不改动原 row", locked_row["personality"], FIELDS["personality"])

# ---- 生成：开放模式回全部，探索模式只回姓名与外观 ----
r = client.post("/api/characters/generate", json={"hint": "古风女剑客", "mode": "open"})
check("生成(open) 200", r.status_code, 200)
open_draft = r.json()
check("生成(open) 回全部字段", sorted(k for k in open_draft if k in FIELDS), sorted(FIELDS))
check("生成(open) locked=False", open_draft["locked"], False)
check("生成(open) 有 draft_id", len(open_draft["draft_id"]) > 8, True)
check("提示词透传", fake_generate.hint, "古风女剑客")

explore_draft = client.post(
    "/api/characters/generate", json={"hint": "", "mode": "explore"}
).json()
check("生成(explore) 只回姓名/外观", sorted(k for k in explore_draft if k in FIELDS),
      ["appearance", "name"])
check("生成(explore) locked=True", explore_draft["locked"], True)
check("生成(explore) 响应里搜不到隐藏值",
      any(v in json.dumps(explore_draft, ensure_ascii=False)
          for v in (FIELDS["personality"], FIELDS["speech_style"], FIELDS["backstory"])), False)
check("非法 mode 422",
      client.post("/api/characters/generate", json={"mode": "wat"}).status_code, 422)

# ---- 用草稿建角色 ----
created = client.post("/api/characters", json={
    "name": "沈砚", "appearance": "青衫", "avatar": "",
    "personality": "", "speech_style": "", "backstory": "",
    "draft_id": explore_draft["draft_id"],
}).json()
cid = created["id"]
check("建角色响应不含隐藏字段", [k for k in HIDDEN if k in created], [])
check("建角色响应 locked=True", created["locked"], True)
con = database.connect()
row = dict(con.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone())
con.close()
check("探索模式以草稿为准落库（空串提交也覆盖不掉）",
      (row["personality"], row["speech_style"], row["backstory"]),
      (FIELDS["personality"], FIELDS["speech_style"], FIELDS["backstory"]))

oc = client.post("/api/characters", json={
    "name": "陆青", "appearance": "红衣", "personality": "我改过的性格",
    "speech_style": "短句", "backstory": "我改过的背景", "avatar": "",
    "draft_id": open_draft["draft_id"],
}).json()
check("开放模式草稿以请求体为准", oc["personality"], "我改过的性格")
check("开放模式建角色 locked=False", oc["locked"], False)
check("草稿 id 不存在 → 400",
      client.post("/api/characters", json={"name": "无", "draft_id": "deadbeef"}).status_code, 400)
mc = client.post("/api/characters", json={"name": "阿澈", "personality": "手工填的性格"}).json()
check("手工创建 locked=False", mc["locked"], False)
check("手工创建保留字段", mc["personality"], "手工填的性格")

# ---- 所有下发路径都隐藏 ----
lst = {c["id"]: c for c in client.get("/api/characters").json()}
check("列表里锁定角色无隐藏字段", [k for k in HIDDEN if k in lst[cid]], [])
check("列表里未锁定角色有隐藏字段", "personality" in lst[oc["id"]], True)
check("单查锁定角色无隐藏字段",
      [k for k in HIDDEN if k in client.get(f"/api/characters/{cid}").json()], [])

s = client.post("/api/sessions", json={"mode": "character_chat", "character_id": cid,
                                       "title": "测试"}).json()
check("会话详情内嵌角色无隐藏字段", [k for k in HIDDEN if k in s["character"]], [])
sd = client.get(f"/api/sessions/{s['id']}").json()
check("再查会话详情仍无隐藏字段", [k for k in HIDDEN if k in sd["character"]], [])
check("会话详情 locked=True", sd["character"]["locked"], True)

# ---- 锁定时不能改写，也不能清空 ----
r = client.put(f"/api/characters/{cid}", json={
    "name": "沈砚改名", "appearance": "白衣", "avatar": "",
    "personality": "试图覆盖", "speech_style": "试图覆盖", "backstory": "试图覆盖",
})
check("锁定时 PUT 200", r.status_code, 200)
check("锁定时 PUT 响应仍隐藏", [k for k in HIDDEN if k in r.json()], [])
con = database.connect()
row = dict(con.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone())
con.close()
check("锁定时公开字段已更新", (row["name"], row["appearance"]), ("沈砚改名", "白衣"))
check("锁定时隐藏字段未被覆盖", row["personality"], FIELDS["personality"])

client.put(f"/api/characters/{cid}", json={"name": "沈砚", "appearance": "白衣",
                                           "personality": "", "speech_style": "", "backstory": ""})
con = database.connect()
row = dict(con.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone())
con.close()
check("空串提交不清空隐藏字段", row["personality"], FIELDS["personality"])

# ---- 锁定字段照常进入提示词（这是"锁定"的前提） ----
con = database.connect()
srow = con.execute("SELECT * FROM sessions WHERE id=?", (s["id"],)).fetchone()
crow = con.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
con.close()
system = prompts.build_system_prompt(srow, crow, "")
check("提示词里有性格", FIELDS["personality"] in system, True)
check("提示词里有背景", FIELDS["backstory"] in system, True)

# ---- 解锁：单向、永久 ----
r = client.post(f"/api/characters/{cid}/unlock")
check("解锁 200", r.status_code, 200)
check("解锁后返回全部字段", sorted(k for k in r.json() if k in FIELDS), sorted(FIELDS))
check("解锁后 locked=False", r.json()["locked"], False)
check("解锁后单查含隐藏字段",
      client.get(f"/api/characters/{cid}").json()["personality"], FIELDS["personality"])
r = client.put(f"/api/characters/{cid}", json={
    "name": "沈砚", "appearance": "白衣", "personality": "解锁后可以改了",
    "speech_style": "也一样", "backstory": "背景", "avatar": ""})
check("解锁后可改隐藏字段", r.json()["personality"], "解锁后可以改了")
check("重复解锁幂等", client.post(f"/api/characters/{cid}/unlock").status_code, 200)
check("已解锁角色在会话详情里可见",
      [k for k in HIDDEN if k in client.get(f"/api/sessions/{s['id']}").json()["character"]],
      list(HIDDEN))

# ---- 容错解析 ----
CJ = character_gen._clean_json
check("解析纯 JSON", CJ('{"name":"甲","personality":"乙"}')["name"], "甲")
check("解析代码块", CJ('```json\n{"name":"甲"}\n```')["name"], "甲")
check("解析夹带解释", CJ('好的，这是角色：\n{"name":"甲"}\n希望满意')["name"], "甲")
check("解析思考残留", CJ('<think>想想</think>{"name":"甲"}')["name"], "甲")
check("解析非 dict", CJ("[1,2]"), {})
check("解析失败给空", CJ("完全不是 JSON"), {})
check("逐行中文标签退化", CJ("姓名：甲\n性格：乙"),
      {"name": "甲", "personality": "乙"})
check("空输入", CJ(""), {})
try:
    character_gen._norm({"appearance": "只有外观"})
    check("缺姓名应报错", "没报错", "ValueError")
except ValueError:
    check("缺姓名应报错", "ValueError", "ValueError")
check("列表值合并", character_gen._norm({"name": "甲", "personality": ["一", "二"]})["personality"],
      "一；二")
check("超长截断", len(character_gen._norm({"name": "甲", "backstory": "字" * 2000})["backstory"]),
      character_gen.MAX_FIELD_CHARS)

# ---- 草稿上限与 JSON 模式载荷 ----
ids = [character_gen.new_draft(dict(FIELDS), "open") for _ in range(character_gen.MAX_DRAFTS + 5)]
check("草稿未超上限", len(character_gen._DRAFTS) <= character_gen.MAX_DRAFTS, True)
check("最早的草稿已被淘汰", character_gen.take_draft(ids[0]), None)
check("最新的草稿还在", bool(character_gen.take_draft(ids[-1])), True)

from app.ollama_client import _payload  # noqa: E402

check("JSON 模式载荷", _payload("m", [], False, None, "json")["format"], "json")
check("普通对话不带 format", "format" in _payload("m", [], True, None), False)

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("角色生成与探索模式锁定用例全部通过")
