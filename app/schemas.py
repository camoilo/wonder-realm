from pydantic import BaseModel, Field, field_validator

# 头像以 data URL 存进数据库（跟着库走，备份才完整）。前端已把图片缩到最长边 256px，
# 这里的上限只是兜底：超限多半说明前端压缩没生效，或有人在直接调接口。
AVATAR_MAX_CHARS = 256 * 1024
AVATAR_PREFIXES = (
    "data:image/jpeg;base64,",
    "data:image/png;base64,",
    "data:image/webp;base64,",
)


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1)
    appearance: str = ""
    personality: str = ""
    speech_style: str = ""
    backstory: str = ""
    avatar: str = ""

    @field_validator("avatar")
    @classmethod
    def _check_avatar(cls, v: str) -> str:
        """空串合法（回落到姓名首字占位）；非空必须是白名单内的图片 data URL。

        只放行这几种位图，刻意不含 svg——svg 可以带脚本，而它会被直接放进 <img src>。
        """
        v = (v or "").strip()
        if not v:
            return ""
        if len(v) > AVATAR_MAX_CHARS:
            raise ValueError(f"头像数据过大（上限 {AVATAR_MAX_CHARS // 1024}KB）")
        if not v.startswith(AVATAR_PREFIXES):
            raise ValueError("头像必须是 jpeg/png/webp 的 data URL")
        return v


class SessionIn(BaseModel):
    mode: str = "free_scenario"
    character_id: int | None = None
    title: str = ""  # 留空表示交给模型自动命名（sessions.title_auto）
    gen_settings: dict = {}


class SessionPatch(BaseModel):
    title: str | None = None
    gen_settings: dict | None = None


class MessageEdit(BaseModel):
    # 允许空正文：角色情境里模型可能只写了情境没写台词，那条消息的正文就是空的，
    # 用户编辑情境时不该被迫补一句台词。真正的约束在路由里（正文与情境不能同时为空）
    content: str = ""
    scenario: str | None = None


class MemoryEdit(BaseModel):
    content: str = ""


# 对话区背景图：每角色至多这么多张
BACKGROUND_MAX_COUNT = 5
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
