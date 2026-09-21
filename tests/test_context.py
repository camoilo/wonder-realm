"""上下文预算：记忆阈值必须留在 `num_ctx` 窗口之内（见 DEVELOPMENT 10.42）。

两个数字分处 `config.yaml` 的 `memory` 与 `ollama.options`，改一个忘一个**不会报错**——
只会让 Ollama 超窗后从最前面静默截断，而系统提示词（角色设定 + 记忆 + "我的设定"）正好
排在最前面，表现成"角色忽然失忆/串味"，事后很难查。所以这里把它们绑在一条断言上。

换算比例用实测值（qwen3.5:4b，见 10.42）：短样本 1.33 字/token、6800 字长文 1.54 字/token；
这里取 **1.2 字/token** 当保守值（标点、英文片段更费 token），并额外要求留出 10% 余量
给模型自己写。

残留风险（不在此断言、只在文档里写明）：单条消息上限 2000 字，若连续多条满上限长消息
堆在一起，未归档量会短暂冲高，而每轮压缩只归档 20 条——极端情况下仍可能溢出窗口。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.config import CONFIG_PATH, DEFAULTS, get_config  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


cfg = get_config()
yaml_cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

num_ctx = cfg["ollama"]["options"]["num_ctx"]
threshold = cfg["memory"]["compress_threshold_chars"]

# 1. 生效值 = 用户选定值（10.42：窗口 32768、阈值 20000）
check("上下文窗口是 32768", num_ctx, 32768)
check("记忆阈值是 20000 字符", threshold, 20000)
check("注入历史条数仍是 60", cfg["chat"]["history_max_messages"], 60)

# 2. config.yaml 与 DEFAULTS 不能各写一套（缺键时用 DEFAULTS，两处不一致会出现
#    "改了配置没用"或"删了配置反而变了"的怪事）
check("num_ctx 两处一致",
      yaml_cfg["ollama"]["options"]["num_ctx"], DEFAULTS["ollama"]["options"]["num_ctx"])
check("记忆阈值两处一致",
      yaml_cfg["memory"]["compress_threshold_chars"],
      DEFAULTS["memory"]["compress_threshold_chars"])

# 3. 阈值 + 系统提示词换算成 token 后仍在窗口内，且留有余量
SYSTEM_CHARS = 4000  # 角色各项上限合计 + 记忆 600 + 我的设定，按上限粗估
CONSERVATIVE = 1.2   # 字/token，实测 1.33~1.5，取更费 token 的值当保守估计
estimated = (threshold + SYSTEM_CHARS) / CONSERVATIVE
check(f"阈值 {threshold} 字加系统提示词换算后仍在窗口内（估 {estimated:.0f} token）",
      estimated < num_ctx * 0.9, True)
check("压缩产出的摘要上限没变", cfg["memory"]["max_memory_chars"], 600)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("上下文预算用例全部通过")
