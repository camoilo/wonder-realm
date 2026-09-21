import logging

from . import ollama_client
from .config import get_config
from .database import connect, now

log = logging.getLogger("ollama_agent")

COMPRESS_PROMPT = """以下是关于角色「{name}」的现有记忆：
{old_memory}

以下是新增的对话记录：
{dialog}

请把新对话中值得长期记住的信息合并进现有记忆，输出更新后的完整记忆。
只保留：重要事件、双方透露的个人信息、关系变化、约定与承诺、关键剧情走向。
丢弃寒暄和重复内容。用条目列表（- 开头）输出，总长度不超过 {max_chars} 字。
只输出记忆内容本身。"""

_running: set[tuple[str, int]] = set()
_status: dict[tuple[str, int], dict] = {}


def scope_for_session(session) -> tuple[str, int] | None:
    if session["mode"] in ("character_chat", "character_scenario"):
        if session["character_id"] is None:
            return None
        return ("character", session["character_id"])
    if session["mode"] == "free_scenario":
        return ("session", session["id"])
    return None


def read_memory(con, scope: tuple[str, int]):
    return con.execute(
        "SELECT * FROM memories WHERE scope_type=? AND scope_id=?", scope
    ).fetchone()


def compress_status(scope: tuple[str, int]) -> dict:
    return _status.get(scope, {"failed": False, "at": None})


async def maybe_compress(session_id: int) -> None:
    """会话未归档内容超过阈值时，把最早一批消息压缩进长期记忆。失败静默重试。"""
    cfg = get_config()["memory"]
    con = connect()
    try:
        session = con.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not session:
            return
        scope = scope_for_session(session)
        if not scope:
            return
        row = con.execute(
            "SELECT COALESCE(SUM(LENGTH(content)), 0) AS chars FROM messages "
            "WHERE session_id=? AND archived=0",
            (session_id,),
        ).fetchone()
        if row["chars"] < cfg["compress_threshold_chars"]:
            return
        batch = con.execute(
            "SELECT id, role, content FROM messages WHERE session_id=? AND archived=0 "
            "ORDER BY id LIMIT ?",
            (session_id, cfg["archive_batch_size"]),
        ).fetchall()
        if not batch:
            return
        name = "本次创作"
        if scope[0] == "character":
            c = con.execute(
                "SELECT name FROM characters WHERE id=?", (scope[1],)
            ).fetchone()
            if c:
                name = c["name"]
        old = read_memory(con, scope)
        old_memory = old["content"] if old else "（无）"
        dialog = "\n".join(
            f"{'user' if r['role'] == 'user' else name}: {r['content']}" for r in batch
        )
        prompt = COMPRESS_PROMPT.format(
            name=name,
            old_memory=old_memory,
            dialog=dialog,
            max_chars=cfg["max_memory_chars"],
        )
        settings = con.execute(
            "SELECT model, memory_model FROM app_settings WHERE id=1"
        ).fetchone()
        model = settings["memory_model"] or settings["model"]
    finally:
        con.close()

    if not model:
        # 还没选模型（首次使用）：这次不压缩，下一轮生成时再试——记忆是附带功能，
        # 不该因为没选模型就报错打断对话
        log.info("还没有选择模型，跳过记忆压缩")
        return
    if scope in _running:  # 同 scope 已有压缩在途，避免重复合并覆盖
        return
    _running.add(scope)
    try:
        opts = dict(get_config()["ollama"]["options"])
        opts["temperature"] = 0.3
        result = await ollama_client.chat_once(
            [{"role": "user", "content": prompt}], model, opts
        )
        if not result.strip():
            raise ValueError("压缩结果为空")
        con = connect()
        try:
            con.execute(
                "INSERT INTO memories(scope_type, scope_id, content, message_count, updated_at) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(scope_type, scope_id) DO UPDATE SET "
                "content=excluded.content, message_count=message_count+excluded.message_count, "
                "updated_at=excluded.updated_at",
                (scope[0], scope[1], result.strip(), len(batch), now()),
            )
            ids = [r["id"] for r in batch]
            con.execute(
                f"UPDATE messages SET archived=1 "
                f"WHERE id IN ({','.join('?' * len(ids))}) AND archived=0",
                ids,
            )
            con.commit()
        finally:
            con.close()
        _status[scope] = {"failed": False, "at": now()}
        log.info("记忆压缩完成（%s %s）：归档 %d 条", scope[0], scope[1], len(ids))
    except Exception as e:
        _status[scope] = {"failed": True, "at": now()}
        log.warning("记忆压缩失败（%s %s）：%s", scope[0], scope[1], e)
    finally:
        _running.discard(scope)
