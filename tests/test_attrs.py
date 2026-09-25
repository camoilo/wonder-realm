"""附加属性：解析（[ATTR] 块）、提示词注入、上一条消息的口径、落库与编辑接口。

用临时库 + TestClient，绝不碰 data/ 下的真实库。

跑法：uv run python tests/test_attrs.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, generation, parser, prompts  # noqa: E402
from app.routes import characters as character_routes  # noqa: E402
from app.routes import messages as message_routes  # noqa: E402
from app.routes import sessions as session_routes  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


DEFS = [
    {"name": "心情", "type": "text", "hint": "用一句简短的话描述"},
    {"name": "好感", "type": "percent", "hint": ""},
]

# ---- 1. 解析：属性块先摘掉，再解析正文 ----
RAW = "[SCENARIO]雨下得很大\n[DIALOG]进来吧\n[ATTR]\n心情：有点紧张\n好感：42"
body, block = parser.split_attrs(RAW)
check("属性块被摘出去", "[ATTR]" in block and "[ATTR]" in body, False)
check("正文原样保留", body.strip(), "[SCENARIO]雨下得很大\n[DIALOG]进来吧")
check("属性块内容保留", block.strip(), "心情：有点紧张\n好感：42")
check("摘完再解析：台词里没有属性", parser.parse_output("immersive", body),
      ("雨下得很大", "进来吧"))
check("解析出的属性", parser.parse_attrs(block, DEFS),
      [{"name": "心情", "type": "text", "value": "有点紧张"},
       {"name": "好感", "type": "percent", "value": 42.0}])

# 模型的小毛病都要能忍：闭合标记、其它标记名、半角冒号与等号、带 % 与小数、多余的空格
_tolerant = "[ATTRS]\n- 心情: 挺开心的\n好感 = 42.5%\n[/ATTRS]"
_body, _block = parser.split_attrs("我很好" + _tolerant)
check("宽容：别的标记名 + 闭合标记 + 半角分隔符 + 百分号",
      parser.parse_attrs(_block, DEFS),
      [{"name": "心情", "type": "text", "value": "挺开心的"},
       {"name": "好感", "type": "percent", "value": 42.5}])
check("宽容：正文没被吃掉", parser.parse_output("chat", _body), (None, "我很好"))

# 定义是唯一依据：模型自己编的条目丢掉；百分比超范围夹断；文字型空值丢掉
check("定义里没有的名字丢掉", parser.parse_attrs("运气：爆棚\n心情：平静", DEFS),
      [{"name": "心情", "type": "text", "value": "平静"}])
check("百分比夹到 0-100", parser.parse_attrs("好感：-5\n心情：a", DEFS)[0]["value"], 0.0)
check("百分比取第一个数字", parser.parse_attrs("好感：大约 88 左右", DEFS)[0]["value"], 88.0)
check("百分比没有数字就丢掉", parser.parse_attrs("好感：还行", DEFS), [])
check("文字型空值丢掉", parser.parse_attrs("心情：\n好感：1", DEFS),
      [{"name": "好感", "type": "percent", "value": 1.0}])
check("没有属性块时正文不受影响", parser.split_attrs("就一句话"), ("就一句话", ""))
# 实测 9B 模型会把整块写成一行（`[ATTR]心情值：85%好感度：60%`）：只按行切就只剩第一条，
# 所以在每个已知属性名前也要断开（用户报过"话末又写了一遍属性"，顺手发现这条）
_one_line = parser.split_attrs("好呀，那就看电影。[ATTR]心情：有点紧张 好感：42%")[1]
check("整块写成一行也能全解析出来",
      parser.parse_attrs(_one_line, DEFS),
      [{"name": "心情", "type": "text", "value": "有点紧张"},
       {"name": "好感", "type": "percent", "value": 42.0}])
check("名字长的优先（「好感度」不会被「好感」切断）",
      parser.parse_attrs("好感度：88%", [{"name": "好感", "type": "percent", "hint": ""},
                                        {"name": "好感度", "type": "percent", "hint": ""}]),
      [{"name": "好感度", "type": "percent", "value": 88.0}])
check("属性块插在中间也能摘掉（位置不敏感）",
      parser.split_attrs("前半\n[ATTR]\n心情：x\n后半")[0].replace("\n", "|"), "前半|后半")

# 属性块在前时，正文里的 [SCENARIO] 依然认得出（旧的场景/台词解析没被带坏）
check("属性块不影响场景/台词解析",
      parser.parse_output("immersive", parser.split_attrs("[ATTR]\n好感：1\n[SCENARIO]晴天\n[DIALOG]早")[0]),
      ("晴天", "早"))

# ---- 2. 提示词：有定义才注入，位置在记忆之后、回复要求之前 ----
CHARACTER = {
    "name": "阿岚", "appearance": "", "personality": "", "speech_style": "", "backstory": "",
}
c_plain = prompts.build_chat_system(CHARACTER, "", {})
check("没有属性定义时整块不出现", "# 附加属性" in c_plain, False)
c = prompts.build_chat_system(CHARACTER, "", {}, None, None, (DEFS, []))
check("有定义时给出状态块", "# 角色的当前状态（附加属性）" in c, True)
check("有几条定义就列几行", c.count("心情：") >= 1 and c.count("好感：") >= 1, True)
check("还没有记录时写明给初始值", "暂无记录" in c, True)
check("解释写进提示词", "用一句简短的话描述" in c, True)
check("要求输出 [ATTR] 块", "用一个 [ATTR] 块" in c and "[ATTR]\n心情：" in c, True)
check("说明用户看不到这个块", "用户看不到它" in c, True)
# 实测模型会把状态块里的「心情：98」照抄到台词结尾（"……好的呀。心情：98%"）：光说"别写进台词"
# 拦不住，提示词里必须点名反例（用户报过）
check("正文里禁止出现属性名与属性值（带反例）",
      "正文里绝对不要出现属性名或属性值" in c and "不要在话的结尾写" in c, True)
check("状态块在回复要求之前",
      c.index("# 角色的当前状态") < c.index("# 回复要求"), True)
check("输出规则在最后（附加属性那段在正文规则之后）",
      c.index("尤其不要把动作放进括号里") < c.index("# 附加属性"), True)

c_vals = prompts.build_chat_system(
    CHARACTER, "", {}, None, None,
    (DEFS, [{"name": "心情", "type": "text", "value": "开心"},
            {"name": "好感", "type": "percent", "value": 42.0}]),
)
check("上一轮的值描进状态块", "心情：开心（文字型，一句简短的话）" in c_vals, True)
check("百分比写明 0-100", "好感：42（百分比型，0-100 的整数）" in c_vals, True)
check("只有部分值时不编造其余", "暂无记录" not in c_vals, True)

i = prompts.build_immersive_system(
    CHARACTER, "", {}, None, None, (DEFS, [{"name": "好感", "type": "percent", "value": 7.5}])
)
check("沉浸模式同样注入", "# 角色的当前状态（附加属性）" in i and "好感：7.5" in i, True)
check("沉浸模式的两段标记规则仍在", "[SCENARIO]" in i and "[DIALOG]" in i, True)

d = prompts.build_director_system("", {}, None)
check("导演模式没有这段（sans 属性参数）", "# 附加属性" in d, False)
check("三种模式里只有导演不带属性（用 build_system_prompt 验证）",
      "# 附加属性" in prompts.build_system_prompt(
          {"mode": "chat", "gen_settings": "{}"}, CHARACTER, "", None, None, (DEFS, []))
      and "# 附加属性" in prompts.build_system_prompt(
          {"mode": "immersive", "gen_settings": "{}"}, CHARACTER, "", None, None, (DEFS, []))
      and "# 附加属性" in prompts.build_system_prompt(
          {"mode": "director", "gen_settings": "{}"}, None, "", None, None, (DEFS, [])), False)

# ---- 3. 库里的形状规则 ----
check("定义：空名丢掉", database.parse_attr_defs('[{"name": " ", "type": "text"}]'), [])
check("定义：类型不合法丢掉", database.parse_attr_defs('[{"name": "x", "type": "number"}]'), [])
check("定义：坏 JSON 退回空表", database.parse_attr_defs("{不是数组"), [])
check("定义：写入时也丢空名",
      database.clean_attr_defs([{"name": "", "type": "text"}, {"name": "心情", "type": "text"}]),
      '[{"name": "心情", "type": "text", "hint": ""}]')
check("值：空值不写进来", database.parse_attrs('[{"name": "心情", "type": "text", "value": ""}]'), [])
check("值：百分比夹断",
      database.parse_attrs('[{"name": "好感", "type": "percent", "value": 999}]')[0]["value"], 100.0)
check("值：坏 JSON 退回空表", database.parse_attrs("nope"), [])

# ---- 4. 临时库：角色定义、上一条消息的口径、落库 ----
tmp = Path(".test_attrs_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
database.init_db(str(tmp), "", "")
app = FastAPI()
app.include_router(character_routes.router)
app.include_router(session_routes.router)
app.include_router(message_routes.router)
client = TestClient(app)

a = client.post("/api/characters", json={"name": "阿岚"}).json()
check("新角色没有属性定义", a["attr_defs"], [])
r = client.put(f"/api/characters/{a['id']}", json={"name": "阿岚", "attr_defs": DEFS})
check("保存属性定义", r.json()["attr_defs"], DEFS)
check("保存时丢掉没命名的行",
      client.put(f"/api/characters/{a['id']}",
                 json={"name": "阿岚", "attr_defs": [{"name": " ", "type": "text"}]}
                 ).json()["attr_defs"], [])
client.put(f"/api/characters/{a['id']}", json={"name": "阿岚", "attr_defs": DEFS})
r = client.put(f"/api/characters/{a['id']}", json={"name": "阿岚改"})
check("没带 attr_defs 就不动它（编辑角色弹窗里没有这个编辑器）", r.json()["attr_defs"], DEFS)
check("类型非法被拒（422）",
      client.put(f"/api/characters/{a['id']}",
                 json={"name": "阿岚", "attr_defs": [{"name": "x", "type": "number"}]}).status_code, 422)
check("属性条数超上限被拒（422）",
      client.put(f"/api/characters/{a['id']}", json={"name": "阿岚", "attr_defs": [
          {"name": f"n{i}", "type": "text"} for i in range(9)]}).status_code, 422)

# 两个会话（同一角色）：用来验证"上一条"与跨会话的退路
c1 = client.post("/api/sessions", json={"mode": "chat", "character_id": a["id"]}).json()
c2 = client.post("/api/sessions", json={"mode": "immersive", "character_id": a["id"]}).json()

con = database.connect()
def add_msg(sid, role, content, attrs="[]", created="2026-01-01T00:00:00"):
    cur = con.execute(
        "INSERT INTO messages(session_id, role, content, scenario, attrs, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (sid, role, content, None, attrs, created),
    )
    con.commit()
    return cur.lastrowid

check("全新会话：上一条为空（不注入）",
      generation.previous_attrs(con, con.execute("SELECT * FROM sessions WHERE id=?", (c1["id"],)).fetchone(),
                                con.execute("SELECT * FROM characters WHERE id=?", (a["id"],)).fetchone()), [])

m1 = add_msg(c1["id"], "user", "在吗")
m2 = add_msg(c1["id"], "assistant", "在", database.clean_attrs(
    [{"name": "心情", "type": "text", "value": "平静"}, {"name": "好感", "type": "percent", "value": 10}]))
# 每轮调用前，**这轮的输入消息就是会话里最新的一条**（聊天是先落 user 消息再组装上下文，
# 重新生成是保留那条 user 消息再组装），所以"上一条"= 输入之前的那一条
add_msg(c1["id"], "user", "你在忙吗")
sess1 = con.execute("SELECT * FROM sessions WHERE id=?", (c1["id"],)).fetchone()
char1 = con.execute("SELECT * FROM characters WHERE id=?", (a["id"],)).fetchone()
check("会话里之前的消息：取它带回的属性",
      generation.previous_attrs(con, sess1, char1),
      [{"name": "心情", "type": "text", "value": "平静"},
       {"name": "好感", "type": "percent", "value": 10.0}])

# 退路：当前会话没有"上一条"（这轮输入就是第一条）→ 该角色其它会话里时间最近的那一条
m3 = add_msg(c2["id"], "assistant", "又见面了", database.clean_attrs(
    [{"name": "心情", "type": "text", "value": "惊喜"}]), created="2026-02-02T10:00:00")
add_msg(c2["id"], "user", "嗯，我来了", created="2026-02-02T10:01:00")  # 这轮的输入
sess2 = con.execute("SELECT * FROM sessions WHERE id=?", (c2["id"],)).fetchone()
check("当前会话没有上一条 → 退到该角色其它会话里最近的一条",
      generation.previous_attrs(con, sess2, char1),
      [{"name": "心情", "type": "text", "value": "惊喜"}])
# 退路取的就是"时间最近的那一条"本身（严格口径，用户确认过）：它没有属性时
# 什么都不注入——不会为了"有值可注入"再往前翻
c3 = client.post("/api/sessions", json={"mode": "chat", "character_id": a["id"]}).json()
add_msg(c3["id"], "user", "第一次说话", created="2026-04-04T10:00:00")
sess3 = con.execute("SELECT * FROM sessions WHERE id=?", (c3["id"],)).fetchone()
check("退路取时间最近的那一条；它没有属性就为空（且不含这轮输入自己）",
      generation.previous_attrs(con, sess3, char1), [])
check("角色一条消息都没有时为空", generation.previous_attrs(
    con, sess3,
    con.execute("SELECT * FROM characters WHERE id=?",
                (client.post("/api/characters", json={"name": "小满"}).json()["id"],)).fetchone()), [])

# 落库：属性块不进正文，值写进 attrs 列
mid, content, scenario, attrs = generation.persist_message(
    c1["id"], "chat", "我在的\n[ATTR]\n心情：开心\n好感：88", DEFS
)
check("落库的正文里没有属性块", content, "我在的")
check("落库的返回值带属性", attrs,
      [{"name": "心情", "type": "text", "value": "开心"},
       {"name": "好感", "type": "percent", "value": 88.0}])
row = con.execute("SELECT attrs FROM messages WHERE id=?", (mid,)).fetchone()
check("库里存的是解析后的 JSON", database.parse_attrs(row["attrs"]), attrs)
con.close()

# ---- 5. 接口：消息列表带属性、编辑面板能改 ----
msgs = client.get(f"/api/sessions/{c1['id']}/messages").json()
check("消息列表里 attrs 已经是数组", isinstance(msgs[-1]["attrs"], list), True)
check("消息列表带回了属性值", msgs[-1]["attrs"][1], {"name": "好感", "type": "percent", "value": 88.0})
r = client.put(f"/api/messages/{mid}", json={"content": "我在的", "attrs": [
    {"name": "心情", "type": "text", "value": "特别开心"},
    {"name": "好感", "type": "percent", "value": 95}]})
check("编辑属性值", r.json()["attrs"],
      [{"name": "心情", "type": "text", "value": "特别开心"},
       {"name": "好感", "type": "percent", "value": 95.0}])
check("编辑时把空值清掉（空值不写进来）",
      client.put(f"/api/messages/{mid}", json={"content": "我在的", "attrs": [
          {"name": "心情", "type": "text", "value": ""}]}).json()["attrs"], [])
r = client.put(f"/api/messages/{mid}", json={"content": "只改正文"})
check("没带 attrs 就不动它", r.json()["attrs"], [])
check("编辑后消息列表里的属性跟着变",
      client.get(f"/api/sessions/{c1['id']}/messages").json()[-1]["attrs"], [])
check("编辑接口仍不接受空正文",
      client.put(f"/api/messages/{mid}", json={"content": "   "}).status_code, 400)

shutil.rmtree(tmp, ignore_errors=True)
print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("附加属性用例全部通过")
