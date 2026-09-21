"""用户输入的字数上限。

只在这里定义一次：`schemas.py` 的 `max_length` 用它做后端校验，`GET /api/limits` 把它
下发给前端做 `maxlength` 与右下角的实时计数。前后端各写一套数字迟早会对不上——改了后端
忘了前端，用户就会看到"打得进、存不下"。
"""

LIMITS = {
    # 对话内容：够写一大段剧情，又不会把 num_ctx（默认 32768 token）挤爆
    "message": 2000,
    # 编辑消息时的情境说明
    "scenario": 2000,
    # 角色字段。四项里的前三项与 character_gen.MAX_FIELD_CHARS 对齐（生成结果不会超限），
    # 背景故事通常更长，单独放宽
    "name": 20,
    "appearance": 600,
    "personality": 600,
    "speech_style": 600,
    "backstory": 1200,
    # 生成要求的自由文本（题材/文风这类单行、附加要求/导演指令这类多行）
    "genre": 60,
    "extra": 500,
    # 让模型生成角色的提示词
    "hint": 200,
    # "我的设定"（用户本人）：姓名与身份都会进提示词，长度按"一两句话"给
    "user_name": 20,
    "identity": 300,
    "user_appearance": 600,
    # 记忆摘要会注入每一次生成，不能太长；正常由模型压缩产出（配置里约束 600 字）
    "memory": 2000,
    # 会话标题
    "title": 40,
}
