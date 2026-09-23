"""世界设定：id=1 是当前世界、id>1 是世界预设；名称只给自己看（不进提示词），
描述 / 规则 / 词库进三种模式的提示词。用哪份世界由绑定决定——聊天与沉浸跟着角色，
导演跟着会话（见 DEVELOPMENT §2.4）。

用临时库 + TestClient，绝不碰 data/ 下的真实库。

跑法：uv run python tests/test_world.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, prompts  # noqa: E402
from app.limits import LIMITS  # noqa: E402
from app.routes import characters as character_routes  # noqa: E402
from app.routes import sessions as session_routes  # noqa: E402
from app.routes import world as world_routes  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


EMPTY = {"name": "", "description": "", "rules": "", "terms": []}

# ---- 1. 新库：默认全空，且只有一行 ----
tmp = Path(".test_world_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), "", "")
check("新库世界设定为空", database.read_world(), EMPTY)
check("世界表只有一行", database.connect().execute(
    "SELECT COUNT(*) FROM worlds").fetchone()[0], 1)

# ---- 2. 接口往返 ----
app = FastAPI()
app.include_router(world_routes.router)
client = TestClient(app)

r = client.put("/api/world", json={
    "name": "灰港秘闻录",
    "description": "终年雾锁的海港城，钟楼比太阳更可靠",
    "rules": "入夜后不得提及海神之名；借来的东西必须还回原处",
    "terms": [
        {"term": "潮汐钟", "meaning": "记录潮位而非时刻的钟"},
        {"term": "议会廊桥", "meaning": ""},
    ],
})
check("保存返回 200", r.status_code, 200)
saved = r.json()
check("名称存下来了", saved["name"], "灰港秘闻录")
check("词库两条且保持顺序", [t["term"] for t in saved["terms"]], ["潮汐钟", "议会廊桥"])
check("解释可以留空", saved["terms"][1]["meaning"], "")
check("GET 与保存结果一致", client.get("/api/world").json(), saved)

check("全空也能保存", client.put("/api/world", json={}).json(), EMPTY)

# 只填一部分：其余项就是空串，不报错
client.put("/api/world", json={"rules": "  只有规则  "})
check("文本两端空白被去掉", client.get("/api/world").json()["rules"], "只有规则")
check("没填的项是空串", client.get("/api/world").json()["description"], "")

# 名词为空的行被丢弃：界面上刚点出来、还没填的空行不该让整次保存失败
client.put("/api/world", json={"name": "甲", "terms": [
    {"term": "   "}, {"term": " 乙 ", "meaning": " 有解释 "},
]})
check("空名词行被丢弃且其余被 strip", client.get("/api/world").json()["terms"],
      [{"term": "乙", "meaning": "有解释"}])

# ---- 3. 上限 ----
check("名称超限 422",
      client.put("/api/world", json={"name": "字" * (LIMITS["world_name"] + 1)}).status_code, 422)
check("名称等于上限放行",
      client.put("/api/world", json={"name": "字" * LIMITS["world_name"]}).status_code, 200)
check("描述超限 422",
      client.put("/api/world",
                 json={"description": "字" * (LIMITS["world_description"] + 1)}).status_code, 422)
check("规则超限 422",
      client.put("/api/world",
                 json={"rules": "字" * (LIMITS["world_rules"] + 1)}).status_code, 422)
check("名词超限 422",
      client.put("/api/world", json={"terms": [
          {"term": "字" * (LIMITS["world_term"] + 1)}]}).status_code, 422)
check("解释超限 422",
      client.put("/api/world", json={"terms": [
          {"term": "甲", "meaning": "字" * (LIMITS["world_term_meaning"] + 1)}]}).status_code, 422)
check("词条数等于上限放行",
      client.put("/api/world", json={"terms": [
          {"term": f"n{i}"} for i in range(LIMITS["world_terms_max"])]}).status_code, 200)
check("词条数超限 422",
      client.put("/api/world", json={"terms": [
          {"term": f"n{i}"} for i in range(LIMITS["world_terms_max"] + 1)]}).status_code, 422)

# ---- 4. 提示词注入 ----
WORLD = {
    "name": "灰港秘闻录",
    "description": "终年雾锁的海港城",
    "rules": "入夜后不得提及海神之名",
    "terms": [{"term": "潮汐钟", "meaning": "记录潮位的钟"}, {"term": "议会廊桥", "meaning": ""}],
}
CHARACTER = {
    "name": "阿岚", "appearance": "", "personality": "", "speech_style": "", "backstory": "",
}

for mode in ("chat", "immersive", "director"):
    session = {"mode": mode, "gen_settings": "{}"}
    system = prompts.build_system_prompt(session, CHARACTER, "", None, WORLD)
    check(f"{mode} 注入描述", "终年雾锁的海港城" in system, True)
    check(f"{mode} 注入规则", "入夜后不得提及海神之名" in system, True)
    check(f"{mode} 注入词库（带解释）", "- 潮汐钟：记录潮位的钟" in system, True)
    check(f"{mode} 词条没有解释时只给名词", "- 议会廊桥\n" in system, True)
    check(f"{mode} 世界名称不进提示词", "灰港秘闻录" in system, False)

system = prompts.build_system_prompt(
    {"mode": "chat", "gen_settings": "{}"}, CHARACTER, "", None, WORLD
)
check("世界设定排在角色设定之前",
      system.index("# 世界设定") < system.index("# 角色设定"), True)
check("世界块带一句约束说明", "不要改写这些设定" in system, True)

# 只填了名称 = 等于没填：整块不出现（不给模型一段空标签）
only_name = {"name": "只填了名字", "description": "", "rules": "", "terms": []}
system = prompts.build_system_prompt(
    {"mode": "chat", "gen_settings": "{}"}, CHARACTER, "", None, only_name
)
check("只有名称时不注入世界块", "# 世界设定" in system, False)
check("只有名称时名字也不出现", "只填了名字" in system, False)

system = prompts.build_system_prompt(
    {"mode": "chat", "gen_settings": "{}"}, CHARACTER, "", None, None
)
check("没有世界设定时也不报错", "# 世界设定" in system, False)

# 组装成消息时也带着（生成走的是 build_messages 这条路）
msgs = prompts.build_messages(
    {"mode": "director", "gen_settings": "{}"}, None, "", [], None, WORLD
)
check("build_messages 的 system 消息含世界设定", "# 世界设定" in msgs[0]["content"], True)

# ---- 5. 库里的词库 JSON 被写坏时降级成空列表，而不是整个读取失败 ----
con = database.connect()
con.execute("UPDATE worlds SET terms=? WHERE id=1", ("{不是数组",))
con.commit()
con.close()
check("坏 JSON 退回空列表", database.read_world()["terms"], [])
check("坏 JSON 不影响其它字段", isinstance(database.read_world()["rules"], str), True)

# ---- 6. 世界预设：增 / 列 / 覆盖 / 删，且不动 id=1 ----
# 与"我的设定"预设完全同构（见 2.3）：同一个主体一张表，id=1 是当前那份、id>1 是预设
app.include_router(character_routes.router)
app.include_router(session_routes.router)
client.put("/api/world", json={"name": "当前世界", "description": "当下的那份", "terms": []})

check("新库没有世界预设", client.get("/api/world/presets").json(), [])
check("世界预设名字为空被拒",
      client.post("/api/world/presets", json={"description": "没名字"}).status_code, 400)
w1 = client.post("/api/world/presets", json={
    "name": "海边小城", "description": "常年有雾", "rules": "没有魔法",
    "terms": [{"term": "雾钟", "meaning": "报雾的钟"}],
}).json()
check("存为世界预设 200 并带回整份设定",
      (w1["name"], w1["description"], w1["rules"], w1["terms"]),
      ("海边小城", "常年有雾", "没有魔法", [{"term": "雾钟", "meaning": "报雾的钟"}]))
check("新预设默认没绑角色",
      [p["characters"] for p in client.get("/api/world/presets").json() if p["id"] == w1["id"]], [[]])
check("存预设不影响当前世界", client.get("/api/world").json()["name"], "当前世界")
w2 = client.post("/api/world/presets", json={"name": "高原", "rules": "风大"}).json()
check("列表里两条且新的在前",
      [p["name"] for p in client.get("/api/world/presets").json()], ["高原", "海边小城"])
check("当前世界不在预设里",
      "当前世界" in [p["name"] for p in client.get("/api/world/presets").json()], False)
check("世界预设名字上限仍生效",
      client.post("/api/world/presets", json={"name": "字" * (LIMITS["world_name"] + 1)}).status_code, 422)
check("世界预设词库上限仍生效",
      client.post("/api/world/presets", json={"name": "x", "terms": [
          {"term": f"t{i}", "meaning": ""} for i in range(LIMITS["world_terms_max"] + 1)
      ]}).status_code, 422)

r = client.put(f"/api/world/presets/{w2['id']}", json={
    "name": "高原", "description": "海拔四千米", "terms": [{"term": "雪线", "meaning": "界线"}],
})
check("覆盖世界预设 200", (r.status_code, r.json()["description"]), (200, "海拔四千米"))
check("覆盖不新增条目", len(client.get("/api/world/presets").json()), 2)
check("覆盖时名字为空被拒",
      client.put(f"/api/world/presets/{w2['id']}", json={"name": " "}).status_code, 400)
check("覆盖不存在的预设 404",
      client.put("/api/world/presets/999", json={"name": "x"}).status_code, 404)
check("覆盖 id=1（当前世界）被拒",
      client.put("/api/world/presets/1", json={"name": "x"}).status_code, 404)
check("覆盖世界预设不影响当前世界", client.get("/api/world").json()["description"], "当下的那份")

# ---- 7. 绑定：角色（聊天 / 沉浸）与导演会话 ----
c1 = client.post("/api/characters", json={"name": "阿岚"}).json()
c2 = client.post("/api/characters", json={"name": "小满"}).json()
check("新建角色默认不绑世界", (c1["world_id"], c2["world_id"]), (None, None))
r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚", "world_id": w1["id"]})
check("给角色绑世界预设", r.json()["world_id"], w1["id"])
client.put(f"/api/characters/{c2['id']}", json={"name": "小满", "world_id": w1["id"]})
by_id = {p["id"]: p for p in client.get("/api/world/presets").json()}
check("一份世界预设可以绑多个角色",
      [c["name"] for c in by_id[w1["id"]]["characters"]], ["阿岚", "小满"])
check("没被绑的预设显示为空", by_id[w2["id"]]["characters"], [])
# 面板保存角色设定时提交的表单里没有 world_id——那不能被当成"解绑"（同 profile_id）
r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚改", "appearance": "黑衣"})
check("不改世界绑定就不动它", r.json()["world_id"], w1["id"])
r = client.put(f"/api/characters/{c1['id']}", json={"name": "阿岚改", "world_id": None})
check("显式 null 才解绑世界", r.json()["world_id"], None)
check("绑不存在的世界预设被拒",
      client.put(f"/api/characters/{c1['id']}",
                 json={"name": "阿岚", "world_id": 999}).status_code, 400)
check("不能绑到 id=1（那是当前世界，不是预设）",
      client.put(f"/api/characters/{c1['id']}",
                 json={"name": "阿岚", "world_id": 1}).status_code, 400)
check("身份与世界两个绑定互不干扰",
      client.put(f"/api/characters/{c1['id']}",
                 json={"name": "阿岚", "profile_id": None}).json()["world_id"], None)

# 导演会话没有角色，世界只能挂在会话上
s = client.post("/api/sessions", json={"mode": "director", "world_id": w1["id"]}).json()
check("新建导演会话时绑世界", s["world_id"], w1["id"])
check("新建导演会话时也能不绑",
      client.post("/api/sessions", json={"mode": "director"}).json()["world_id"], None)
check("导演会话绑不存在的世界预设被拒",
      client.post("/api/sessions", json={"mode": "director", "world_id": 999}).status_code, 400)
r = client.patch(f"/api/sessions/{s['id']}", json={"world_id": w2["id"]})
check("事后改导演会话的世界", r.json()["world_id"], w2["id"])
r = client.patch(f"/api/sessions/{s['id']}", json={"title": "只改标题"})
check("不提交 world_id 就不动绑定（生成要求补丁里没有它）", r.json()["world_id"], w2["id"])
r = client.patch(f"/api/sessions/{s['id']}", json={"world_id": None})
check("显式 null 解绑导演会话的世界", r.json()["world_id"], None)
check("导演会话绑到 id=1 被拒",
      client.patch(f"/api/sessions/{s['id']}", json={"world_id": 1}).status_code, 400)

# ---- 8. 删掉世界预设：引用它的角色与会话一起解绑，不留悬空 id ----
client.put(f"/api/characters/{c2['id']}", json={"name": "小满", "world_id": w1["id"]})
client.patch(f"/api/sessions/{s['id']}", json={"world_id": w1["id"]})
check("删除被引用的世界预设 200",
      client.delete(f"/api/world/presets/{w1['id']}").status_code, 200)
check("删预设后角色自动解绑",
      [c["world_id"] for c in client.get("/api/characters").json() if c["id"] == c2["id"]], [None])
check("删预设后导演会话自动解绑",
      client.get(f"/api/sessions/{s['id']}").json()["world_id"], None)
check("删除世界预设不动当前世界", client.get("/api/world").json()["name"], "当前世界")
check("重复删除 404", client.delete(f"/api/world/presets/{w1['id']}").status_code, 404)
check("删 id=1（当前世界）被拒", client.delete("/api/world/presets/1").status_code, 404)

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("世界设定用例全部通过")
