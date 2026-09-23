from fastapi import APIRouter, Depends, HTTPException

from ..database import clean_attrs, connect, get_db, now, parse_attrs
from ..generation import generation_response, load_generation_context, prepare_generation
from ..schemas import MessageEdit

router = APIRouter(prefix="/api")


def _get_message(con, mid: int):
    row = con.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not row:
        raise HTTPException(404, "消息不存在")
    return row


def message_payload(row) -> dict:
    """一条消息的对外形状：把 attrs 那列 JSON 解析成数组（前端不该自己解 JSON）。

    消息既从这里下发，也从 `/api/sessions/{id}/messages` 下发，所以解析只有这一处。
    """
    out = dict(row)
    if "attrs" in out:
        out["attrs"] = parse_attrs(out["attrs"])
    return out


def _touch_session(con, sid: int):
    con.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))


@router.put("/messages/{mid}")
def edit_message(mid: int, body: MessageEdit, db=Depends(get_db)):
    msg = _get_message(db, mid)
    # 允许"只有情境、没有台词"（模型可能只写了场景），但两者都空就不是一条消息了
    keeps_scenario = (
        body.scenario
        if "scenario" in body.model_fields_set
        else (msg["scenario"] if msg["scenario"] != "MULTI" else None)
    )
    if not body.content.strip() and not (keeps_scenario or "").strip():
        raise HTTPException(400, "消息内容不能为空")
    sets, vals = ["content=?", "edited=1"], [body.content]
    # scenario 仅在显式传入时更新（显式传 null 表示清空情境）；未传则保持原值
    if "scenario" in body.model_fields_set:
        sets.append("scenario=?")
        vals.append(body.scenario)
    # 附加属性同理：没带这一项就是不改（别的调用方只改正文时不该被清空）
    if "attrs" in body.model_fields_set and body.attrs is not None:
        sets.append("attrs=?")
        vals.append(clean_attrs([a.model_dump() for a in body.attrs]))
    vals.append(mid)
    db.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id=?", vals)
    _touch_session(db, msg["session_id"])
    db.commit()
    return message_payload(_get_message(db, mid))


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
        sid = msg["session_id"]
        # 先校验再删：角色已删除等情况下必须原样保留已有消息，不能删完才发现不能生成
        load_generation_context(con, sid)
        if msg["role"] == "assistant":
            # 替换式：连这条生成一起删掉，再重新生成
            con.execute("DELETE FROM messages WHERE session_id=? AND id>=?", (sid, mid))
        else:
            # 用户消息本身必须保留（它就是这轮的输入），只删它之后的内容再生成回复。
            # 主动停止生成后可能压根没有 assistant 消息，这条路径是唯一的补救入口。
            con.execute("DELETE FROM messages WHERE session_id=? AND id>?", (sid, mid))
        con.commit()
        msgs, model, mode, options, defs = prepare_generation(con, sid)
    finally:
        con.close()
    return generation_response(sid, msgs, model, mode, options, defs=defs)
