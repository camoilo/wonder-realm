from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:3b",
        "options": {"temperature": 0.8, "num_ctx": 8192},
    },
    "memory": {
        "model": "",
        "compress_threshold_chars": 6000,
        "archive_batch_size": 20,
        "max_memory_chars": 600,
    },
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
