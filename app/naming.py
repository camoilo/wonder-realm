import logging
import re

from . import ollama_client
from .config import get_config
from .database import connect

log = logging.getLogger("ollama_agent")

NAME_PROMPT = """请根据用户在下面这些发言，概括这次对话的主题并起一个标题。
要求：不超过 {max_chars} 个字，只写标题本身，不要标点、引号或"标题："之类的前缀。

用户说过的话：
{user}"""

_running: set[int] = set()

_PREFIX = re.compile(r"^\s*(标题|标题名|题目|主题)\s*[:：]\s*")
_QUOTES = "\"'“”‘’《》【】〈〉「」"
_PUNCT = "。．.!！?？,，、;；:：~～-—"


def _clean(raw: str, max_chars: int) -> str:
    """把模型输出规整成可直接当标题用的短句。"""
    text = (raw or "").strip()
    if not text:
        return ""
    # 思考型模型可能残留推理段：先去掉闭合的整段，再截断未闭合的
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    if "<think>" in text:
        text = text.split("<think>")[0]
    text = text.splitlines()[0].strip() if text.strip() else ""
    text = _PREFIX.sub("", text)
    text = text.strip(_QUOTES).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text.strip(_PUNCT).strip()


async def maybe_autoname(session_id: int) -> None:
    """首轮对话结束后用模型总结标题。

    只对「创建时未指定标题」（title_auto=1）的会话生效，成功后置 title_auto=0，
    因此每个会话至多自动命名一次；失败不置位，下一轮生成会重试。
    """
    if session_id in _running:  # 同名会话已在命名中，避免并发覆盖
        return
    cfg = get_config()
    max_chars = cfg["naming"]["max_chars"]
    min_user_chars = cfg["naming"]["min_user_chars"]
    con = connect()
    try:
        session = con.execute(
            "SELECT id, title_auto FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not session or not session["title_auto"]:
            return
        rows = con.execute(
            "SELECT role, content FROM messages "
            "WHERE session_id=? AND archived=0 ORDER BY id LIMIT 12",
            (session_id,),
        ).fetchall()
        # 只取用户说过的话：角色回复本身是带着长期记忆生成的，
        # 把回复喂给命名提示词会把旧记忆的内容混进标题，导致命名跑偏。
        user_text = " / ".join(
            r["content"].strip() for r in rows if r["role"] == "user" and r["content"].strip()
        )
        if len(user_text) < min_user_chars:
            return  # 用户还没说出有信息量的内容，等下一轮生成再试
        settings = con.execute(
            "SELECT model, memory_model FROM app_settings WHERE id=1"
        ).fetchone()
        model = (
            cfg["naming"]["model"] or settings["memory_model"] or settings["model"]
        )
    finally:
        con.close()

    _running.add(session_id)
    try:
        opts = dict(cfg["ollama"]["options"])
        opts["temperature"] = 0.3
        prompt = NAME_PROMPT.format(max_chars=max_chars, user=user_text[:300])
        raw = await ollama_client.chat_once(
            [{"role": "user", "content": prompt}], model, opts
        )
        title = _clean(raw, max_chars)
        if not title:
            raise ValueError("标题为空")
        con = connect()
        try:
            # 条件里再校验 title_auto：避免命名期间用户手动重命名被覆盖
            con.execute(
                "UPDATE sessions SET title=?, title_auto=0 WHERE id=? AND title_auto=1",
                (title, session_id),
            )
            con.commit()
        finally:
            con.close()
        log.info("会话 %s 自动命名为「%s」", session_id, title)
    except Exception as e:
        log.warning("会话自动命名失败（%s）：%s", session_id, e)
    finally:
        _running.discard(session_id)
