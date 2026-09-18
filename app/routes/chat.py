from fastapi import APIRouter, HTTPException

from ..database import connect, now
from ..generation import generation_response, prepare_generation
from ..schemas import ChatIn

router = APIRouter(prefix="/api")


@router.post("/sessions/{sid}/chat")
async def chat(sid: int, body: ChatIn):
    con = connect()
    try:
        row = con.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "会话不存在")
        cur = con.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
            (sid, "user", body.message, now()),
        )
        user_id = cur.lastrowid
        con.commit()
        msgs, model, mode = prepare_generation(con, sid)
    finally:
        con.close()
    return generation_response(sid, msgs, model, mode, meta={"message_id": user_id})
