"""输入字数上限（10.31）：后端按 limits.LIMITS 校验，前端从 /api/limits 取同一份。

上限只写一处：`app/limits.py`。这里盯住三件事——超限被拒（422）、等于上限放行、
以及 `GET /api/limits` 与 `FIELDS` 里下发的数字和上限表一致（前端据此设 maxlength
与右下角计数，数字不一致就会出现"打得进、存不下"）。
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pydantic  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.character_gen import MAX_FIELD_CHARS  # noqa: E402
from app.limits import LIMITS  # noqa: E402
from app.prompts import FIELDS  # noqa: E402
from app.routes import settings as settings_routes  # noqa: E402
from app.schemas import (  # noqa: E402
    ChatIn, CharacterIn, GenerateIn, MemoryEdit, MessageEdit, SessionIn, SessionPatch, WorldIn,
)

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


# 每个超限字段：[说明, 模型, 其它必填, 字段名, 上限]
CASES = [
    ("消息正文", ChatIn, {"message": "hi"}, "message", LIMITS["message"]),
    ("角色姓名", CharacterIn, {"name": "甲"}, "name", LIMITS["name"]),
    ("角色外观", CharacterIn, {"name": "甲"}, "appearance", LIMITS["appearance"]),
    ("角色性格", CharacterIn, {"name": "甲"}, "personality", LIMITS["personality"]),
    ("角色语言风格", CharacterIn, {"name": "甲"}, "speech_style", LIMITS["speech_style"]),
    ("角色背景故事", CharacterIn, {"name": "甲"}, "backstory", LIMITS["backstory"]),
    ("新建会话标题", SessionIn, {}, "title", LIMITS["title"]),
    ("修改会话标题", SessionPatch, {}, "title", LIMITS["title"]),
    ("编辑消息正文", MessageEdit, {}, "content", LIMITS["message"]),
    ("编辑消息情境", MessageEdit, {}, "scenario", LIMITS["scenario"]),
    ("记忆内容", MemoryEdit, {}, "content", LIMITS["memory"]),
    ("生成角色提示词", GenerateIn, {}, "hint", LIMITS["hint"]),
    # 世界设定：名称只给自己看，描述/规则进提示词（词库的嵌套上限在 test_world.py 里测）
    ("世界名称", WorldIn, {}, "name", LIMITS["world_name"]),
    ("世界描述", WorldIn, {}, "description", LIMITS["world_description"]),
    ("世界规则", WorldIn, {}, "rules", LIMITS["world_rules"]),
]

for label, cls, base, field, limit in CASES:
    try:
        cls(**{**base, field: "字" * (limit + 1)})
        check(f"{label} 超限被拒", "未拦截", "string_too_long")
    except pydantic.ValidationError as e:
        check(f"{label} 超限被拒", e.errors()[0]["type"], "string_too_long")
    try:
        cls(**{**base, field: "字" * limit})
        check(f"{label} 等于上限放行", True, True)
    except pydantic.ValidationError as e:
        check(f"{label} 等于上限放行", e.errors()[0]["type"], "通过")

# 模型给角色字段的截断上限不能高于输入上限，否则生成结果会被前端/后端拦住
for key in ("appearance", "personality", "speech_style", "backstory"):
    check(f"生成截断 {key} 不高于输入上限", MAX_FIELD_CHARS <= LIMITS[key], True)

# 接口下发的上限与上限表一致，也覆盖生成要求表单里的自由文本字段
app = FastAPI()
app.include_router(settings_routes.router)
with TestClient(app) as client:
    served = client.get("/api/limits").json()
check("GET /api/limits 与上限表一致", served, LIMITS)

form = client.get("/api/gen-settings").json()["fields"]
for mode, fields in form.items():
    for f in fields:
        if f["type"] in ("text", "textarea"):
            want = LIMITS["genre"] if f["type"] == "text" else LIMITS["extra"]
            check(f"{mode}.{f['key']} 表单上限", f.get("max"), want)
        else:
            check(f"{mode}.{f['key']} 不该有上限", "max" in f, False)

# 前端模板引用的每个 limits.<key> 都必须在上限表里（写错键会渲染成 undefined）
import re  # noqa: E402

html = (Path(__file__).resolve().parent.parent / "app/static/index.html").read_text(encoding="utf-8")
used = set(re.findall(r"limits\.([a-z_]+)", html))
check("模板引用的上限键都在表里", sorted(used - set(LIMITS)), [])
# genre / extra 走的是 FIELDS 里的 "max"（后端随字段定义下发），模板里不会写 limits.xxx
check("模板里没写死的上限键只有 genre / extra", sorted(set(LIMITS) - used), ["extra", "genre"])

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("输入字数上限用例全部通过")
