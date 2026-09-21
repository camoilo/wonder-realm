"""世界设定：全局一份；名称只给自己看（不进提示词），描述 / 规则 / 词库进三种模式的提示词。

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
    "SELECT COUNT(*) FROM world").fetchone()[0], 1)

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

for mode in ("character_chat", "character_scenario", "free_scenario"):
    session = {"mode": mode, "gen_settings": "{}"}
    system = prompts.build_system_prompt(session, CHARACTER, "", None, WORLD)
    check(f"{mode} 注入描述", "终年雾锁的海港城" in system, True)
    check(f"{mode} 注入规则", "入夜后不得提及海神之名" in system, True)
    check(f"{mode} 注入词库（带解释）", "- 潮汐钟：记录潮位的钟" in system, True)
    check(f"{mode} 词条没有解释时只给名词", "- 议会廊桥\n" in system, True)
    check(f"{mode} 世界名称不进提示词", "灰港秘闻录" in system, False)

system = prompts.build_system_prompt(
    {"mode": "character_chat", "gen_settings": "{}"}, CHARACTER, "", None, WORLD
)
check("世界设定排在角色设定之前",
      system.index("# 世界设定") < system.index("# 角色设定"), True)
check("世界块带一句约束说明", "不要改写这些设定" in system, True)

# 只填了名称 = 等于没填：整块不出现（不给模型一段空标签）
only_name = {"name": "只填了名字", "description": "", "rules": "", "terms": []}
system = prompts.build_system_prompt(
    {"mode": "character_chat", "gen_settings": "{}"}, CHARACTER, "", None, only_name
)
check("只有名称时不注入世界块", "# 世界设定" in system, False)
check("只有名称时名字也不出现", "只填了名字" in system, False)

system = prompts.build_system_prompt(
    {"mode": "character_chat", "gen_settings": "{}"}, CHARACTER, "", None, None
)
check("没有世界设定时也不报错", "# 世界设定" in system, False)

# 组装成消息时也带着（生成走的是 build_messages 这条路）
msgs = prompts.build_messages(
    {"mode": "free_scenario", "gen_settings": "{}"}, None, "", [], None, WORLD
)
check("build_messages 的 system 消息含世界设定", "# 世界设定" in msgs[0]["content"], True)

# ---- 5. 库里的词库 JSON 被写坏时降级成空列表，而不是整个读取失败 ----
con = database.connect()
con.execute("UPDATE world SET terms=? WHERE id=1", ("{不是数组",))
con.commit()
con.close()
check("坏 JSON 退回空列表", database.read_world()["terms"], [])
check("坏 JSON 不影响其它字段", isinstance(database.read_world()["rules"], str), True)

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("世界设定用例全部通过")
