from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "ollama": {
        "base_url": "http://localhost:11434",
        # 空 = 首次使用不预选模型：由用户在顶栏自己选，之后沿用上次的选择（app_settings）
        "model": "",
        # temperature 只是兜底：对话生成的实际取值来自会话的「发散程度」档位
        # （见 prompts.chat_options），记忆压缩与会话命名自己压到 0.3
        # num_ctx 是硬天花板：超窗时 Ollama 从最前面静默截断，而系统提示词（角色设定 +
        # 记忆 + 我的设定）正好在最前面。32768 与 memory 的阈值配套，见 DEVELOPMENT §9.5 提示词与解析
        "options": {"temperature": 0.9, "num_ctx": 32768},
    },
    "memory": {
        "model": "",
        # 未归档消息的字符合计到该值就压缩。实测中文约 1.33 字/token，20000 字约
        # 15000 token，加上系统提示词的几千 token 仍在 num_ctx 之内
        "compress_threshold_chars": 20000,
        "archive_batch_size": 20,
        "max_memory_chars": 600,
    },
    # 让模型生成角色设定的等待上限（秒）。给得宽是因为思考型模型开着思考时可能很久：
    # 实测同一提示词 60 秒是常态，偶发一次超过 300 秒
    "character_gen": {"timeout": 600},
    "chat": {"history_max_messages": 60},
    "naming": {"model": "", "max_chars": 12, "min_user_chars": 8},
    "server": {"host": "127.0.0.1", "port": 17800},
    "data_dir": str(ROOT / "data"),
    "backup": {"dir": str(ROOT / "backups"), "days": 14, "on_startup": True},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve(path_like) -> str:
    """相对路径一律相对项目根目录解析，这样从任何工作目录启动都落到同一处。"""
    path = Path(path_like)
    return str(path if path.is_absolute() else ROOT / path)


def load_config() -> dict:
    loaded = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, loaded)
    cfg["data_dir"] = _resolve(cfg["data_dir"])
    backup = cfg.setdefault("backup", {})
    backup["dir"] = _resolve(backup.get("dir") or DEFAULTS["backup"]["dir"])
    return cfg


CONFIG = load_config()


def get_config() -> dict:
    return CONFIG
