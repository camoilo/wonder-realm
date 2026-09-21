import asyncio
import json
import logging

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from . import memory, naming, ollama_client
from .database import connect, now, read_profile
from .parser import parse_output
from .prompts import build_messages, chat_options

log = logging.getLogger("ollama_agent")

_bg_tasks: set = set()


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def spawn(coro) -> None:
    """后台任务（记忆压缩、会话命名）：不阻塞响应，失败只记日志。"""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)  # 持引用防止被 GC
    task.add_done_callback(_bg_tasks.discard)


def load_generation_context(con, sid: int):
    """读取会话并校验可生成性：会话存在，角色模式的绑定角色仍在。

    单独抽出来是为了让调用方能在**改动数据之前**先校验——例如重新生成要先删消息，
    若把校验留在删之后，角色已删除时就会白删一截历史。
    """
    session = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session:
        raise HTTPException(404, "会话不存在")
    character = None
    if session["mode"] in ("character_chat", "character_scenario"):
        cid = session["character_id"]
        if cid is not None:
            character = con.execute(
                "SELECT * FROM characters WHERE id=?", (cid,)
            ).fetchone()
        if cid is None or character is None:
            raise HTTPException(400, "该会话绑定的角色已删除，无法继续生成")
    return session, character


def prepare_generation(con, sid: int):
    """读取会话/角色/记忆/未归档历史，组装模型输入。调用方负责连接生命周期。

    返回值带上 options（含本会话的发散程度），调用方原样交给 generation_response。
    """
    session, character = load_generation_context(con, sid)
    memory_content = ""
    scope = memory.scope_for_session(session)
    if scope:
        row = memory.read_memory(con, scope)
        memory_content = row["content"] if row else ""
    rows = con.execute(
        "SELECT role, content, scenario FROM messages "
        "WHERE session_id=? AND archived=0 ORDER BY id",
        (sid,),
    ).fetchall()
    model = con.execute("SELECT model FROM app_settings WHERE id=1").fetchone()["model"]
    # "我的设定"是全局单行，跟着一起组装；自由情境模式在 prompts 里会忽略它
    msgs = build_messages(session, character, memory_content, rows, read_profile())
    return msgs, model, session["mode"], chat_options(session)


def persist_message(sid: int, mode: str, raw: str) -> tuple[int | None, str, str | None]:
    """解析并落库一条生成消息，返回 (message_id, content, scenario)。

    raw 为空、解析后既无正文也无情境时不落库，返回 (None, "", None)，由调用方决定如何提示。
    "只有情境、没有台词"也算有效内容——那正是模型输出的东西，不该丢。
    """
    raw = (raw or "").strip()
    if not raw:
        return None, "", None
    scenario, content = parse_output(mode, raw)
    if not content.strip() and not (scenario and scenario != "MULTI"):
        return None, "", None
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO messages(session_id, role, content, scenario, created_at) "
            "VALUES(?,?,?,?,?)",
            (sid, "assistant", content, scenario, now()),
        )
        con.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))
        con.commit()
        return cur.lastrowid, content, scenario
    finally:
        con.close()


def generation_response(
    sid: int, msgs: list, model: str, mode: str, options: dict | None = None,
    meta: dict | None = None,
):
    """SSE 流：生成 → 解析 → 落库 → done。chat 传 meta（user 消息 id），regenerate 不传。

    options 来自 prepare_generation()，带着本会话的发散程度；不传则用 config 的默认值。
    """

    async def gen():
        parts = []
        if meta is not None:
            yield sse("meta", meta)
        try:
            async for kind, value in ollama_client.chat_stream(msgs, model, options):
                if kind == "delta":
                    parts.append(value)
                    yield sse("delta", {"text": value})
                else:
                    yield sse("status", {"phase": value})
        except asyncio.CancelledError:
            # 用户点了「停止」：客户端断开使本生成器被取消。
            # 已经流出的部分照常落库，只是没有 done 事件（前端靠重新拉取消息同步）。
            message_id, content, _ = persist_message(sid, mode, "".join(parts))
            if message_id is None:
                log.info("生成被停止（会话 %s），尚无内容可保留", sid)
            else:
                log.info("生成被停止（会话 %s），保留 %d 字", sid, len(content))
                spawn(memory.maybe_compress(sid))
            raise
        except Exception as e:  # Ollama 连接失败 / 响应异常
            log.warning("生成失败（会话 %s）：%s", sid, e)
            yield sse("error", {"message": f"生成失败：{e}"})
            return
        message_id, content, scenario = persist_message(sid, mode, "".join(parts))
        if message_id is None:
            yield sse("error", {"message": "模型未返回内容"})
            return
        spawn(memory.maybe_compress(sid))
        spawn(naming.maybe_autoname(sid))
        yield sse("done", {"message_id": message_id, "content": content, "scenario": scenario})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
