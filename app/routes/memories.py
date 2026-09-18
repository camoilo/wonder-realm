from fastapi import APIRouter, Depends, HTTPException

from .. import memory
from ..database import get_db, now
from ..schemas import MemoryEdit

router = APIRouter(prefix="/api")


def _payload(con, scope: tuple[str, int]) -> dict:
    row = memory.read_memory(con, scope)
    status = memory.compress_status(scope)
    return {
        "content": row["content"] if row else "",
        "message_count": row["message_count"] if row else 0,
        "updated_at": row["updated_at"] if row else None,
        "compress_failed": status["failed"],
    }


def _upsert(con, scope: tuple[str, int], content: str):
    con.execute(
        "INSERT INTO memories(scope_type, scope_id, content, message_count, updated_at) "
        "VALUES(?,?,?,0,?) "
        "ON CONFLICT(scope_type, scope_id) DO UPDATE SET "
        "content=excluded.content, updated_at=excluded.updated_at",
        (scope[0], scope[1], content, now()),
    )
    con.commit()


def _character_scope(con, cid: int) -> tuple[str, int]:
    if not con.execute("SELECT id FROM characters WHERE id=?", (cid,)).fetchone():
        raise HTTPException(404, "角色不存在")
    return ("character", cid)


def _session_scope(con, sid: int) -> tuple[str, int]:
    s = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "会话不存在")
    if s["mode"] != "free_scenario":
        raise HTTPException(400, "仅情境生成模式的会话有会话级记忆")
    return ("session", sid)


@router.get("/memories/character/{cid}")
def get_character_memory(cid: int, db=Depends(get_db)):
    return _payload(db, _character_scope(db, cid))


@router.put("/memories/character/{cid}")
def put_character_memory(cid: int, body: MemoryEdit, db=Depends(get_db)):
    scope = _character_scope(db, cid)
    _upsert(db, scope, body.content)
    return _payload(db, scope)


@router.get("/memories/session/{sid}")
def get_session_memory(sid: int, db=Depends(get_db)):
    return _payload(db, _session_scope(db, sid))


@router.put("/memories/session/{sid}")
def put_session_memory(sid: int, body: MemoryEdit, db=Depends(get_db)):
    scope = _session_scope(db, sid)
    _upsert(db, scope, body.content)
    return _payload(db, scope)
