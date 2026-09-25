import json

from .config import get_config
from .limits import LIMITS

REPLY_LENGTH_DESC = {
    "short": "每次回复不超过2句话",
    "medium": "每次回复2到4句话",
    "long": "每次回复可以详细展开",
}

PROACTIVE_DESC = {
    "low": "被动回应即可，不要主动抛出新话题",
    "medium": "适度主动，偶尔推进话题",
    "high": "主动抛出新话题，积极推进对话",
}

SCENARIO_LENGTH_DESC = {
    "short": "情境说明用1句话",
    "medium": "情境说明用1到3句话",
    "long": "情境说明3句话以上，可以充分铺陈",
}

PACE_DESC = {
    "slow": "剧情推进平缓，多停留于当下氛围",
    "medium": "剧情推进节奏适中",
    "fast": "剧情推进快速，尽快进入新的事件",
}

FREE_LENGTH_DESC = {
    "short": "单次生成篇幅简短",
    "medium": "单次生成长度适中",
    "long": "单次生成篇幅较长，可以充分展开",
}

COMPOSITION_DESC = {
    "scenario_only": "只写情境，不要输出任何 [DIALOG] 台词",
    "scenario_heavy": "以情境为主，情境可以铺陈多段，台词只作少量点缀",
    "balanced": "情境与台词大致均衡，按剧情需要自然安排",
    "dialog_heavy": "以台词为主，情境只作简短交代",
}

# 「发散程度」档位：界面上只显示四个标签，数值不出现在界面上。它不是提示词内容，
# 而是覆盖请求里的 options.temperature（见 2.3、chat_options()）。
TEMPERATURE_LEVELS = {
    "strict": 0.2,
    "steady": 0.6,
    "standard": 0.9,
    "wild": 1.3,
}

TEMPERATURE_OPTIONS = [
    ("strict", "严谨"),
    ("steady", "稳定"),
    ("standard", "标准"),
    ("wild", "放飞"),
]

DEFAULT_SETTINGS = {
    "chat": {
        "reply_length": "medium",
        "proactive": "medium",
        "temperature": "standard",
        "extra": "",
    },
    "immersive": {
        "scenario_length": "medium",
        "pace": "medium",
        "temperature": "standard",
        "director_notes": "",
        "extra": "",
    },
    "director": {
        "genre": "",
        "style": "",
        "length": "medium",
        "composition": "balanced",
        "temperature": "standard",
        "extra": "",
    },
}

# 三种模式共用的「发散程度」字段定义
TEMPERATURE_FIELD = {
    "key": "temperature", "label": "发散程度", "type": "radio",
    "hint": "只影响生成的随机程度，不写进提示词",
    "options": TEMPERATURE_OPTIONS,
}

# 生成要求表单字段定义，供前端渲染（GET /api/gen-settings）。
# 自由文本字段带 "max"：前端据此设 maxlength 并显示右下角计数，数字来自 limits.LIMITS，
# 不在前端另写一份
FIELDS = {
    "chat": [
        {"key": "reply_length", "label": "回复长度", "type": "radio",
         "options": [("short", "简短"), ("medium", "适中"), ("long", "详细")]},
        {"key": "proactive", "label": "主动性", "type": "radio",
         "options": [("low", "低"), ("medium", "中"), ("high", "高")]},
        TEMPERATURE_FIELD,
        {"key": "extra", "label": "附加要求", "type": "textarea", "max": LIMITS["extra"],
         "placeholder": "任意补充要求，原样注入提示词"},
    ],
    "immersive": [
        {"key": "scenario_length", "label": "情境篇幅", "type": "radio",
         "options": [("short", "简短"), ("medium", "适中"), ("long", "详细")]},
        {"key": "pace", "label": "推进速度", "type": "radio",
         "options": [("slow", "平缓"), ("medium", "适中"), ("fast", "快速")]},
        TEMPERATURE_FIELD,
        {"key": "director_notes", "label": "导演指令", "type": "textarea", "max": LIMITS["extra"],
         "hint": "只影响情境走向，不进入对话", "placeholder": "如：让两人的关系逐渐缓和"},
        {"key": "extra", "label": "附加要求", "type": "textarea", "max": LIMITS["extra"]},
    ],
    "director": [
        {"key": "genre", "label": "题材", "type": "text", "max": LIMITS["genre"],
         "placeholder": "如：都市奇幻、武侠"},
        {"key": "style", "label": "文风", "type": "text", "max": LIMITS["genre"],
         "placeholder": "如：细腻文学风、轻喜剧"},
        {"key": "length", "label": "单次篇幅", "type": "radio",
         "options": [("short", "短"), ("medium", "中"), ("long", "长")]},
        {"key": "composition", "label": "情境/台词配比", "type": "radio",
         "hint": "决定情境与台词各占多少，可只写情境",
         "options": [("scenario_only", "只有情境"), ("scenario_heavy", "情境为主"),
                     ("balanced", "均衡"), ("dialog_heavy", "台词为主")]},
        TEMPERATURE_FIELD,
        {"key": "extra", "label": "附加要求", "type": "textarea", "max": LIMITS["extra"]},
    ],
}


