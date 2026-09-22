import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser import parse_output, split_segments


def run_case(name, got, expected):
    assert got == expected, f"{name}: got {got!r}, want {expected!r}"


# 聊天模式：原样返回
run_case(
    "chat-passthrough",
    parse_output("chat", " 你好呀 "),
    (None, "你好呀"),
)

# 沉浸模式：一段情境 + 一段话语
run_case(
    "scenario-basic",
    parse_output("immersive", "[SCENARIO]雨夜的书店\n[DIALOG]你来了。"),
    ("雨夜的书店", "你来了。"),
)

# 沉浸模式：多段 DIALOG 合并
run_case(
    "scenario-multi-dialog",
    parse_output("immersive", "[SCENARIO]公园\n[DIALOG]早\n[DIALOG]早啊"),
    ("公园", "早\n早啊"),
)

# 沉浸模式：只有 DIALOG，无情境
run_case(
    "scenario-no-scenario",
    parse_output("immersive", "[DIALOG]只有台词"),
    (None, "只有台词"),
)

# 容错：无标记时整体降级为话语，不丢内容
run_case(
    "fallback-no-marker",
    parse_output("immersive", "模型忘了格式直接说话"),
    (None, "模型忘了格式直接说话"),
)

# ---- 以下用例来自实际遇到的输出 ----
# 模型把标记写成 [SCENERY]、台词写在标记之前、末尾还多了个空的 [DIALOG]
# （只认标准标记的话会只匹配到那个空 [DIALOG]，于是情境为空、整段被打成纯文本）
run_case(
    "tolerant-scenery-tag",
    parse_output(
        "immersive",
        "你好啊，最近过得怎么样？[SCENERY]庆明坐在教室的最后一排，窗外阳光透过树叶洒下斑驳的光影。[DIALOG]",
    ),
    ("庆明坐在教室的最后一排，窗外阳光透过树叶洒下斑驳的光影。", "你好啊，最近过得怎么样？"),
)

# 小写标记
run_case(
    "tolerant-lowercase",
    parse_output("immersive", "[scenario]雨天\n[dialog]带伞了吗"),
    ("雨天", "带伞了吗"),
)

# 全角括号
run_case(
    "tolerant-fullwidth",
    parse_output("immersive", "【SCENARIO】黄昏\n【DIALOG】回来了"),
    ("黄昏", "回来了"),
)

# 情境被拆成多段：合并保留，不能只取第一段
run_case(
    "tolerant-multi-scenario",
    parse_output("immersive", "[SCENARIO]前半\n[SCENARIO]后半\n[DIALOG]嗯"),
    ("前半\n后半", "嗯"),
)

# 只有情境、没有台词：正文为空串，情境保留（由 persist_message 决定是否落库）
run_case(
    "scenario-only",
    parse_output("immersive", "[SCENARIO]只有场景"),
    ("只有场景", ""),
)

# 只有空标记：没有可显示的内容，不能把裸标记当正文
run_case("only-empty-tags", parse_output("immersive", "[DIALOG]"), (None, ""))
run_case("only-empty-scenario", parse_output("immersive", "[SCENARIO]  "), (None, ""))

# 导演模式：content 保留带标记全文，scenario 置 MULTI
raw = "[SCENARIO]便利店\n[DIALOG]女孩：你好\n[DIALOG]店员：欢迎光临"
run_case("free-multi", parse_output("director", raw), ("MULTI", raw))

# 导演模式无标记：同样降级
run_case(
    "free-fallback",
    parse_output("director", "随便写点什么"),
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

# 分段渲染同样要容错：裸文本按话语算，空标记不产生空段落
run_case(
    "split-tolerant",
    split_segments("你好[SCENERY]下雨了[DIALOG]"),
    [
        {"type": "dialog", "text": "你好"},
        {"type": "scenario", "text": "下雨了"},
    ],
)
run_case("split-only-empty-tag", split_segments("[DIALOG]"), [])

print("Parser 全部用例通过")
