from fastapi import APIRouter, Depends, HTTPException
import httpx

from .. import character_gen
from ..character_gen import HIDDEN_FIELDS, public_character
from ..database import get_db, now
from ..schemas import BACKGROUND_MAX_COUNT, BackgroundsIn, CharacterCreateIn, CharacterIn, GenerateIn

router = APIRouter(prefix="/api")


def _get_character(db, cid: int):
    row = db.execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone()
    if not row:
        raise HTTPException(404, "角色不存在")
    return row


@router.get("/characters")
def list_characters(db=Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM characters ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    counts = {
        r["character_id"]: r["n"]
        for r in db.execute(
            "SELECT character_id, COUNT(*) AS n FROM sessions "
            "WHERE character_id IS NOT NULL GROUP BY character_id"
        )
    }
    return [public_character(r) | {"session_count": counts.get(r["id"], 0)} for r in rows]


@router.post("/characters/generate")
async def generate_character(body: GenerateIn):
    """让模型生成一份角色设定，先存成草稿（还没有角色 id）。

    探索模式只回姓名与外观：另外三项前端根本拿不到，锁定才算真的锁上。
    """
    try:
        fields = await character_gen.generate_character(body.hint)
    except ValueError as e:
        # 我们自己的校验：没选模型、模型没给出姓名
        raise HTTPException(502, f"生成失败：{e}")
    except httpx.HTTPError as e:
        # 连不上 Ollama、超时、响应异常。刻意不catch宽泛的 Exception：
        # 真出了编程错误就该是 500，而不是伪装成"生成失败"
        raise HTTPException(502, f"生成失败：{e}")
    draft_id = character_gen.new_draft(fields, body.mode)
    visible = dict(fields) if body.mode == "open" else {
        k: v for k, v in fields.items() if k not in HIDDEN_FIELDS
    }
    return {"draft_id": draft_id, "mode": body.mode, "locked": body.mode == "explore", **visible}


@router.post("/characters")
def create_character(body: CharacterCreateIn, db=Depends(get_db)):
    draft = character_gen.take_draft(body.draft_id) if body.draft_id else None
    if body.draft_id and draft is None:
        raise HTTPException(400, "这次生成的结果已经失效，请重新生成")

    if draft and draft["mode"] == "explore":
        # 探索模式：三个隐藏字段以草稿为准，请求体里那几个空串一律不算数
        fields = {k: draft[k] for k in HIDDEN_FIELDS}
        locked = 1
    else:
        # 手工创建，或开放模式的草稿（用户可能改过生成结果）：以请求体为准
        fields = {k: getattr(body, k).strip() for k in HIDDEN_FIELDS}
        locked = 0

    cur = db.execute(
        "INSERT INTO characters(name, appearance, personality, speech_style, backstory, avatar, locked, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            body.name.strip(),
            body.appearance.strip(),
            fields["personality"],
            fields["speech_style"],
            fields["backstory"],
            body.avatar,
            locked,
            now(),
            now(),
        ),
    )
    db.commit()
    return public_character(_get_character(db, cur.lastrowid))


@router.get("/characters/{cid}")
def get_character(cid: int, db=Depends(get_db)):
    return public_character(_get_character(db, cid))


@router.put("/characters/{cid}")
def update_character(cid: int, body: CharacterIn, db=Depends(get_db)):
    row = _get_character(db, cid)
    if row["locked"]:
        # 锁定时只允许改公开字段：请求体里那三个字段（前端压根没有值，是空串）
        # 一律忽略，否则面板一保存就把隐藏设定清空了
        db.execute(
            "UPDATE characters SET name=?, appearance=?, avatar=?, updated_at=? WHERE id=?",
            (body.name.strip(), body.appearance.strip(), body.avatar, now(), cid),
        )
    else:
        db.execute(
            "UPDATE characters SET name=?, appearance=?, personality=?, speech_style=?, backstory=?, avatar=?, updated_at=? "
            "WHERE id=?",
            (
                body.name.strip(),
                body.appearance.strip(),
                body.personality.strip(),
                body.speech_style.strip(),
                body.backstory.strip(),
                body.avatar,
                now(),
                cid,
            ),
        )
    db.commit()
    return public_character(_get_character(db, cid))


@router.post("/characters/{cid}/unlock")
def unlock_character(cid: int, db=Depends(get_db)):
    """公开角色设定：永久取消锁定，之后接口照常下发、也开放编辑。

    没有反向操作——"再锁回去"意味着用户看过的内容还能收回去，没有意义。
    """
    row = _get_character(db, cid)
    if not row["locked"]:
        return public_character(row)
    db.execute("UPDATE characters SET locked=0, updated_at=? WHERE id=?", (now(), cid))
    db.commit()
    return public_character(_get_character(db, cid))


@router.delete("/characters/{cid}")
def delete_character(cid: int, db=Depends(get_db)):
    _get_character(db, cid)
    # 会话由外键 ON DELETE SET NULL 保留；角色记忆删除；背景图由外键 ON DELETE CASCADE 删除
    db.execute("DELETE FROM memories WHERE scope_type='character' AND scope_id=?", (cid,))
    db.execute("DELETE FROM characters WHERE id=?", (cid,))
    db.commit()
    return {"ok": True}


@router.get("/characters/{cid}/backgrounds")
def list_backgrounds(cid: int, db=Depends(get_db)):
    """单独取背景图：不随角色列表/会话详情返回，避免每次请求都背上几 MB 图片。"""
    _get_character(db, cid)
    rows = db.execute(
        "SELECT data FROM character_images WHERE character_id=? ORDER BY position, id",
        (cid,),
    ).fetchall()
    return {"images": [r["data"] for r in rows], "max": BACKGROUND_MAX_COUNT}


@router.put("/characters/{cid}/backgrounds")
def replace_backgrounds(cid: int, body: BackgroundsIn, db=Depends(get_db)):
    """整体替换。前端是把这一组图当一个整体编辑的（增删都发生在表单里、保存时一次提交），
    逐张增删反而要维护更多中间状态，且新建角色时还没有 id 可挂。"""
    _get_character(db, cid)
    db.execute("DELETE FROM character_images WHERE character_id=?", (cid,))
    for i, data in enumerate(body.images):
        db.execute(
            "INSERT INTO character_images(character_id, position, data, created_at) "
            "VALUES(?,?,?,?)",
            (cid, i, data, now()),
        )
    db.commit()
    return {"images": body.images, "max": BACKGROUND_MAX_COUNT}
