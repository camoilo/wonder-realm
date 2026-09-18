from fastapi import APIRouter, Depends, HTTPException

from ..database import get_db, now
from ..schemas import CharacterIn

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
    return [dict(r) | {"session_count": counts.get(r["id"], 0)} for r in rows]


@router.post("/characters")
def create_character(body: CharacterIn, db=Depends(get_db)):
    cur = db.execute(
        "INSERT INTO characters(name, appearance, personality, speech_style, backstory, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            body.name.strip(),
            body.appearance.strip(),
            body.personality.strip(),
            body.speech_style.strip(),
            body.backstory.strip(),
            now(),
            now(),
        ),
    )
    db.commit()
    return dict(_get_character(db, cur.lastrowid))


@router.get("/characters/{cid}")
def get_character(cid: int, db=Depends(get_db)):
    return dict(_get_character(db, cid))


@router.put("/characters/{cid}")
def update_character(cid: int, body: CharacterIn, db=Depends(get_db)):
    _get_character(db, cid)
    db.execute(
        "UPDATE characters SET name=?, appearance=?, personality=?, speech_style=?, backstory=?, updated_at=? "
        "WHERE id=?",
        (
            body.name.strip(),
            body.appearance.strip(),
            body.personality.strip(),
            body.speech_style.strip(),
            body.backstory.strip(),
            now(),
            cid,
        ),
    )
    db.commit()
    return dict(_get_character(db, cid))


@router.delete("/characters/{cid}")
def delete_character(cid: int, db=Depends(get_db)):
    _get_character(db, cid)
    # 会话由外键 ON DELETE SET NULL 保留；角色记忆删除
    db.execute("DELETE FROM memories WHERE scope_type='character' AND scope_id=?", (cid,))
    db.execute("DELETE FROM characters WHERE id=?", (cid,))
    db.commit()
    return {"ok": True}
