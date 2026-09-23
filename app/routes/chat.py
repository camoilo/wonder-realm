from fastapi import APIRouter

from ..database import connect, now
from ..generation import generation_response, load_generation_context, prepare_generation
from ..schemas import ChatIn

router = APIRouter(prefix="/api")


@router.post("/sessions/{sid}/chat")
async def chat(sid: int, body: ChatIn):
    con = connect()
    try:
        # 先校验再落 user 消息：角色已删除的会话不该再留下一条永远得不到回复的消息
        load_generation_context(con, sid)
        # 情境可选：只有话语时不写 NULL 之外的东西；去空白后为空就存 NULL，
        # 与"这条消息没有情境"保持同一种表示（messages.scenario 的 MULTI 是导演模式专用）
        scenario = (body.scenario or "").strip() or None
        cur = con.execute(
            "INSERT INTO messages(session_id, role, content, scenario, created_at) VALUES(?,?,?,?,?)",
            (sid, "user", body.message, scenario, now()),
        )
        user_id = cur.lastrowid
        con.commit()
        msgs, model, mode, options, defs = prepare_generation(con, sid)
    finally:
        con.close()
    return generation_response(
        sid, msgs, model, mode, options, meta={"message_id": user_id}, defs=defs
    )
