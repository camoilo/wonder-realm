import re

# 标记识别刻意宽容：实测模型会写成 [SCENERY]、[SCENE]、小写、甚至全角括号。
# 宽容只影响"能不能认出标记"，不改变我们要求模型输出什么（提示词里仍严格要求
# [SCENARIO]/[DIALOG]）——目的是让一次用词偏差不至于把整条消息打成纯文本。
SCENARIO_TAGS = ("SCENARIO", "SCENERY", "SCENE", "NARRATION", "SETTING", "CONTEXT")
DIALOG_TAGS = ("DIALOG", "DIALOGUE", "SPEECH", "TALK")
_ALL_TAGS = SCENARIO_TAGS + DIALOG_TAGS

_TAG = r"[\[【]\s*(?:" + "|".join(_ALL_TAGS) + r")\s*[\]】]"

# 一段 = 标记 + 到下一个标记（或结尾）为止的内容；不要求标记独占一行
SEGMENT = re.compile(
    r"[\[【]\s*(" + "|".join(_ALL_TAGS) + r")\s*[\]】]\s*(.*?)(?=\n?" + _TAG + r"|$)",
    re.S | re.I,
)

MULTI = "MULTI"  # free_scenario 落库标记：content 存带标记全文，前端分段渲染


def _is_scenario(tag: str) -> bool:
    return tag.upper() in SCENARIO_TAGS


def _pieces(text: str) -> list[tuple[str, str]]:
    """把全文切成 [(类型, 内容)]，类型为 "scenario" / "dialog"。

    两个容错点都来自实际遇到的输出：
    1. 标记之外的裸文本按话语算——模型常把台词写在第一个标记之前（顺序颠倒）。
    2. 内容为空的标记直接跳过，不产生空段落。
    """
    out: list[tuple[str, str]] = []
    last = 0
    for m in SEGMENT.finditer(text):
        head = text[last:m.start()].strip()
        if head:
            out.append(("dialog", head))
        body = m.group(2).strip()
        if body:
            out.append(("scenario" if _is_scenario(m.group(1)) else "dialog", body))
        last = m.end()
    tail = text[last:].strip()
    if tail:
        out.append(("dialog", tail))
    return out


def parse_output(mode: str, raw: str) -> tuple[str | None, str]:
    """把模型原始输出解析为 (scenario, content)。

    角色对话模式原样返回；完全认不出标记时整体降级为话语文本，不丢内容。
    角色情境模式下允许"只有情境、没有台词"：此时 content 为空串、scenario 有值，
    由调用方决定是否落库（见 generation.persist_message）。
    """
    text = (raw or "").strip()
    if mode == "character_chat":
        return None, text

    # 必须区分"有没有出现标记"和"切出了什么段落"：无标记时 _pieces 也会把整段
    # 当成话语返回，若用它来判断就会把纯文本误标成 MULTI（free_scenario 的降级路径）
    found = SEGMENT.search(text)
    pieces = _pieces(text)
    if not pieces:
        # 有标记但全是空的（例如模型只吐了个 [DIALOG]）：当作没内容，
        # 否则会把裸标记当正文显示给用户
        return (None, "") if found else (None, text)

    if mode == "character_scenario":
        # 情境可能被拆成多段，合并保留——只取第一段会静默丢掉后面的内容
        scenario = "\n".join(t for kind, t in pieces if kind == "scenario").strip()
        dialog = "\n".join(t for kind, t in pieces if kind == "dialog").strip()
        return (scenario or None), dialog

    # free_scenario：只在真的出现标记时才走分段渲染，否则与角色情境一样降级
    return (MULTI if found else None), text


def split_segments(raw: str) -> list[dict]:
    """分段渲染用：把带标记的全文切成 [{type, text}]，完全无标记时整体作话语。"""
    text = (raw or "").strip()
    pieces = _pieces(text)
    if pieces:
        return [{"type": kind, "text": body} for kind, body in pieces]
    if SEGMENT.search(text):
        return []  # 只有空标记：没有可渲染的内容
    return [{"type": "dialog", "text": text}]
