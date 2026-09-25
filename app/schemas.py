from pydantic import BaseModel, Field, field_validator

from .limits import LIMITS

# 头像以 data URL 存进数据库（跟着库走，备份才完整）。前端已把图片缩到最长边 256px，
# 这里的上限只是兜底：超限多半说明前端压缩没生效，或有人在直接调接口。
AVATAR_MAX_CHARS = 256 * 1024
AVATAR_PREFIXES = (
    "data:image/jpeg;base64,",
    "data:image/png;base64,",
    "data:image/webp;base64,",
)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=LIMITS["message"])
    # 沉浸模式下用户自己写的情境（场景、动作、心理），可选：只有话语也是合法消息
    scenario: str | None = Field(default=None, max_length=LIMITS["scenario"])


def _check_avatar(v: str) -> str:
    """空串合法（回落到姓名首字占位）；非空必须是白名单内的图片 data URL。

    只放行这几种位图，刻意不含 svg——svg 可以带脚本，而它会被直接放进 <img src>。
    角色头像与"我的设定"头像共用这一份校验。
    """
    v = (v or "").strip()
    if not v:
        return ""
    if len(v) > AVATAR_MAX_CHARS:
        raise ValueError(f"头像数据过大（上限 {AVATAR_MAX_CHARS // 1024}KB）")
    if not v.startswith(AVATAR_PREFIXES):
        raise ValueError("头像必须是 jpeg/png/webp 的 data URL")
    return v


class AttrDef(BaseModel):
    """附加属性的一条**定义**（挂在角色上，见 DEVELOPMENT §2.6）。

    名称必填、类型必须二选一（`text` 文字型 / `percent` 百分比型）；解释可选，只进提示词，
    用来告诉模型这个属性是什么意思、该怎么取值。
    """

    name: str = Field(default="", max_length=LIMITS["attr_name"])
    type: str = "text"
    hint: str = Field(default="", max_length=LIMITS["attr_hint"])

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("text", "percent"):
            raise ValueError("属性类型只能是 text 或 percent")
        return v


class AttrValue(BaseModel):
    """一条**属性值**（挂在消息上）。名字与类型跟着值一起存，历史消息因此自解释。"""

    name: str = Field(default="", max_length=LIMITS["attr_name"])
    type: str = "text"
    value: str | float | int | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("text", "percent"):
            raise ValueError("属性类型只能是 text 或 percent")
        return v


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=LIMITS["name"])
    appearance: str = Field(default="", max_length=LIMITS["appearance"])
    personality: str = Field(default="", max_length=LIMITS["personality"])
    speech_style: str = Field(default="", max_length=LIMITS["speech_style"])
    backstory: str = Field(default="", max_length=LIMITS["backstory"])
    avatar: str = ""
    # 这个角色用哪份「我的设定」预设（user_profiles.id）。None = 不绑定。
    # 取值必须靠 model_fields_set 区分"没带这一项"和"显式传 null"：右侧面板保存角色设定时
    # 提交的是面板表单（不含这一项），若把"没带"当成解绑，一保存角色就把绑定清掉了
    # （见 routes/characters.py 与 DEVELOPMENT §2.3 我的设定）
    profile_id: int | None = None
    # 同理：这个角色用哪份**世界**预设（worlds.id）。None = 不绑定（见 §2.4 世界设定）
    world_id: int | None = None
    # 附加属性定义（见 §2.6）。同样靠 model_fields_set 区分"没带 = 不改"：
    # 编辑角色弹窗里不带它（那份表单没有这个编辑器），不能被当成"清空所有属性"
    attr_defs: list[AttrDef] | None = Field(default=None, max_length=LIMITS["attr_max"])

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, v: str) -> str:
        return _check_avatar(v)


class ProfileIn(BaseModel):
    """用户本人的设定（"我的设定"）。全部可选：什么都不填也能保存。

    `name` 是只给自己看的名字（**不进提示词**），`call_name` 才是模型对你的称呼（进提示词）。
    """

    name: str = Field(default="", max_length=LIMITS["user_name"])
    call_name: str = Field(default="", max_length=LIMITS["user_call_name"])
    identity: str = Field(default="", max_length=LIMITS["identity"])
    appearance: str = Field(default="", max_length=LIMITS["user_appearance"])
    avatar: str = ""

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, v: str) -> str:
        return _check_avatar(v)


