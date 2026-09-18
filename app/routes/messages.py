from fastapi import APIRouter, Depends, HTTPException

from ..database import connect, get_db, now
from ..generation import generation_response, prepare_generation
from ..schemas import MessageEdit

router = APIRouter(prefix="/api")


def _get_message(con, mid: int):
    row = con.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not row:
        raise HTTPException(404, "消息不存在")
    return row


def _touch_session(con, sid: int):
    con.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))


@router.put("/messages/{mid}")
def edit_message(mid: int, body: MessageEdit, db=Depends(get_db)):
    msg = _get_message(db, mid)
    sets, vals = ["content=?", "edited=1"], [body.content]
    # scenario 仅在显式传入时更新（显式传 null 表示清空情境）；未传则保持原值
    if "scenario" in body.model_fields_set:
        sets.append("scenario=?")
        vals.append(body.scenario)
    vals.append(mid)
    db.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id=?", vals)
    _touch_session(db, msg["session_id"])
    db.commit()
    return dict(_get_message(db, mid))


@router.delete("/messages/{mid}")
def delete_message(mid: int, cascade: bool = False, db=Depends(get_db)):
    msg = _get_message(db, mid)
    if cascade:
        db.execute(
            "DELETE FROM messages WHERE session_id=? AND id>=?",
            (msg["session_id"], mid),
        )
    else:
        db.execute("DELETE FROM messages WHERE id=?", (mid,))
    _touch_session(db, msg["session_id"])
    db.commit()
    return {"ok": True}


@router.post("/messages/{mid}/regenerate")
async def regenerate(mid: int):
    con = connect()
    try:
        msg = _get_message(con, mid)
        if msg["role"] != "assistant":
            raise HTTPException(400, "只能对生成消息触发重新生成")
        sid = msg["session_id"]
        con.execute("DELETE FROM messages WHERE session_id=? AND id>=?", (sid, mid))
        con.commit()
        msgs, model, mode = prepare_generation(con, sid)
    finally:
        con.close()
    return generation_response(sid, msgs, model, mode)
