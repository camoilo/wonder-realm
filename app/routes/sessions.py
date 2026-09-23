import json

from fastapi import APIRouter, Depends, HTTPException

from ..character_gen import public_character
from ..database import get_db, now, read_world_by_id
from ..schemas import SessionIn, SessionPatch

router = APIRouter(prefix="/api")

MODES = ("chat", "immersive", "director")
CHARACTER_MODES = ("chat", "immersive")
# 请求体里没提 world_id 时的占位：与 None（显式解绑）区分开
UNSET = object()


def _dump(settings: dict) -> str:
    return json.dumps(settings or {}, ensure_ascii=False)


def _world_binding(body) -> object:
    """导演会话绑的世界预设（见 DEVELOPMENT §2.4 世界设定）：UNSET = 这一项不用动。

    聊天与沉浸两种模式的世界跟着**角色**走（`characters.world_id`），这里只服务导演模式——
    那种会话没有角色，世界只能挂在会话上。只认已存在的预设：id<=1 是"当前世界"本身。
    """
    if "world_id" not in body.model_fields_set:
        return UNSET
    wid = body.world_id
    if wid is None:
        return None
    if wid <= 1 or read_world_by_id(wid) is None:
        raise HTTPException(400, "要绑定的「世界」预设不存在")
    return wid


def _get_session(db, sid: int):
    row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404, "会话不存在")
    return row


def _session_detail(db, sid: int) -> dict:
    session = dict(_get_session(db, sid))
    character = None
    if session["character_id"]:
        row = db.execute(
            "SELECT * FROM characters WHERE id=?", (session["character_id"],)
        ).fetchone()
        if row:
            # 必须走同一个裁剪：会话详情里也内嵌角色，漏了它就能从这里读到锁定的设定
            character = public_character(row)
    session["character"] = character
    try:
        session["gen_settings"] = json.loads(session["gen_settings"] or "{}")
    except json.JSONDecodeError:
        session["gen_settings"] = {}
    return session


@router.get("/sessions")
def list_sessions(
    mode: str | None = None,
    character_id: int | None = None,
    db=Depends(get_db),
):
    sql = "SELECT * FROM sessions"
    conds, params = [], []
    if mode:
        conds.append("mode=?")
        params.append(mode)
    if character_id:
        conds.append("character_id=?")
        params.append(character_id)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY updated_at DESC, id DESC"
    return [dict(r) for r in db.execute(sql, params).fetchall()]


@router.post("/sessions")
def create_session(body: SessionIn, db=Depends(get_db)):
    if body.mode not in MODES:
        raise HTTPException(400, f"未知模式：{body.mode}")
    character_id = None
    if body.mode in CHARACTER_MODES:
        if not body.character_id:
            raise HTTPException(400, "该模式需要选择角色")
        row = db.execute(
            "SELECT id FROM characters WHERE id=?", (body.character_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "角色不存在")
        character_id = body.character_id
    world = _world_binding(body)
    cur = db.execute(
        "INSERT INTO sessions(mode, character_id, world_id, title, title_auto, gen_settings, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            body.mode,
            character_id,
            None if world is UNSET else world,
            body.title.strip() or "新会话",
            0 if body.title.strip() else 1,  # 未命名的新会话交给模型自动命名
            _dump(body.gen_settings),
            now(),
            now(),
        ),
    )
    db.commit()
    return _session_detail(db, cur.lastrowid)


@router.get("/sessions/{sid}")
def get_session(sid: int, db=Depends(get_db)):
    return _session_detail(db, sid)


@router.patch("/sessions/{sid}")
def update_session(sid: int, body: SessionPatch, db=Depends(get_db)):
    _get_session(db, sid)
    world = _world_binding(body)
    sets, vals = [], []
    if body.title is not None:
        sets.append("title=?")
        vals.append(body.title.strip() or "新会话")
        sets.append("title_auto=0")  # 手动命名后不再被自动标题覆盖
    if body.gen_settings is not None:
        sets.append("gen_settings=?")
        vals.append(_dump(body.gen_settings))
    # 没带 world_id = 不改绑定（前端保存生成要求时提交的补丁里就没有它）
    if world is not UNSET:
        sets.append("world_id=?")
        vals.append(world)
    if sets:
        sets.append("updated_at=?")
        vals.append(now())
        vals.append(sid)
        db.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", vals)
        db.commit()
    return _session_detail(db, sid)


@router.delete("/sessions/{sid}")
def delete_session(sid: int, db=Depends(get_db)):
    session = _get_session(db, sid)
    # 消息由外键级联删除；director 会话的记忆一并删除
    if session["mode"] == "director":
        db.execute("DELETE FROM memories WHERE scope_type='session' AND scope_id=?", (sid,))
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.commit()
    return {"ok": True}


@router.get("/sessions/{sid}/messages")
def get_messages(sid: int, db=Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,)
    ).fetchall()
    return [dict(r) for r in rows]
