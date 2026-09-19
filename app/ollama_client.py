import asyncio
import json
import re

import httpx

from .config import get_config
from .database import thinking_disabled


class ThinkFilter:
    """流式 <think> 过滤器。feed() 返回 (正文增量, 是否处于思考态)。"""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""  # 未决缓冲：可能含被 chunk 边界拆开的半个标签
        self.in_think = False

    def feed(self, chunk: str):
        self.buf += chunk
        out = []
        while True:
            tag = self.CLOSE if self.in_think else self.OPEN
            i = self.buf.find(tag)
            if i < 0:  # 无完整标签：留出可能是标签前缀的尾巴
                keep = len(tag) - 1
                if len(self.buf) > keep:
                    head, self.buf = self.buf[:-keep], self.buf[-keep:]
                    if not self.in_think:
                        out.append(head)
                break
            if not self.in_think:
                out.append(self.buf[:i])
            self.in_think = not self.in_think
            self.buf = self.buf[i + len(tag):]
        return "".join(out), self.in_think

    def flush(self) -> str:
        """流结束：思考态未闭合说明全程无正文，返回空串；否则放出残尾。"""
        if self.in_think:
            return ""
        out, self.buf = self.buf, ""
        return out


def _payload(model: str, messages: list[dict], stream: bool, options: dict | None) -> dict:
    """组装请求体，并在用户关掉思考模式时带上 think=False。

    只可能发 False，永远不会发 True：实测非思考型模型收到 think=True 会直接 400
    （"does not support thinking"），而 think=False 它们照收不误。所以"关"是安全的方向，
    "开"不是——要开就别传这个参数，让模型自己决定。
    """
    cfg = get_config()["ollama"]
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": options or cfg["options"],
    }
    if thinking_disabled():
        payload["think"] = False
    return payload


async def chat_stream(messages: list[dict], model: str, options: dict | None = None):
    """流式调用 Ollama /api/chat，兼容有无思考模式的模型。

    yield (kind, value)：("status", "thinking"/"generating") 或 ("delta", 正文增量)。
    """
    cfg = get_config()["ollama"]
    payload = _payload(model, messages, True, options)
    tf = ThinkFilter()
    saw_thinking = False
    saw_content = False
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as client:
        async with client.stream(
            "POST", f"{cfg['base_url']}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                msg = chunk.get("message") or {}
                if msg.get("thinking") and not saw_thinking:
                    saw_thinking = True
                    yield ("status", "thinking")
                text = msg.get("content", "")
                if text:
                    out, in_think = tf.feed(text)
                    if in_think and not saw_thinking:
                        saw_thinking = True
                        yield ("status", "thinking")
                    if out:
                        if not saw_content:
                            saw_content = True
                            yield ("status", "generating")
                        yield ("delta", out)
                if chunk.get("done"):
                    break
    tail = tf.flush()
    if tail:
        if not saw_content:
            yield ("status", "generating")
        yield ("delta", tail)


async def chat_once(messages: list[dict], model: str, options: dict | None = None) -> str:
    """非流式调用（记忆压缩、会话命名用），返回剥离思考段后的正文。"""
    cfg = get_config()["ollama"]
    payload = _payload(model, messages, False, options)
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
        resp = await client.post(f"{cfg['base_url']}/api/chat", json=payload)
        resp.raise_for_status()
        content = (resp.json().get("message") or {}).get("content", "")
    return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()


async def list_models() -> list[dict]:
    """已安装模型列表，thinking 标记是否为思考型模型。

    取 /api/tags 与 /api/show 两处 capabilities 的**并集**：实测两者会对同一模型给出不同
    结果（sorc/qwen3.5-instruct-uncensored:4b 在 tags 里缺 thinking、show 里有），只信
    tags 会漏标。show 是按模型逐个查，所以并发发出去；查不到就退化成只用 tags 的结果。
    """
    cfg = get_config()["ollama"]
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{cfg['base_url']}/api/tags")
        resp.raise_for_status()
        models = resp.json().get("models", [])

        async def caps(name: str, from_tags) -> set:
            try:
                r = await client.post(f"{cfg['base_url']}/api/show", json={"model": name})
                r.raise_for_status()
                from_show = r.json().get("capabilities") or []
            except (httpx.HTTPError, ValueError):
                from_show = []
            return set(from_tags or []) | set(from_show)

        merged = await asyncio.gather(*(caps(m["name"], m.get("capabilities")) for m in models))

    return [
        {"name": m["name"], "thinking": "thinking" in c}
        for m, c in zip(models, merged)
    ]
