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
    "server": {"host": "127.0.0.1", "port": 8000},
    "data_dir": str(ROOT / "data"),
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    loaded = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, loaded)
    data_dir = Path(cfg["data_dir"])
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    cfg["data_dir"] = str(data_dir)
    return cfg


CONFIG = load_config()


def get_config() -> dict:
    return CONFIG
