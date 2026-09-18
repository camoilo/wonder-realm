import re

# [SCENARIO]/[DIALOG] 分段匹配；容错：不要求标记独占一行
SEGMENT = re.compile(
    r"\[(SCENARIO|DIALOG)\]\s*(.*?)(?=\n?\[(?:SCENARIO|DIALOG)\]|$)", re.S
)

MULTI = "MULTI"  # free_scenario 落库标记：content 存带标记全文，前端分段渲染


def parse_output(mode: str, raw: str) -> tuple[str | None, str]:
    """把模型原始输出解析为 (scenario, content)。

    角色对话模式原样返回；解析不出标记时整体降级为话语文本，不丢内容。
    """
    text = (raw or "").strip()
    if mode == "character_chat":
        return None, text

    segs = SEGMENT.findall(text)
    if not segs:
        return None, text

    if mode == "character_scenario":
        scenario = next((t.strip() for tag, t in segs if tag == "SCENARIO"), None)
        dialog = "\n".join(t.strip() for tag, t in segs if tag == "DIALOG")
        return (scenario or None), (dialog or text)

    return MULTI, text


def split_segments(raw: str) -> list[dict]:
    """分段渲染用：把带标记的全文切成 [{type, text}]，无标记时整体作话语。"""
    text = (raw or "").strip()
    segs = SEGMENT.findall(text)
    if not segs:
        return [{"type": "dialog", "text": text}]
    return [
        {"type": "scenario" if tag == "SCENARIO" else "dialog", "text": t.strip()}
        for tag, t in segs
    ]
