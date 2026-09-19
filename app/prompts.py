import json

from .config import get_config

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

DEFAULT_SETTINGS = {
    "character_chat": {
        "reply_length": "medium",
        "proactive": "medium",
        "extra": "",
    },
    "character_scenario": {
        "scenario_length": "medium",
        "pace": "medium",
        "director_notes": "",
        "extra": "",
    },
    "free_scenario": {
        "genre": "",
        "style": "",
        "length": "medium",
        "composition": "balanced",
        "extra": "",
    },
}

# 生成要求表单字段定义，供前端渲染（GET /api/gen-settings/{mode} 或随会话返回）
FIELDS = {
    "character_chat": [
        {"key": "reply_length", "label": "回复长度", "type": "radio",
         "options": [("short", "简短"), ("medium", "适中"), ("long", "详细")]},
        {"key": "proactive", "label": "主动性", "type": "radio",
         "options": [("low", "低"), ("medium", "中"), ("high", "高")]},
        {"key": "extra", "label": "附加要求", "type": "textarea",
         "placeholder": "任意补充要求，原样注入提示词"},
    ],
    "character_scenario": [
        {"key": "scenario_length", "label": "情境篇幅", "type": "radio",
         "options": [("short", "简短"), ("medium", "适中"), ("long", "详细")]},
        {"key": "pace", "label": "推进速度", "type": "radio",
         "options": [("slow", "平缓"), ("medium", "适中"), ("fast", "快速")]},
        {"key": "director_notes", "label": "导演指令", "type": "textarea",
         "hint": "只影响情境走向，不进入对话", "placeholder": "如：让两人的关系逐渐缓和"},
        {"key": "extra", "label": "附加要求", "type": "textarea"},
    ],
    "free_scenario": [
        {"key": "genre", "label": "题材", "type": "text", "placeholder": "如：都市奇幻、武侠"},
        {"key": "style", "label": "文风", "type": "text", "placeholder": "如：细腻文学风、轻喜剧"},
        {"key": "length", "label": "单次篇幅", "type": "radio",
         "options": [("short", "短"), ("medium", "中"), ("long", "长")]},
        {"key": "composition", "label": "情境/台词配比", "type": "radio",
         "hint": "决定情境与台词各占多少，可只写情境",
         "options": [("scenario_only", "只有情境"), ("scenario_heavy", "情境为主"),
                     ("balanced", "均衡"), ("dialog_heavy", "台词为主")]},
        {"key": "extra", "label": "附加要求", "type": "textarea"},
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


def render_character_chat_settings(s: dict) -> str:
    parts = [
        f"回复长度：{REPLY_LENGTH_DESC.get(s.get('reply_length'), REPLY_LENGTH_DESC['medium'])}",
    ]
    parts.append(f"主动性：{PROACTIVE_DESC.get(s.get('proactive'), PROACTIVE_DESC['medium'])}")
    if s.get("extra"):
        parts.append(f"附加要求：{s['extra']}")
    return _join(parts)


def render_character_scenario_settings(s: dict) -> str:
    parts = [
        f"情境篇幅：{SCENARIO_LENGTH_DESC.get(s.get('scenario_length'), SCENARIO_LENGTH_DESC['medium'])}"
    ]
    parts.append(f"剧情推进：{PACE_DESC.get(s.get('pace'), PACE_DESC['medium'])}")
    if s.get("extra"):
        parts.append(f"附加要求：{s['extra']}")
    return _join(parts)


def render_free_scenario_settings(s: dict) -> str:
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
    "character_chat": render_character_chat_settings,
    "character_scenario": render_character_scenario_settings,
    "free_scenario": render_free_scenario_settings,
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


def build_character_chat_system(character, memory_content: str, settings: dict) -> str:
    name = character["name"]
    return (
        "你要完全扮演下面这个角色，与用户进行对话。\n\n"
        + _character_block(character)
        + _memory_block(memory_content)
        + "# 回复要求\n"
        f"{render_character_chat_settings(settings)}\n\n"
        "# 输出规则\n"
        f"只输出{name}说出的话。不要输出旁白、动作描写、心理描写、括号注释或舞台说明。\n"
        "不要在开头重复角色名。"
    )


def build_character_scenario_system(character, memory_content: str, settings: dict) -> str:
    return (
        "你要扮演下面这个角色，与用户在同一个故事情境中互动。\n\n"
        + _character_block(character)
        + _memory_block(memory_content)
        + "# 生成要求\n"
        f"{render_character_scenario_settings(settings)}\n\n"
        "# 导演指令\n"
        f"{settings.get('director_notes') or '（无）'}\n"
        "导演指令只决定情境与剧情的走向，不属于对话内容，角色不得提及或回应“收到指令”。\n\n"
        "# 输出规则\n"
        "严格按下面两段的顺序输出，段首必须原样使用这两个英文标记：\n"
        "[SCENARIO]场景、动作、氛围等情境说明\n"
        "[DIALOG]你扮演的角色说出的话\n"
        "标记只能用 [SCENARIO] 与 [DIALOG] 这两个词，不要写成 [SCENERY]、[SCENE] 或中文标记。\n"
        "两段都必须有内容：不要输出空标记，也不要在标记之外写任何文字。"
    )


def build_free_scenario_system(memory_content: str, settings: dict) -> str:
    # 这个模式没有独立的"导演指令"字段：用户在对话里发的内容本身就是对下一步的指令，
    # 再单设一个字段属于重复，且会让"当前指令"分散在两处。
    return (
        "你是创意写作引擎，根据用户的引导生成故事情境与角色对话。\n\n"
        "# 本会话此前的剧情\n"
        f"{memory_content.strip() or '（暂无，这是新的故事）'}\n\n"
        "# 生成要求\n"
        f"{render_free_scenario_settings(settings)}\n\n"
        "# 输出规则\n"
        "每次生成都用下面的标记分段输出，每个段落以标记开头，段落数量与先后顺序不限：\n"
        "[SCENARIO]场景、氛围、事件等情境说明\n"
        "[DIALOG]角色名：该角色说出的话\n"
        "[SCENARIO] 与 [DIALOG] 都可以只出现其中一种，也可以各自出现多次。\n"
        "[DIALOG] 是可选的：只写情境时就不要输出任何 [DIALOG]。\n"
        "情境与台词的比例由「情境与台词的配比」要求决定。"
    )


def build_system_prompt(session, character, memory_content: str) -> str:
    mode = session["mode"]
    settings = get_gen_settings(session)
    if mode == "character_chat" and character is not None:
        return build_character_chat_system(character, memory_content, settings)
    if mode == "character_scenario" and character is not None:
        return build_character_scenario_system(character, memory_content, settings)
    if mode == "free_scenario":
        return build_free_scenario_system(memory_content, settings)
    return "你是一个友好的中文对话助手，回答简洁自然。"


def _restore_history(mode: str, row) -> str:
    """情境模式的历史 assistant 消息按原始标记格式回填，提升格式遵循率。"""
    content = row["content"]
    if mode == "character_scenario":
        scenario = row["scenario"] if "scenario" in row.keys() else None
        if scenario:
            # 只有情境、没有台词时不要再补一个空的 [DIALOG]，那会教模型输出空标记
            if content.strip():
                return f"[SCENARIO]{scenario}\n[DIALOG]{content}"
            return f"[SCENARIO]{scenario}"
    return content


def build_messages(session, character, memory_content: str, history_rows) -> list[dict]:
    mode = session["mode"]
    system = build_system_prompt(session, character, memory_content)
    limit = get_config()["chat"]["history_max_messages"]
    msgs = [{"role": "system", "content": system}]
    for r in history_rows[-limit:]:
        if r["role"] == "assistant" and mode != "character_chat":
            msgs.append({"role": "assistant", "content": _restore_history(mode, r)})
        else:
            msgs.append({"role": r["role"], "content": r["content"]})
    return msgs