def get_gen_settings(session) -> dict:
    try:
        stored = json.loads(session["gen_settings"] or "{}")
    except (json.JSONDecodeError, TypeError):
        stored = {}
    merged = dict(DEFAULT_SETTINGS.get(session["mode"], {}))
    merged.update({k: v for k, v in stored.items() if v})
    return merged


def _join(parts: list[str]) -> str:
    return "；".join(p for p in parts if p) + "。"


def chat_options(session) -> dict:
    """生成用的 Ollama options：config 的 options 打底，按会话的「发散程度」覆盖 temperature。

    档位缺失或不是已知档位时保持 config 的值（旧会话、或有人直接往 gen_settings 里塞了怪值）。
    记忆压缩与会话命名不走这里——它们自己把 temperature 压到 0.3（见 memory.py、naming.py）。
    """
    opts = dict(get_config()["ollama"]["options"])
    value = TEMPERATURE_LEVELS.get(get_gen_settings(session).get("temperature"))
    if value is not None:
        opts["temperature"] = value
    return opts


def render_chat_settings(s: dict) -> str:
    parts = [
        f"回复长度：{REPLY_LENGTH_DESC.get(s.get('reply_length'), REPLY_LENGTH_DESC['medium'])}",
    ]
    parts.append(f"主动性：{PROACTIVE_DESC.get(s.get('proactive'), PROACTIVE_DESC['medium'])}")
    if s.get("extra"):
        parts.append(f"附加要求：{s['extra']}")
    return _join(parts)


def render_immersive_settings(s: dict) -> str:
    parts = [
        f"情境篇幅：{SCENARIO_LENGTH_DESC.get(s.get('scenario_length'), SCENARIO_LENGTH_DESC['medium'])}"
    ]
    parts.append(f"剧情推进：{PACE_DESC.get(s.get('pace'), PACE_DESC['medium'])}")
    if s.get("extra"):
        parts.append(f"附加要求：{s['extra']}")
    return _join(parts)


def render_director_settings(s: dict) -> str:
    parts = []
    if s.get("genre"):
        parts.append(f"题材：{s['genre']}")
    if s.get("style"):
        parts.append(f"文风：{s['style']}")
    parts.append(f"篇幅：{FREE_LENGTH_DESC.get(s.get('length'), FREE_LENGTH_DESC['medium'])}")
    parts.append(
        "情境与台词的配比："
        f"{COMPOSITION_DESC.get(s.get('composition'), COMPOSITION_DESC['balanced'])}"
    )
    if s.get("extra"):
        parts.append(f"附加要求：{s['extra']}")
    return _join(parts)


RENDERERS = {
    "chat": render_chat_settings,
    "immersive": render_immersive_settings,
    "director": render_director_settings,
}


def _field(value: str) -> str:
    return (value or "").strip() or "（未设定）"


