from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class CharacterIn(BaseModel):
    name: str = Field(min_length=1)
    appearance: str = ""
    personality: str = ""
    speech_style: str = ""
    backstory: str = ""


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
