import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser import parse_output, split_segments


def run_case(name, got, expected):
    assert got == expected, f"{name}: got {got!r}, want {expected!r}"


# 角色对话模式：原样返回
run_case(
    "chat-passthrough",
    parse_output("character_chat", " 你好呀 "),
    (None, "你好呀"),
)

# 角色情境：一段情境 + 一段话语
run_case(
    "scenario-basic",
    parse_output("character_scenario", "[SCENARIO]雨夜的书店\n[DIALOG]你来了。"),
    ("雨夜的书店", "你来了。"),
)

# 角色情境：多段 DIALOG 合并
run_case(
    "scenario-multi-dialog",
    parse_output("character_scenario", "[SCENARIO]公园\n[DIALOG]早\n[DIALOG]早啊"),
    ("公园", "早\n早啊"),
)

# 角色情境：只有 DIALOG，无情境
run_case(
    "scenario-no-scenario",
    parse_output("character_scenario", "[DIALOG]只有台词"),
    (None, "只有台词"),
)

# 容错：无标记时整体降级为话语，不丢内容
run_case(
    "fallback-no-marker",
    parse_output("character_scenario", "模型忘了格式直接说话"),
    (None, "模型忘了格式直接说话"),
)

# 自由情境：content 保留带标记全文，scenario 置 MULTI
raw = "[SCENARIO]便利店\n[DIALOG]女孩：你好\n[DIALOG]店员：欢迎光临"
run_case("free-multi", parse_output("free_scenario", raw), ("MULTI", raw))

# 自由情境无标记：同样降级
run_case(
    "free-fallback",
    parse_output("free_scenario", "随便写点什么"),
    (None, "随便写点什么"),
)

# 分段渲染
run_case(
    "split-segments",
    split_segments(raw),
    [
        {"type": "scenario", "text": "便利店"},
        {"type": "dialog", "text": "女孩：你好"},
        {"type": "dialog", "text": "店员：欢迎光临"},
    ],
)
run_case(
    "split-no-marker",
    split_segments("纯文本"),
    [{"type": "dialog", "text": "纯文本"}],
)

print("Parser 全部用例通过")
