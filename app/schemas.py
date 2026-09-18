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
    content: str = Field(min_length=1)
    scenario: str | None = None


class MemoryEdit(BaseModel):
    content: str = ""


class SettingsIn(BaseModel):
    model: str | None = None
    memory_model: str | None = None
