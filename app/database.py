import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    appearance   TEXT NOT NULL DEFAULT '',
    personality  TEXT NOT NULL DEFAULT '',
    speech_style TEXT NOT NULL DEFAULT '',
    backstory    TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    -- 自定义头像，存 data URL（jpg/png/webp）。空串表示不用自定义头像，回落到姓名首字占位
    avatar       TEXT NOT NULL DEFAULT '',
    -- 探索模式：1 = 性格/语言风格/背景故事对用户隐藏且不可改（接口也不下发），
    -- 点击「公开角色设定」后永久置 0。见 character_gen.py 与 10.29
    locked       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mode         TEXT NOT NULL CHECK(mode IN ('character_chat','character_scenario','free_scenario')),
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    title        TEXT NOT NULL DEFAULT '新会话',
    title_auto   INTEGER NOT NULL DEFAULT 1,
    gen_settings TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content    TEXT NOT NULL,
    scenario   TEXT,
    archived   INTEGER NOT NULL DEFAULT 0,
    edited     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type    TEXT NOT NULL CHECK(scope_type IN ('character','session')),
    scope_id      INTEGER NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    UNIQUE(scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    id           INTEGER PRIMARY KEY CHECK(id = 1),
    model        TEXT NOT NULL,
    memory_model TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);

-- 角色的对话区背景图，每个角色至多若干张（上限在 schemas.py）。
-- 刻意不放进 characters 表：头像是单张就已经让每次角色列表都把它带上，
-- 背景图有 5 张、单张可达数百 KB，塞进角色表会让列表接口变成每次几 MB。
CREATE TABLE IF NOT EXISTS character_images (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    data         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_character_images ON character_images(character_id, position, id);

-- 零散的界面偏好，键值对存放。用独立的新表而不是给 app_settings 加列：
-- CREATE TABLE IF NOT EXISTS 对**已有库**也会把新表建出来，而加列不会（我们不做补列，
-- 见 4.2）——所以新表不需要用户删库重建，新列需要。
CREATE TABLE IF NOT EXISTS app_prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- 用户本人的设定（右侧面板的"我的设定"）。全局单行表，和 app_settings 一样。
-- 单开一张表而不是给别的表加列：新表对已有库也会建出来（见 4.2），无需用户删库；
-- 而且它是"用户"这个主体的属性，跟角色、会话都没有从属关系
CREATE TABLE IF NOT EXISTS user_profile (
    id         INTEGER PRIMARY KEY CHECK(id=1),
    name       TEXT NOT NULL DEFAULT '',
    identity   TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '',
    avatar     TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""

DB_PATH: Path | None = None
DB_FILENAME = "chatbot.db"


def db_file(data_dir) -> Path:
    """数据库文件路径。备份在 init_db 之前跑，那时 DB_PATH 还没设，所以需要这个入口。"""
    return Path(data_dir) / DB_FILENAME


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db(data_dir: str, default_model: str, default_memory_model: str = "") -> None:
    """建库建表。不做旧库补列：开发阶段直接删掉 data/ 重建即可（见 DEVELOPMENT 4.2）。"""
    global DB_PATH
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    DB_PATH = path / DB_FILENAME
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.execute(
        "INSERT OR IGNORE INTO app_settings(id, model, memory_model, updated_at) VALUES(1, ?, ?, ?)",
        (default_model, default_memory_model, now()),
    )
    # "我的设定"也是单行表：缺了就补一行空白的，读的时候不必到处判 None
    con.execute(
        "INSERT OR IGNORE INTO user_profile(id, updated_at) VALUES(1, ?)", (now(),)
    )
    con.commit()
    con.close()


def connect() -> sqlite3.Connection:
    # check_same_thread=False：SSE 生成器与依赖注入可能在不同线程使用连接
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def get_db():
    con = connect()
    try:
        yield con
    finally:
        con.close()


# 界面偏好：是否禁用思考模式（存 "1"/"0"）
PREF_DISABLE_THINKING = "disable_thinking"


def read_pref(key: str, default: str = "") -> str:
    con = connect()
    try:
        row = con.execute("SELECT value FROM app_prefs WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        con.close()


def write_pref(key: str, value: str) -> None:
    con = connect()
    try:
        con.execute(
            "INSERT INTO app_prefs(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        con.commit()
    finally:
        con.close()


def thinking_disabled() -> bool:
    """生成时是否禁用思考模式。集中在这里读，聊天/重新生成/记忆压缩/自动命名就都会遵守。"""
    return read_pref(PREF_DISABLE_THINKING, "0") == "1"


PROFILE_FIELDS = ("name", "identity", "appearance", "avatar")


def read_profile() -> dict:
    """用户本人的设定。行不存在时返回全空，调用方不必判 None（init_db 会补行）。"""
    con = connect()
    try:
        row = con.execute(
            "SELECT name, identity, appearance, avatar FROM user_profile WHERE id=1"
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else {k: "" for k in PROFILE_FIELDS}


def write_profile(values: dict) -> dict:
    """整体覆盖式写入（表单就是整体提交的），返回写入后的结果。"""
    con = connect()
    try:
        con.execute(
            "UPDATE user_profile SET name=?, identity=?, appearance=?, avatar=?, updated_at=? WHERE id=1",
            (
                values.get("name", ""),
                values.get("identity", ""),
                values.get("appearance", ""),
                values.get("avatar", ""),
                now(),
            ),
        )
        con.commit()
    finally:
        con.close()
    return read_profile()


def read_settings() -> dict:
    con = connect()
    try:
        row = con.execute(
            "SELECT model, memory_model FROM app_settings WHERE id=1"
        ).fetchone()
        out = dict(row)
    finally:
        con.close()
    out["disable_thinking"] = thinking_disabled()
    return out
