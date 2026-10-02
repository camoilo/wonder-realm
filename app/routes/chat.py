from fastapi import APIRouter

from ..database import connect, now
from ..generation import (
    generation_response,
    load_generation_context,
    prepare_generation,
    stop_all,
)
from ..schemas import ChatIn

router = APIRouter(prefix="/api")


@router.post("/generate/stop")
def stop_generating():
    """停止当前所有正在进行的生成（三端通用：手机、电脑、多开窗口）。

    只让流尽快收尾，不删任何东西：已经流出的部分照常落库（与「停止」键同一种语义）。
    角色生成是普通请求、记忆压缩与会话命名是后台任务，它们跑在别的路径上，
    这里管不到——它们各自有超时，也不会阻塞对话。
    """
    return {"ok": True, "epoch": stop_all()}


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