def _character_block(character) -> str:
    return (
        "# 角色设定\n"
        f"姓名：{character['name']}\n"
        f"外观：{_field(character['appearance'])}\n"
        f"性格：{_field(character['personality'])}\n"
        f"语言风格：{_field(character['speech_style'])}\n"
        f"背景：{_field(character['backstory'])}\n\n"
    )


def _memory_block(memory_content: str) -> str:
    return (
        "# 你对这个用户的记忆\n"
        f"{memory_content.strip() or '（暂无，这是你们的初次交流）'}\n\n"
    )


def _world_block(world) -> str:
    """世界设定。**名称不进来**（用户要求：只给自己辨认）；其余三项都空就整块不出现。

    三种模式都注入，位置在角色设定之前——世界是最外层的框架，"你身处这个世界、并且扮演
    这个角色"比反过来自然。
    """
    w = world or {}
    description = (w.get("description") or "").strip()
    rules = (w.get("rules") or "").strip()
    terms = []
    for t in w.get("terms") or []:
        term = (t.get("term") or "").strip()
        if not term:
            continue
        meaning = (t.get("meaning") or "").strip()
        terms.append(f"- {term}：{meaning}" if meaning else f"- {term}")
    if not (description or rules or terms):
        return ""
    parts = ["# 世界设定"]
    if description:
        parts.append(f"描述：{description}")
    if rules:
        parts.append(f"规则：{rules}")
    if terms:
        parts.append("词库：")
        parts.extend(terms)
    parts.append(
        "以上是这个世界的既定设定：描述与规则必须遵守，词库里的专有名词按给定含义使用，"
        "不要改写这些设定，也不要向用户复述这份设定。"
    )
    return "\n".join(parts) + "\n\n"


def _user_block(profile) -> str:
    """用户本人的设定。三项都没填就整块不出现——不要给模型一段空标签。

    只给聊天与沉浸两种模式用：导演模式是"写故事"，没有"我是谁"这回事（见 DEVELOPMENT §2.3 我的设定）。
    """
    p = profile or {}
    name = (p.get("name") or "").strip()
    identity = (p.get("identity") or "").strip()
    appearance = (p.get("appearance") or "").strip()
    if not (name or identity or appearance):
        return ""
    parts = []
    if name:
        parts.append(f"姓名：{name}")
    if identity:
        parts.append(f"身份：{identity}")
    if appearance:
        parts.append(f"外观：{appearance}")
    return (
        "# 与你对话的人\n"
        + "\n".join(parts)
        + "\n以上是用户本人的设定（不是你要扮演的角色）。据此理解对方的身份与外貌，"
        "可以直接称呼对方，但不要把这些内容念出来，也不要替对方说话。\n\n"
    )


