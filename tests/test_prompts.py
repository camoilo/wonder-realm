"""提示词内容检查：三种模式的输出规则与段落拼装。

重点盯聊天模式——它是"像发消息"的对话，模型却习惯把动作塞进括号（「（轻轻笑了一下）」），
所以提示词必须把这件事明确禁止，并且给出反例。这条规则是纯文本，改坏了不会有任何报错，
只能靠断言看着。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import prompts  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


CHARACTER = {
    "name": "阿岚",
    "appearance": "",
    "personality": "",
    "speech_style": "",
    "backstory": "",
}
WORLD = {"name": "不算数的名字", "description": "一座海边小城", "rules": "", "terms": []}
PROFILE = {"name": "小李", "identity": "", "appearance": ""}


def chat(**kw):
    return prompts.build_chat_system(CHARACTER, kw.get("memory", ""), {}, kw.get("profile"), kw.get("world"))


# ---- 聊天模式：只写说出口的话 ----
s = chat()
check("写明像发消息", "像手机发消息" in s, True)
check("写明只输出说出口的话", "说出口的话" in s, True)
check("明确禁止括号里的动作", "尤其不要把动作放进括号里" in s, True)
check("给了括号动作的反例", "（轻轻笑了一下）" in s, True)
check("禁止旁白与场景描写", "旁白" in s and "场景描写" in s, True)
check("禁止星号包裹动作", "*笑*" in s, True)
check("禁止输出标记", "[SCENARIO]" in s and "[DIALOG]" in s, True)
check("说明多句要换行分段", "换行分段" in s, True)
check("不要在开头重复角色名", "不要在正文开头重复角色名" in s, True)
check("角色名出现在规则里", "阿岚" in s, True)
# 这条是聊天模式与沉浸模式的分界：聊天模式不该要求输出情境
check("聊天模式不提情境块", "情境说明" in s, False)

# ---- 沉浸模式仍然要情境（别把聊天模式的规则串过去） ----
immersive = prompts.build_immersive_system(CHARACTER, "", {}, None, None)
check("沉浸模式保留情境要求", "[SCENARIO]" in immersive, True)
check("沉浸模式要求两段标记", "[DIALOG]" in immersive, True)
check("沉浸模式禁止空标记与标记外文字",
      "不要输出空标记" in immersive and "不要在标记之外写任何文字" in immersive, True)
check("沉浸模式不会说“像发消息”", "像手机发消息" in immersive, False)

# ---- 导演模式仍然按配比写情境与台词 ----
director = prompts.build_director_system("", {}, None)
check("导演模式保留标记说明", "[SCENARIO]" in director and "[DIALOG]" in director, True)

# ---- 段落拼装：空块整块不出现；顺序固定 ----
full = chat(profile=PROFILE, world=WORLD, memory="他昨天提过怕黑")
check("世界设定在角色设定之前",
      0 < full.index("# 世界设定") < full.index("# 角色设定"), True)
check("我的设定在角色设定之后",
      full.index("# 角色设定") < full.index("# 与你对话的人"), True)
check("记忆在回复要求之前",
      full.index("# 你对这个用户的记忆") < full.index("# 回复要求"), True)
check("输出规则在最后", full.rindex("# 输出规则") > full.index("# 回复要求"), True)
check("世界名称不发给模型", WORLD["name"] in full, False)
check("世界描述发给了模型", "一座海边小城" in full, True)
empty = chat()
check("没有世界设定时整块不出现", "# 世界设定" in empty, False)
check("没有我的设定时整块不出现", "# 与你对话的人" in empty, False)
check("没有记忆时给出初次交流的说明", "初次交流" in empty, True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("提示词用例全部通过")