class WorldTerm(BaseModel):
    """词库的一条：专有名词 + 它的解释。两项都能留空——空行在保存时被丢弃。"""

    term: str = Field(default="", max_length=LIMITS["world_term"])
    meaning: str = Field(default="", max_length=LIMITS["world_term_meaning"])


class WorldIn(BaseModel):
    """世界设定（全局一份）。四项全可选，什么都不填就是"没有世界设定"。

    `name` 只给自己辨认，**不进提示词**；其余三项进提示词（见 prompts._world_block）。
    """

    name: str = Field(default="", max_length=LIMITS["world_name"])
    description: str = Field(default="", max_length=LIMITS["world_description"])
    rules: str = Field(default="", max_length=LIMITS["world_rules"])
    terms: list[WorldTerm] = Field(
        default_factory=list, max_length=LIMITS["world_terms_max"]
    )


class CharacterCreateIn(CharacterIn):
    """新建角色。带 draft_id 时说明这一份来自模型生成的草稿。

    锁不锁定由**草稿**决定，不从这里传：否则调用方可以在生成后自称"开放模式"，
    把本该隐藏的字段要回去，锁定就形同虚设。
    """

    draft_id: str | None = None


class GenerateIn(BaseModel):
    """让模型生成角色的入参。"""

    hint: str = Field(default="", max_length=LIMITS["hint"])
    mode: str = "open"  # open = 全部直接展示；explore = 只公开姓名与外观

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in ("open", "explore"):
            raise ValueError("mode 只能是 open 或 explore")
        return v


class SessionIn(BaseModel):
    mode: str = "director"
    character_id: int | None = None
    # 导演会话绑定的世界预设（worlds.id）。聊天与沉浸两种模式的世界跟着角色走，不用这一项
    world_id: int | None = None
    # 留空表示交给模型自动命名（sessions.title_auto）
    title: str = Field(default="", max_length=LIMITS["title"])
    gen_settings: dict = {}


class SessionPatch(BaseModel):
    title: str | None = Field(default=None, max_length=LIMITS["title"])
    gen_settings: dict | None = None
    # 与角色那边的 profile_id / world_id 同一套语义：**没带这一项 = 不改绑定**，
    # 显式 null = 解绑（见 DEVELOPMENT §2.4 世界设定）
    world_id: int | None = None


class MessageEdit(BaseModel):
    # 允许空正文：沉浸模式里模型可能只写了情境没写台词，那条消息的正文就是空的，
    # 用户编辑情境时不该被迫补一句台词。真正的约束在路由里（正文与情境不能同时为空）
    content: str = Field(default="", max_length=LIMITS["message"])
    scenario: str | None = Field(default=None, max_length=LIMITS["scenario"])
    # 附加属性值（编辑面板里可改，见 §2.6）。**没带这一项 = 不改**（与绑定同一套语义）：
    # 别的调用方（例如只改正文）不该顺手把属性清空
    attrs: list[AttrValue] | None = Field(default=None, max_length=LIMITS["attr_max"])


class MemoryEdit(BaseModel):
    content: str = Field(default="", max_length=LIMITS["memory"])


# 对话区背景图：每角色至多这么多张
BACKGROUND_MAX_COUNT = 10
# 单张上限。前端已把长边压到 1920、重编码为 JPEG，实际通常远小于此
BACKGROUND_MAX_CHARS = 1536 * 1024


class BackgroundsIn(BaseModel):
    images: list[str] = []

    @field_validator("images")
    @classmethod
    def _check_images(cls, v: list[str]) -> list[str]:
        """整体替换式的入参校验：张数、单张大小、以及必须是白名单内的位图 data URL。"""
        items = [(x or "").strip() for x in (v or [])]
        items = [x for x in items if x]  # 空项直接丢弃，不往库里写空串
        if len(items) > BACKGROUND_MAX_COUNT:
            raise ValueError(f"最多只能放 {BACKGROUND_MAX_COUNT} 张背景图")
        for item in items:
            if len(item) > BACKGROUND_MAX_CHARS:
                raise ValueError(f"背景图过大（单张上限 {BACKGROUND_MAX_CHARS // 1024}KB）")
            if not item.startswith(AVATAR_PREFIXES):
                raise ValueError("背景图必须是 jpeg/png/webp 的 data URL")
        return items


class SettingsIn(BaseModel):
    model: str | None = None
    memory_model: str | None = None
    # 界面上的"思考模式"开关；None 表示这次不改它
    disable_thinking: bool | None = None
    # 是否允许局域网来源访问（见 §8.3）；None 表示这次不改它。只有本机能改
    lan_enabled: bool | None = None
