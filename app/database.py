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
    -- 自定义头像，存 data URL（jpg/png/webp）。放在最后：ALTER TABLE ADD COLUMN 也是追加到末尾，
    -- 这样新库与补列后的旧库列序一致。空串表示不用自定义头像，回落到姓名首字占位。
    avatar       TEXT NOT NULL DEFAULT ''
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
"""

DB_PATH: Path | None = None
DB_FILENAME = "chatbot.db"


def db_file(data_dir) -> Path:
    """数据库文件路径。备份在 init_db 之前跑，那时 DB_PATH 还没设，所以需要这个入口。"""
    return Path(data_dir) / DB_FILENAME


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _migrate(con: sqlite3.Connection) -> None:
    """为存量的旧库补列：CREATE TABLE IF NOT EXISTS 不会修改已存在的表。

    每张表都先确认存在再补列：本函数也会被只建了部分表的场景调用
    （单测里造的最小旧库就是如此），缺表时静默跳过而不是报错。
    """
    sess_cols = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
    if sess_cols and "title_auto" not in sess_cols:
        con.execute(
            "ALTER TABLE sessions ADD COLUMN title_auto INTEGER NOT NULL DEFAULT 1"
        )
        # 存量会话一律不参与自动命名，避免覆盖用户已有的标题
        con.execute("UPDATE sessions SET title_auto=0")
    char_cols = {row[1] for row in con.execute("PRAGMA table_info(characters)")}
    if char_cols and "avatar" not in char_cols:
        con.execute("ALTER TABLE characters ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")


def init_db(data_dir: str, default_model: str, default_memory_model: str = "") -> None:
    global DB_PATH
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    DB_PATH = path / DB_FILENAME
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    _migrate(con)
    con.execute(
        "INSERT OR IGNORE INTO app_settings(id, model, memory_model, updated_at) VALUES(1, ?, ?, ?)",
        (default_model, default_memory_model, now()),
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


def read_settings() -> dict:
    con = connect()
    try:
        row = con.execute(
            "SELECT model, memory_model FROM app_settings WHERE id=1"
        ).fetchone()
        return dict(row)
    finally:
        con.close()
