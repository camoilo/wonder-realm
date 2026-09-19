"""让模型生成角色设定，以及"探索模式"的锁定规则。

锁定只针对用户可见性：锁定的三个字段照样注入 system prompt（角色必须有性格，
否则就没有扮演可言），只是不下发给前端、也不允许通过接口改写。
"""
import json
import logging
import re
import uuid

from . import ollama_client
from .config import get_config
from .database import connect
from .prompts import TEMPERATURE_LEVELS

log = logging.getLogger("ollama_agent")

# 探索模式下对用户隐藏的三个字段
HIDDEN_FIELDS = ("personality", "speech_style", "backstory")
VISIBLE_FIELDS = ("name", "appearance")
FIELDS = VISIBLE_FIELDS + HIDDEN_FIELDS

MAX_FIELD_CHARS = 600
MAX_HINT_CHARS = 200

GEN_PROMPT = """请设计一个适合长期一对一对话的角色。

{requirement}只输出一个 JSON 对象，不要任何解释文字，不要 Markdown 代码块。字段如下：
{{
  "name": "姓名，2 到 4 个汉字，不要用「无名」「待定」这类占位名",
  "appearance": "外观：年龄、身形、衣着、标志性特征，1 到 2 句",
  "personality": "性格：好恶、待人方式、做事的倾向，1 到 3 句",
  "speech_style": "语言风格：口癖、语气、用词习惯，1 到 2 句",
  "backstory": "背景故事与当前处境，2 到 4 句"
}}
全部用中文。四个非姓名字段都要写具体的内容，不要留空、不要写"未设定"。"""

NO_REQUIREMENT = "角色可以完全自由发挥，但要有辨识度、便于展开对话。\n\n"
REQUIREMENT = "用户希望的设定（请尽量贴合）：{hint}\n\n"

# 生成中的草稿只放在内存里：它是"还没决定要不要的角色"，不值得进数据库。
# 键是草稿 id，值是 {"mode": "open"/"explore", 五个字段...}
_DRAFTS: dict[str, dict] = {}
MAX_DRAFTS = 30


def public_character(row) -> dict:
    """按锁定状态裁剪角色，供所有下发角色的接口共用。

    集中在一处是必须的：角色既出现在角色列表/单查里，也内嵌在会话详情里，
    漏掉任何一个入口，"上锁"都等于没做。
    """
    out = dict(row)
    locked = bool(out.get("locked"))
    out["locked"] = locked
    if locked:
        for key in HIDDEN_FIELDS:
            out.pop(key, None)
    return out


def _clean_json(raw: str) -> dict:
    """从模型输出里挖出 JSON 对象。容忍代码块、前后解释文字与思考残留。"""
    text = (raw or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    if "<think>" in text:
        text = text.split("<think>")[0]
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    # 退化：截第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    # 再退化：按 "键：值" 逐行取（个别模型会输出列表式的文本，或在 JSON 模式之外说话）。
    # 中文标签要映射回英文字段名，否则取出来的键对不上，等于没兜底
    labels = {
        "name": ("name", "姓名", "名字", "角色名"),
        "appearance": ("appearance", "外观", "外貌", "外表"),
        "personality": ("personality", "性格", "个性"),
        "speech_style": ("speech_style", "language", "语言风格", "说话风格", "语气", "语言"),
        "backstory": ("backstory", "背景", "背景故事", "经历"),
    }
    by_label = {lab.lower(): key for key, labs in labels.items() for lab in labs}
    out = {}
    for line in text.splitlines():
        m = re.match(r'\s*"?([^"：:]{1,12})"?\s*[:：]\s*"?(.*?)"?\s*,?\s*$', line)
        if not m:
            continue
        key = by_label.get(m.group(1).strip().lower())
        if key and m.group(2).strip() and key not in out:
            out[key] = m.group(2).strip()
    return out


def _norm(data: dict) -> dict:
    """取出五个字段并做长度与空值兜底；姓名为空视为失败。"""
    out = {}
    for key in FIELDS:
        value = data.get(key)
        if isinstance(value, (list, tuple)):
            value = "；".join(str(v).strip() for v in value if str(v).strip())
        out[key] = str(value or "").strip()[:MAX_FIELD_CHARS]
    if not out["name"]:
        raise ValueError("模型没有给出姓名")
    return out


async def generate_character(hint: str = "") -> dict:
    """让当前对话模型生成一份角色设定。只生成文字，不管头像与背景。"""
    cfg = get_config()
    con = connect()
    try:
        row = con.execute("SELECT model FROM app_settings WHERE id=1").fetchone()
    finally:
        con.close()
    model = (row["model"] if row else "") or cfg["ollama"]["model"]
    if not model:
        raise ValueError("还没有选择模型，无法生成角色")

    hint = (hint or "").strip()[:MAX_HINT_CHARS]
    prompt = GEN_PROMPT.format(
        requirement=REQUIREMENT.format(hint=hint) if hint else NO_REQUIREMENT
    )
    opts = dict(cfg["ollama"]["options"])
    opts["temperature"] = TEMPERATURE_LEVELS["standard"]
    # format="json" 让 Ollama 约束成合法 JSON，比在提示词里"求"它可靠得多；
    # 解析仍然容错，因为不是所有模型都严格遵守（见 _clean_json）。
    # 模型与思考开关都走同一条 chat_once → _payload：用的是当前选中的模型，
    # 用户关掉思考模式时会带 think=False（见 10.30）
    raw = await ollama_client.chat_once(
        [{"role": "user", "content": prompt}], model, opts, fmt="json",
        timeout=cfg.get("character_gen", {}).get("timeout", 600),
    )
    fields = _norm(_clean_json(raw))
    log.info("生成角色「%s」（提示词 %d 字）", fields["name"], len(hint))
    return fields


def new_draft(fields: dict, mode: str) -> str:
    """存一份草稿，返回它的 id。超过上限就丢掉最早的。"""
    if len(_DRAFTS) >= MAX_DRAFTS:
        for key in list(_DRAFTS)[: len(_DRAFTS) - MAX_DRAFTS + 1]:
            _DRAFTS.pop(key, None)
    draft_id = uuid.uuid4().hex
    _DRAFTS[draft_id] = {"mode": mode, **fields}
    return draft_id


def take_draft(draft_id: str) -> dict | None:
    """取草稿但**不删除**：用户可能反复保存失败后重试。

    刷新页面会让内存里的草稿消失——草稿本来就只是"还没决定的角色"，
    重新生成一次即可；这样也不用为它建表。
    """
    return _DRAFTS.get(draft_id)
