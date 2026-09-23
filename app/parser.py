import re

# 标记识别刻意宽容：实测模型会写成 [SCENERY]、[SCENE]、小写、甚至全角括号。
# 宽容只影响"能不能认出标记"，不改变我们要求模型输出什么（提示词里仍严格要求
# [SCENARIO]/[DIALOG]）——目的是让一次用词偏差不至于把整条消息打成纯文本。
SCENARIO_TAGS = ("SCENARIO", "SCENERY", "SCENE", "NARRATION", "SETTING", "CONTEXT")
DIALOG_TAGS = ("DIALOG", "DIALOGUE", "SPEECH", "TALK")
# 附加属性块（见 DEVELOPMENT §2.6）：同一套宽容，模型写 [STATUS]/[STATE] 也认
ATTR_TAGS = ("ATTR", "ATTRS", "ATTRIBUTE", "ATTRIBUTES", "STATUS", "STATE")
_ALL_TAGS = SCENARIO_TAGS + DIALOG_TAGS

_TAG = r"[\[【]\s*(?:" + "|".join(_ALL_TAGS) + r")\s*[\]】]"
_ATTR_TAG = r"[\[【]\s*(?:" + "|".join(ATTR_TAGS) + r")\s*[\]】]"

# 一段 = 标记 + 到下一个标记（或结尾）为止的内容；不要求标记独占一行
SEGMENT = re.compile(
    r"[\[【]\s*(" + "|".join(_ALL_TAGS) + r")\s*[\]】]\s*(.*?)(?=\n?" + _TAG + r"|$)",
    re.S | re.I,
)

# 属性块：从标记起到"下一个已知标记"或结尾。允许模型多写一个 [/ATTR] 收尾（顺手删掉）
_ATTR_SEGMENT = re.compile(
    r"[\[【]\s*(?:" + "|".join(ATTR_TAGS) + r")\s*[\]】]\s*(.*?)(?=\n?" + _TAG + r"|$)",
    re.S | re.I,
)
_ATTR_CLOSE = re.compile(r"[\[【]\s*/\s*(?:" + "|".join(ATTR_TAGS) + r")\s*[\]】]", re.I)

# 一行属性：名称 + 分隔符 + 值。分隔符宽容到全角冒号、半角冒号与等号；
# 名称里**不许出现标点与空白**，这样"好：我这就去"这类台词不会被误当成属性行
_ATTR_LINE = re.compile(r"^([^:：=，。!！?？\s]{1,20}?)\s*[:：=]\s*(.*)$")

MULTI = "MULTI"  # director 落库标记：content 存带标记全文，前端分段渲染


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


def split_attrs(raw: str) -> tuple[str, str]:
    """把附加属性块从输出里摘出来：返回 (去掉属性块的正文, 属性块内容)。

    **必须先摘再解析正文**：`_pieces` 会把标记之外的裸文本当成台词，属性块若留着，
    "好感：42" 就会当成角色说的话漏进气泡里。位置不敏感（取最后一个属性块），
    因为提示词要求它放在最后、但模型偶尔会插在中间。

    块里"最后一条属性行"之后的内容会**还回正文**——一次位置偏差不该静默吞掉一句话。
    认不出标记就原样返回：宁可属性拿不到，也不能吞掉正文。
    """
    text = raw or ""
    last = None
    for m in _ATTR_SEGMENT.finditer(text):
        last = m
    if last is None:
        return text, ""
    inner = _ATTR_CLOSE.sub("", last.group(1))
    lines = inner.splitlines()
    keep = 0
    for i, line in enumerate(lines):
        if _ATTR_LINE.match(line.strip().lstrip("-•*").strip()):
            keep = i + 1
    block = "\n".join(lines[:keep])
    salvaged = "\n".join(line for line in lines[keep:] if line.strip())
    head = text[: last.start()] + text[last.end():]
    if salvaged:
        head = f"{head.rstrip()}\n{salvaged}" if head.strip() else salvaged
    return head, block


def parse_attrs(block: str, defs) -> list[dict]:
    """属性块 + 定义 → `[{name, type, value}]`。

    只认定义里有的名字（定义是唯一依据，模型自己编的条目丢掉）；定义里有、模型没写的
    那条**不在这里补**——补值需要"上一轮的值"，那是调用方的事（见 generation.py）。
    百分比型从值里抠第一个数字并夹到 0-100；文字型直接取整行。
    """
    wanted = {d["name"]: d for d in (defs or [])}
    out = []
    for line in (block or "").splitlines():
        line = line.strip().lstrip("-•*").strip()
        if not line:
            continue
        m = _ATTR_LINE.match(line)
        if not m:
            continue
        name = m.group(1).strip().strip("【】[]").strip()
        d = wanted.get(name)
        if d is None:
            continue
        value = m.group(2).strip()
        if d["type"] == "percent":
            num = re.search(r"-?\d+(?:\.\d+)?", value)
            if not num:
                continue
            value = max(0.0, min(100.0, float(num.group(0))))
        elif not value:
            continue
        out.append({"name": name, "type": d["type"], "value": value})
    return out


def parse_output(mode: str, raw: str) -> tuple[str | None, str]:
    """把模型原始输出解析为 (scenario, content)。

    聊天模式原样返回；完全认不出标记时整体降级为话语文本，不丢内容。
    沉浸模式下允许"只有情境、没有台词"：此时 content 为空串、scenario 有值，
    由调用方决定是否落库（见 generation.persist_message）。
    """
    text = (raw or "").strip()
    if mode == "chat":
        return None, text

    # 必须区分"有没有出现标记"和"切出了什么段落"：无标记时 _pieces 也会把整段
    # 当成话语返回，若用它来判断就会把纯文本误标成 MULTI（director 的降级路径）
    found = SEGMENT.search(text)
    pieces = _pieces(text)
    if not pieces:
        # 有标记但全是空的（例如模型只吐了个 [DIALOG]）：当作没内容，
        # 否则会把裸标记当正文显示给用户
        return (None, "") if found else (None, text)

    if mode == "immersive":
        # 情境可能被拆成多段，合并保留——只取第一段会静默丢掉后面的内容
        scenario = "\n".join(t for kind, t in pieces if kind == "scenario").strip()
        dialog = "\n".join(t for kind, t in pieces if kind == "dialog").strip()
        return (scenario or None), dialog

    # director：只在真的出现标记时才走分段渲染，否则与沉浸模式一样降级
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