def _attr_num(value) -> str:
    """百分比值去掉没意义的小数尾巴：42.0 → 42，42.5 → 42.5。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number == int(number) else f"{number:g}"


def _attrs_state_block(defs, values) -> str:
    """角色的当前状态（附加属性）。没有定义就整块不出现（功能没启用）。

    值取**上一条消息**带回来的那一份（见 §2.6）：这条消息之前没有带属性的消息时，
    这里逐条写"暂无记录"，让模型给出合理的初始值——而不是把整块去掉（那样它就没
    格式可循了）。放在记忆之后、回复要求之前：越靠后，模型遵循得越好。
    """
    if not defs:
        return ""
    got = {v["name"]: v for v in (values or [])}
    lines = []
    for d in defs:
        v = got.get(d["name"])
        if v is None:
            shown = "（暂无记录，请按剧情给一个合理的初始值）"
        elif d["type"] == "percent":
            shown = f"{_attr_num(v['value'])}（百分比型，0-100 的整数）"
        else:
            shown = f"{v['value']}（文字型，一句简短的话）"
        lines.append(f"{d['name']}：{shown}" + (f"（{d['hint']}）" if d["hint"] else ""))
    return (
        "# 角色的当前状态（附加属性）\n"
        "（下面这段是后台数据，不是台词，也不要用它当说话的内容）\n"
        + "\n".join(lines)
        + "\n以上是上一轮结束时角色的状态，这轮在此基础上继续；没有变化就保持原值，"
        "有变化时给出新值（百分比型可以小幅增减）。\n\n"
    )


def _attrs_rule(defs) -> str:
    """输出规则里那一段：要求模型在正文之后输出 [ATTR] 块（见 §2.6）。

    必须写明"用户看不到这个块"：聊天模式的规则是"只输出说出口的话"，不交代清楚的话，
    模型会把属性当成台词的一部分念出来。**还要把反例写出来**：实测模型会把状态块里的
    "心情：98（百分比型…）"照抄到台词结尾（"……好的呀。心情：98%"），只写"不要写进台词"
    拦不住，得点名"正文里绝对不要出现属性名或属性值，例如不要写「心情：98%」"。
    """
    if not defs:
        return ""
    return (
        "\n\n# 附加属性\n"
        f"在正文之后另起一行，用一个 [ATTR] 块给出这些属性的当前值：{'、'.join(d['name'] for d in defs)}。\n"
        "格式（[ATTR] 单独占一行，之后每行一个「属性名：值」）：\n"
        "[ATTR]\n"
        + "\n".join(f"{d['name']}：……" for d in defs)
        + "\n这个块不是对话内容，用户看不到它。"
        "**正文里绝对不要出现属性名或属性值**——例如不要在话的结尾写「心情：98%」「好感：42」，"
        "也不要在正文里解释这些属性；属性只在 [ATTR] 块里写。"
    )


def build_chat_system(
    character, memory_content: str, settings: dict, profile=None, world=None, attrs=None
) -> str:
    name = character["name"]
    defs, values = attrs or ([], [])
    return (
        "你要完全扮演下面这个角色，与用户进行对话。\n\n"
        + _world_block(world)
        + _character_block(character)
        + _user_block(profile)
        + _memory_block(memory_content)
        + _attrs_state_block(defs, values)
        + "# 回复要求\n"
        f"{render_chat_settings(settings)}\n\n"
        "# 输出规则\n"
        f"这个模式像手机发短信：每一轮只输出{name}**说出口的话**，读起来就是聊天记录本身。\n"
        "不要写动作、表情、语气提示或心理活动，也不要写旁白、场景描写与舞台说明。"
        "**尤其不要把动作放进括号里**\n"
        # 名字前缀是实测最常见的一种走偏：模型写成「苏说：今晚就……」或「苏：今晚就……」，
        # 而界面上名字已经显示在气泡上方了，多这一截就不像聊天记录（用户报过）
        f"不要在开头写「{name}：」「{name}说：」这类前缀——名字界面上已经有了，正文只写话本身。\n"
        "不要在正文里用括号、星号、markdown 标记，也不要用引号把整段话包起来。"
        + _attrs_rule(defs)
    )


def build_immersive_system(
    character, memory_content: str, settings: dict, profile=None, world=None, attrs=None
) -> str:
    defs, values = attrs or ([], [])
    return (
        "你要扮演下面这个角色，与用户在同一个故事情境中互动。\n\n"
        + _world_block(world)
        + _character_block(character)
        + _user_block(profile)
        + _memory_block(memory_content)
        + _attrs_state_block(defs, values)
        + "# 生成要求\n"
        f"{render_immersive_settings(settings)}\n\n"
        "# 导演指令\n"
        f"{settings.get('director_notes') or '（无）'}\n"
        "导演指令只决定情境与剧情的走向，不属于对话内容，角色不得提及或回应“收到指令”。\n\n"
        "# 输出规则\n"
        "严格按下面两段的顺序输出，段首必须原样使用这两个英文标记：\n"
        "[SCENARIO]场景、动作、氛围等情境说明\n"
        "[DIALOG]你扮演的角色说出的话\n"
        "标记只能用 [SCENARIO] 与 [DIALOG] 这两个词，不要写成 [SCENERY]、[SCENE] 或中文标记。\n"
        "[DIALOG] 里只写角色说出的话本身，不要写「角色名：」这类前缀（名字界面上已经有了）。\n"
        "两段都必须有内容：不要输出空标记，也不要在标记之外写任何文字。"
        + _attrs_rule(defs)
    )


def build_director_system(memory_content: str, settings: dict, world=None) -> str:
    # 这个模式没有独立的"导演指令"字段：用户在对话里发的内容本身就是对下一步的指令，
    # 再单设一个字段属于重复，且会让"当前指令"分散在两处。
    return (
        "你是创意写作引擎，根据用户的引导生成故事情境与角色对话。\n\n"
        + _world_block(world)
        + "# 本会话此前的剧情\n"
        f"{memory_content.strip() or '（暂无，这是新的故事）'}\n\n"
        "# 生成要求\n"
        f"{render_director_settings(settings)}\n\n"
        "# 输出规则\n"
        "每次生成都用下面的标记分段输出，每个段落以标记开头，段落数量与先后顺序不限：\n"
        "[SCENARIO]场景、氛围、事件等情境说明\n"
        "[DIALOG]角色名：该角色说出的话\n"
        "[SCENARIO] 与 [DIALOG] 都可以只出现其中一种，也可以各自出现多次。\n"
        "[DIALOG] 是可选的：只写情境时就不要输出任何 [DIALOG]。\n"
        "情境与台词的比例由「情境与台词的配比」要求决定。"
    )


def build_system_prompt(
    session, character, memory_content: str, profile=None, world=None, attrs=None
) -> str:
    mode = session["mode"]
    settings = get_gen_settings(session)
    if mode == "chat" and character is not None:
        return build_chat_system(
            character, memory_content, settings, profile, world, attrs
        )
    if mode == "immersive" and character is not None:
        return build_immersive_system(
            character, memory_content, settings, profile, world, attrs
        )
    if mode == "director":
        # 导演模式不注入"我的设定"：那里没有"我是谁"，写故事的人不是故事里的角色。
        # 但世界设定要注入：故事就发生在那个世界里。
        # 附加属性也不注入：那是"某个角色的状态"，导演模式里没有固定的角色
        return build_director_system(memory_content, settings, world)
    return "你是一个友好的中文对话助手，回答简洁自然。"


def _restore_history(mode: str, row) -> str:
    """历史消息按原始标记格式回填，提升格式遵循率。

    沉浸模式下两个方向都要：助手消息的情境是它写的场景，用户消息的情境是用户给的场景，
    两侧都按 [SCENARIO]/[DIALOG] 回填——模型看到的就是一份完整、同格式的对话记录。
    """
    content = row["content"]
    if mode == "immersive":
        scenario = row["scenario"] if "scenario" in row.keys() else None
        if scenario:
            # 只有情境、没有台词时不要再补一个空的 [DIALOG]，那会教模型输出空标记
            if content.strip():
                return f"[SCENARIO]{scenario}\n[DIALOG]{content}"
            return f"[SCENARIO]{scenario}"
    return content


def build_messages(
    session, character, memory_content: str, history_rows, profile=None, world=None, attrs=None
) -> list[dict]:
    mode = session["mode"]
    system = build_system_prompt(
        session, character, memory_content, profile, world, attrs
    )
    limit = get_config()["chat"]["history_max_messages"]
    msgs = [{"role": "system", "content": system}]
    for r in history_rows[-limit:]:
        # 助手消息：沉浸与导演模式都按标记回填（聊天模式没有情境块）
        if r["role"] == "assistant" and mode != "chat":
            msgs.append({"role": "assistant", "content": _restore_history(mode, r)})
        # 用户消息：只有沉浸模式带了用户写的情境，同样回填
        elif r["role"] == "user" and mode == "immersive":
            msgs.append({"role": "user", "content": _restore_history(mode, r)})
        else:
            msgs.append({"role": r["role"], "content": r["content"]})
    return msgs
