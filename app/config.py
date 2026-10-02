r"""配置加载。

三个"根"要分清（打包后尤其重要，见 DEVELOPMENT §8.4）：

| 名字 | 是什么 | 开发时 | 打包后 |
|---|---|---|---|
| `RESOURCE_ROOT` | **程序自己的文件**：`app/`、`config.yaml` 模板、`app/static/` | 仓库根 | exe 所在目录（PyInstaller 的 `_internal`） |
| 数据根 | **可变数据**的运行根：`config.yaml`、`data/`、`backups/` | 仓库根 | 由 `--data-dir` / `WR_DATA_DIR` 指定（壳给 `%APPDATA%\wonder-realm-desktop`）；不指定就与程序同目录（绿色版） |
| `data_dir` | 数据库目录 | `<数据根>/data` | 同左 |

配置里的相对路径一律相对**数据根**解析：装到只读位置（如 Program Files）时，写操作全落在数据根，
程序目录一个字节都不动。

`get_config()` 是**懒加载**的：数据根与配置文件要先由启动参数定下来，不能在 import 那一刻定死。
"""
import os
import sys
from pathlib import Path

import yaml

RESOURCE_ROOT = Path(__file__).resolve().parent.parent
# 随程序附带的那份配置（打包后当模板用）：数据根里没有 config.yaml 时用它
CONFIG_PATH = RESOURCE_ROOT / "config.yaml"
# 冻结（PyInstaller）后为 True。只用来"说清这次跑的是哪种形态"（`/api/version` 会下发它）
IS_FROZEN = bool(getattr(sys, "frozen", False))

DEFAULTS = {
    "ollama": {
        "base_url": "http://localhost:11434",
        # 空 = 首次使用不预选模型：由用户在顶栏自己选，之后沿用上次的选择（app_settings）
        "model": "",
        # 启动时若探到本机 Ollama 没在运行，就顺手 `ollama serve` 拉起来（见 §3.4）。
        # 只对本机 base_url 生效；不想要这个行为就置 false
        "auto_start": True,
        # temperature 只是兜底：对话生成的实际取值来自会话的「发散程度」档位
        # （见 prompts.chat_options），记忆压缩与会话命名自己压到 0.3
        # num_ctx 是硬天花板：超窗时 Ollama 从最前面静默截断，而系统提示词（角色设定 +
        # 记忆 + 我的设定）正好在最前面。32768 与 memory 的阈值配套，见 DEVELOPMENT §9.5
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
    "server": {
        # 监听地址：0.0.0.0 = 端口对外开放（手机走 http://<本机IP>:17800）；
        # 127.0.0.1 = 物理上只本机可用。改动后需重启生效
        "host": "127.0.0.1",
        "port": 17800,
        # 首次建库时"推送局域网"（允许非本机来源）的默认值，见 DEVELOPMENT §8.3。
        # 之后以数据库的 app_settings.lan_enabled 为准（默认关，桌面端配置按钮随时改）
        "lan": False,
    },
    # 以下三处**相对数据根**解析（见模块开头那张表）
    "data_dir": "data",
    "backup": {"dir": "backups", "days": 7, "on_startup": True},
}

# 进程级只定一次：run.py 在启动最早处按参数设定
_data_root: Path | None = None
_explicit_config: Path | None = None
_CONFIG: dict | None = None


def data_root() -> Path:
    """可变数据的运行根。"""
    if _data_root is not None:
        return _data_root
    env = os.environ.get("WR_DATA_DIR")
    return Path(env).resolve() if env else RESOURCE_ROOT


def set_data_root(path=None) -> Path:
    """指定可变数据的运行根（`--data-dir` / `WR_DATA_DIR`）；传 None = 用程序目录。"""
    global _data_root, _CONFIG
    _data_root = Path(path).resolve() if path else None
    _CONFIG = None                      # 路径变了，缓存的配置作废
    return data_root()


def set_config_path(path=None) -> None:
    """显式指定配置文件（`--config`）；传 None = 按数据根找。"""
    global _explicit_config, _CONFIG
    _explicit_config = Path(path).resolve() if path else None
    _CONFIG = None


def config_path() -> Path:
    """生效的配置文件：显式指定 > 数据根下的 `config.yaml` > 随程序附带的那份。"""
    if _explicit_config is not None:
        return _explicit_config
    local = data_root() / "config.yaml"
    return local if local.exists() else CONFIG_PATH


def _merge(base: dict, override: dict) -> dict:
    """深合并。**必须是深拷贝**：浅拷贝时 `load_config()` 里加工的嵌套字典就是 `DEFAULTS` 里那个
    对象本身，一改就把模块常量写脏了（`backup.dir` 会被换成绝对路径，后续按"默认值"比较全错）。
    """
    out = {k: (_merge(v, {}) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve(path_like) -> str:
    """相对路径一律相对**数据根**解析，这样从任何工作目录启动都落到同一处。"""
    path = Path(path_like)
    return str(path if path.is_absolute() else data_root() / path)


def load_config() -> dict:
    """读配置并算出生效路径（不写缓存，便于用例反复换数据根）。"""
    path = config_path()
    loaded = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, loaded)
    cfg["data_dir"] = _resolve(cfg["data_dir"])
    backup = cfg.setdefault("backup", {})
    backup["dir"] = _resolve(backup.get("dir") or DEFAULTS["backup"]["dir"])
    return cfg


def get_config() -> dict:
    """生效配置（懒加载，见模块开头）。"""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG
