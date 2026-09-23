import json
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
    -- 点击「公开角色设定」后永久置 0。见 character_gen.py 与 DEVELOPMENT §2.2 角色设定
    locked       INTEGER NOT NULL DEFAULT 0,
    -- 这个角色用哪份「我的设定」预设（user_profiles.id），NULL = 不绑定。
    -- 绑定关系**放在角色这一侧**：一条预设可以被多个角色共用（多对一就够了），
    -- 读法是"身份跟着角色走"（见 DEVELOPMENT §2.3 我的设定）。
    -- 被引用的预设删掉时由 delete_preset() 把这一列清成 NULL，不会留悬空引用
    profile_id   INTEGER REFERENCES user_profiles(id),
    -- 同理：这个角色用哪份**世界**预设（worlds.id，NULL = 不绑定）。
    -- 一份世界预设同样可以被多个角色共用（见 DEVELOPMENT §2.4 世界设定）
    world_id     INTEGER REFERENCES worlds(id),
    -- 附加属性**定义**（角色的动态状态：好感 / 心情 / 表情…）。JSON 数组
    -- [{"name","type","hint"}]，type 取 "text" / "percent"。照 worlds.terms 的先例用一列
    -- JSON：它是"整体读写、有序、可增删"的一份小列表，没有按条查询的需求（见 §2.6）
    attr_defs    TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    mode         TEXT NOT NULL CHECK(mode IN ('chat','immersive','director')),
    character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
    -- 导演会话绑定的世界预设（worlds.id，NULL = 不用世界）。只有导演模式会用到它：
    -- 聊天与沉浸两种模式的世界跟着**角色**的 world_id 走（见 DEVELOPMENT §2.4 世界设定）
    world_id     INTEGER REFERENCES worlds(id),
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
    -- 这条消息带回来的附加属性值：JSON 数组 [{"name","type","value"}]（见 §2.6）。
    -- **自带名称与类型**：定义改了、或那条属性被删了，历史消息照样能渲染出来
    attrs      TEXT NOT NULL DEFAULT '[]',
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
    id               INTEGER PRIMARY KEY CHECK(id = 1),
    model            TEXT NOT NULL,
    memory_model     TEXT NOT NULL DEFAULT '',
    -- 界面偏好也收在这一张表里（见 DEVELOPMENT §9.6 界面约定）。
    -- 代价：以后每加一个偏好都要加列，届时要按 4.2 的例外流程做一次性维护
    disable_thinking INTEGER NOT NULL DEFAULT 0,
    -- 是否允许局域网来源访问（见 §8.3）：0 = 只有本机可用（默认，安全优先）。
    -- 监听地址可能是 0.0.0.0（端口对外开放），放不放行由这道开关在应用层决定
    lan_enabled      INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL
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

-- 界面偏好也在这张表里（见 DEVELOPMENT §9.6 界面约定）

-- 用户本人的设定（右侧面板的"我的设定"）。**约定** id=1 是当前使用的那份，
-- id>1 是用户存下来的预设（见 DEVELOPMENT §2.3 我的设定）——所以这里**不能**再写 CHECK(id=1)：
-- 那条约束会把整张表锁成单行，预设就存不进来。
-- 单开一张表而不是给别的表加列：新表对已有库也会建出来（见 4.2），无需用户删库；
-- 而且它是"用户"这个主体的属性，跟角色、会话都没有从属关系。
-- 表名用复数：它装的不是"一行数据"，而是"当前那份 + 若干预设"（world → worlds 同理）
CREATE TABLE IF NOT EXISTS user_profiles (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    identity   TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '',
    avatar     TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

-- 世界设定（右侧面板的"世界设定"）。**和"我的设定"同一套约定**：id=1 是当前世界，id>1 是世界预设。
-- 三种模式都注入提示词：聊天与沉浸跟着**角色**的绑定走，导演会话跟着**会话**的绑定走（见 2.4）。
-- terms 存 JSON 数组 [{"term": ..., "meaning": ...}]：它有序、可增删，整体读写最省事；
-- 名称只给自己辨认，**不进提示词**（用户明确要求）。
CREATE TABLE IF NOT EXISTS worlds (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    rules       TEXT NOT NULL DEFAULT '',
    terms       TEXT NOT NULL DEFAULT '[]',
    updated_at  TEXT NOT NULL
);
"""

DB_PATH: Path | None = None
DB_FILENAME = "chatbot.db"
# init_db 时记下来的默认值：运行中库文件被删掉要重建时，得用同一份默认值补 app_settings
_DEFAULT_MODEL = ""
_DEFAULT_MEMORY_MODEL = ""
_DEFAULT_LAN = False


def db_file(data_dir) -> Path:
    """数据库文件路径。备份在 init_db 之前跑，那时 DB_PATH 还没设，所以需要这个入口。"""
    return Path(data_dir) / DB_FILENAME


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 建表用的是 CREATE TABLE IF NOT EXISTS：**老库不会自动长出新列**，所以给已有表新增列时必须
# 在这里登记一次，否则老库上这一列永远不存在（新库由 SCHEMA 直接建出来）。
# 只登记"加列"，改类型/删列 SQLite 也不支持——那种情况按 4.2 的例外流程重建。
_COLUMN_MIGRATIONS = {
    "characters": {
        "profile_id": "INTEGER REFERENCES user_profiles(id)",
        "world_id": "INTEGER REFERENCES worlds(id)",
        "attr_defs": "TEXT NOT NULL DEFAULT '[]'",
    },
    "sessions": {"world_id": "INTEGER REFERENCES worlds(id)"},
    "messages": {"attrs": "TEXT NOT NULL DEFAULT '[]'"},
    # app_settings 是单行设置表：每加一个偏好就在这里登记一次
    "app_settings": {"lan_enabled": "INTEGER NOT NULL DEFAULT 0"},
}

# 老库里的旧表名 → 新表名。改名的理由：这两张表装的都是"当前那份 + 若干预设"，
# 单数名字会让人以为是单行表。必须**先改名、再建表**：新库直接按新名字建，
# 老库改完名之后建表脚本里的 CREATE TABLE IF NOT EXISTS 自然成了空操作。
# SQLite 的 RENAME 会同步改写别的表里指向它的外键（characters.profile_id 就是这种情况），
# tests/test_naming.py 专门盯着这一点。
_TABLE_RENAMES = {"user_profile": "user_profiles", "world": "worlds"}


def _apply_table_renames(con) -> None:
    """旧表名改成新名字。幂等：已经改过（或本来就是新库）就什么都不做。"""
    have = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for old, new in _TABLE_RENAMES.items():
        if old in have and new not in have:
            con.execute(f"ALTER TABLE {old} RENAME TO {new}")


def _apply_column_migrations(con) -> None:
    """缺哪列补哪列。幂等：已存在的列一律不动。"""
    for table, columns in _COLUMN_MIGRATIONS.items():
        have = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _create_schema() -> None:
    """改名 + 建表 + 补列 + 单行表的初始行。幂等（IF NOT EXISTS / INSERT OR IGNORE），可反复调用。"""
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    _apply_table_renames(con)
    con.executescript(SCHEMA)
    _apply_column_migrations(con)
    con.execute(
        "INSERT OR IGNORE INTO app_settings(id, model, memory_model, lan_enabled, updated_at) "
        "VALUES(1, ?, ?, ?, ?)",
        (_DEFAULT_MODEL, _DEFAULT_MEMORY_MODEL, 1 if _DEFAULT_LAN else 0, now()),
    )
    # "我的设定"也是那个主体的一行：缺了就补一行空白的，读的时候不必到处判 None
    con.execute(
        "INSERT OR IGNORE INTO user_profiles(id, updated_at) VALUES(1, ?)", (now(),)
    )
    # "世界设定"同理（id=1 是当前世界）
    con.execute("INSERT OR IGNORE INTO worlds(id, updated_at) VALUES(1, ?)", (now(),))
    con.commit()
    con.close()


def init_db(
    data_dir: str,
    default_model: str,
    default_memory_model: str = "",
    default_lan: bool = False,
) -> None:
    """建库建表（含老库改名与补列，见 _TABLE_RENAMES / _COLUMN_MIGRATIONS）。

    `default_lan` 只在**首次建库**时写进 `app_settings.lan_enabled`（见 §8.3）：
    与模型选择一样，配置里那个值只作首次默认，之后以库里的为准。
    """
    global DB_PATH, _DEFAULT_MODEL, _DEFAULT_MEMORY_MODEL, _DEFAULT_LAN
    _DEFAULT_MODEL = default_model
    _DEFAULT_MEMORY_MODEL = default_memory_model
    _DEFAULT_LAN = default_lan
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    DB_PATH = path / DB_FILENAME
    _create_schema()


def ensure_db() -> None:
    """运行中库文件（或 data/ 目录）不见了就重建再继续，不必重启应用。

    建表若只发生在启动路径上，运行中删掉 data/ 就会让之后每个请求都 500，
    界面看起来像"前端连不上后端"（见 DEVELOPMENT §9.3）。
    """
    if DB_PATH is None:  # 还没 init_db（例如备份脚本只 import 本模块）
        return
    try:
        if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
            return
    except OSError:  # 正好被删/被占：当成"不在"处理，重建
        pass
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _create_schema()


def connect() -> sqlite3.Connection:
    ensure_db()
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


def thinking_disabled() -> bool:
    """生成时是否禁用思考模式。集中在这里读，聊天/重新生成/记忆压缩/自动命名就都会遵守。

    这个开关就在 `app_settings` 那一行里（见 DEVELOPMENT §9.6）：
    与模型选择同表同行的好处是"读一次设置就拿到全部"，不必再查第二张表。
    """
    con = connect()
    try:
        row = con.execute(
            "SELECT disable_thinking FROM app_settings WHERE id=1"
        ).fetchone()
    finally:
        con.close()
    return bool(row["disable_thinking"]) if row else False


def write_disable_thinking(disabled: bool) -> None:
    con = connect()
    try:
        con.execute(
            "UPDATE app_settings SET disable_thinking=?, updated_at=? WHERE id=1",
            (1 if disabled else 0, now()),
        )
        con.commit()
    finally:
        con.close()


PROFILE_FIELDS = ("name", "identity", "appearance", "avatar")


def read_profile() -> dict:
    """用户本人的设定。行不存在时返回全空，调用方不必判 None（init_db 会补行）。

    `id=1` 这一行是"当前使用的设定"；`id>1` 的行是保存下来的**预设**（见 DEVELOPMENT §2.3 我的设定）。
    两者共用一张表：旧库直接可用，不必改表结构，也不必再开一张表。
    """
    con = connect()
    try:
        row = con.execute(
            "SELECT name, identity, appearance, avatar FROM user_profiles WHERE id=1"
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else {k: "" for k in PROFILE_FIELDS}


def read_profile_by_id(pid: int) -> dict | None:
    """按 id 取一行（预设表用）。不存在返回 None。"""
    con = connect()
    try:
        row = con.execute(
            f"SELECT {_PRESET_COLS} FROM user_profiles WHERE id=?", (pid,)
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def write_profile(values: dict) -> dict:
    """整体覆盖式写入（表单就是整体提交的），返回写入后的结果。"""
    con = connect()
    try:
        con.execute(
            "UPDATE user_profiles SET name=?, identity=?, appearance=?, avatar=?, updated_at=? WHERE id=1",
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


# ---- "我的设定"的预设：同一张表的 id>1 行（见 DEVELOPMENT §2.3 我的设定） ----

_PRESET_COLS = "id, name, identity, appearance, avatar, updated_at"


def _bound_characters(con, column: str) -> dict[int, list[dict]]:
    """按绑定列反查：{预设 id: [绑了它的角色]}。

    绑定存在角色侧（`characters.profile_id` / `characters.world_id`），所以预设列表要显示
    "这条给了哪些角色"就得反查一次。两种预设共用这一份，免得两处口径不一。
    """
    bound: dict[int, list[dict]] = {}
    for r in con.execute(
        f"SELECT id, name, {column} AS pid FROM characters WHERE {column} IS NOT NULL ORDER BY id"
    ):
        bound.setdefault(r["pid"], []).append({"id": r["id"], "name": r["name"]})
    return bound


def list_presets() -> list[dict]:
    """已保存的预设，新的排前面。id=1 是当前设定，不算预设。

    每条附一个 `characters`：绑定了这条预设的角色（`[{"id", "name"}]`，按 id 升序）。
    弹窗里要显示"这条预设给了哪些角色"，所以在同一个响应里一次给全，前端不必再拼。
    """
    con = connect()
    try:
        rows = con.execute(
            f"SELECT {_PRESET_COLS} FROM user_profiles WHERE id>1 ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        bound = _bound_characters(con, "profile_id")
    finally:
        con.close()
    return [{**dict(r), "characters": bound.get(r["id"], [])} for r in rows]


def add_preset(values: dict) -> dict:
    """把当前表单存成一条预设（含头像），返回新建的预设。"""
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO user_profiles(name, identity, appearance, avatar, updated_at) "
            "VALUES(?,?,?,?,?)",
            (
                values.get("name", ""),
                values.get("identity", ""),
                values.get("appearance", ""),
                values.get("avatar", ""),
                now(),
            ),
        )
        con.commit()
        row = con.execute(
            f"SELECT {_PRESET_COLS} FROM user_profiles WHERE id=?", (cur.lastrowid,)
        ).fetchone()
    finally:
        con.close()
    return dict(row)


def update_preset(preset_id: int, values: dict) -> dict | None:
    """用当前表单覆盖一条预设（"保存预设"）；id<=1 或不存在返回 None。"""
    if preset_id <= 1:
        return None
    con = connect()
    try:
        cur = con.execute(
            "UPDATE user_profiles SET name=?, identity=?, appearance=?, avatar=?, updated_at=? "
            "WHERE id=?",
            (
                values.get("name", ""),
                values.get("identity", ""),
                values.get("appearance", ""),
                values.get("avatar", ""),
                now(),
                preset_id,
            ),
        )
        if cur.rowcount == 0:
            return None
        con.commit()
        row = con.execute(
            f"SELECT {_PRESET_COLS} FROM user_profiles WHERE id=?", (preset_id,)
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


def delete_preset(preset_id: int) -> bool:
    """删除一条预设。id<=1 一律拒绝——那是当前设定本身，不是预设。

    顺手把绑定了它的角色解绑（置 NULL）：这一列没有 ON DELETE 级联，
    留着悬空 id 的话角色会一直"指着一份不存在的设定"。
    """
    if preset_id <= 1:
        return False
    con = connect()
    try:
        con.execute("UPDATE characters SET profile_id=NULL WHERE profile_id=?", (preset_id,))
        cur = con.execute("DELETE FROM user_profiles WHERE id=?", (preset_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# ---- 附加属性：定义在 characters.attr_defs、值在 messages.attrs（见 DEVELOPMENT §2.6） ----

ATTR_TYPES = ("text", "percent")
ATTR_PERCENT_MAX = 100.0


def _clean_attr_def_list(items) -> list[dict]:
    """规范化一份定义列表（读与写共用：两边形状必须一致）。名称为空的行丢弃——
    界面上刚点出来、还没填的空行不该让整次保存失败。"""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        kind = str(item.get("type") or "").strip()
        if not name or kind not in ATTR_TYPES:
            continue
        out.append({"name": name, "type": kind, "hint": str(item.get("hint") or "").strip()})
    return out


def parse_attr_defs(raw) -> list[dict]:
    """角色的属性定义（那列 JSON）→ `[{name, type, hint}]`。

    认不出的条目直接丢掉：定义是后续一切（提示词、解析、渲染）的唯一依据，
    宁可少一条，也不能出现"半条定义"把注入与解析带偏。
    """
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return _clean_attr_def_list(data) if isinstance(data, list) else []


def clean_attr_defs(items) -> str:
    """写入前的定义列内容。"""
    return json.dumps(_clean_attr_def_list(items), ensure_ascii=False)


def _attr_value(kind: str, value):
    """一个属性值 → 存进去用的形状。百分比型夹到 0-100 的数字，文字型是短字符串。"""
    if kind == "percent":
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = float(str(value).strip().rstrip("%"))
        except (TypeError, ValueError):
            return None
        return max(0.0, min(ATTR_PERCENT_MAX, number))
    text = str(value or "").strip()
    return text or None


def _clean_attr_list(items) -> list[dict]:
    """规范化一份属性值列表：空值的那条不写进来（"没设置"就不该出现在展示与注入里）。"""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        kind = str(item.get("type") or "").strip()
        if not name or kind not in ATTR_TYPES:
            continue
        value = _attr_value(kind, item.get("value"))
        if value is None:
            continue
        out.append({"name": name, "type": kind, "value": value})
    return out


def parse_attrs(raw) -> list[dict]:
    """消息那列 JSON → `[{name, type, value}]`。"""
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return _clean_attr_list(data) if isinstance(data, list) else []


def clean_attrs(items) -> str:
    """写入前的属性值列内容（与 `parse_attrs` 对称）。"""
    return json.dumps(_clean_attr_list(items), ensure_ascii=False)


# ---- 世界设定：id=1 是当前世界、id>1 是世界预设（见 DEVELOPMENT §2.4 世界设定） ----

_WORLD_COLS = "id, name, description, rules, terms, updated_at"


def _world_row(row) -> dict:
    """把一行世界设定转成接口用的形状（terms 从 JSON 解成列表）。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "rules": row["rules"],
        "terms": _parse_terms(row["terms"]),
    }


def read_world_by_id(pid: int) -> dict | None:
    """按 id 取一行世界设定（预设表用）。不存在返回 None。"""
    con = connect()
    try:
        row = con.execute(
            "SELECT id, name, description, rules, terms FROM worlds WHERE id=?", (pid,)
        ).fetchone()
    finally:
        con.close()
    return _world_row(row) if row else None


def list_world_presets() -> list[dict]:
    """已保存的世界预设，新的排前面。id=1 是当前世界，不算预设。

    与"我的设定"预设完全同构：每项附 `characters`（绑定了这条世界预设的角色）。
    导演会话绑的是 `sessions.world_id`，那条路径不在预设列表里显示（列表只说角色）。
    """
    con = connect()
    try:
        rows = con.execute(
            f"SELECT {_WORLD_COLS} FROM worlds WHERE id>1 ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        bound = _bound_characters(con, "world_id")
    finally:
        con.close()
    return [{**_world_row(r), "characters": bound.get(r["id"], [])} for r in rows]


def add_world_preset(values: dict) -> dict:
    """把当前世界存成一条新预设，返回新建的预设。"""
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO worlds(name, description, rules, terms, updated_at) VALUES(?,?,?,?,?)",
            (*_world_values(values), now()),
        )
        con.commit()
        row = con.execute(
            f"SELECT {_WORLD_COLS} FROM worlds WHERE id=?", (cur.lastrowid,)
        ).fetchone()
    finally:
        con.close()
    return _world_row(row)


def update_world_preset(preset_id: int, values: dict) -> dict | None:
    """覆盖一条世界预设。id<=1（当前世界本身）或不存在返回 None。"""
    if preset_id <= 1:
        return None
    con = connect()
    try:
        name, description, rules, terms = _world_values(values)
        cur = con.execute(
            "UPDATE worlds SET name=?, description=?, rules=?, terms=?, updated_at=? WHERE id=?",
            (name, description, rules, terms, now(), preset_id),
        )
        if cur.rowcount == 0:
            return None
        con.commit()
        row = con.execute(
            f"SELECT {_WORLD_COLS} FROM worlds WHERE id=?", (preset_id,)
        ).fetchone()
    finally:
        con.close()
    return _world_row(row) if row else None


def delete_world_preset(preset_id: int) -> bool:
    """删除一条世界预设。id<=1 一律拒绝——那是当前世界本身。

    引用它的角色与导演会话一并解绑（这两列都没有 ON DELETE 级联）。
    """
    if preset_id <= 1:
        return False
    con = connect()
    try:
        con.execute("UPDATE characters SET world_id=NULL WHERE world_id=?", (preset_id,))
        con.execute("UPDATE sessions SET world_id=NULL WHERE world_id=?", (preset_id,))
        cur = con.execute("DELETE FROM worlds WHERE id=?", (preset_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()

WORLD_FIELDS = ("name", "description", "rules", "terms")


def _parse_terms(raw: str) -> list[dict]:
    """词库那串 JSON 出库时解成 [{"term", "meaning"}]。

    解不出来（手改过库、字段被写坏）时退回空列表：这里宁可能力降级，也不要让整次读取、
    进而让整个生成都失败——词库只是锦上添花。
    """
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "term": str(item.get("term") or ""),
                "meaning": str(item.get("meaning") or ""),
            }
        )
    return out


def _dump_terms(items) -> str:
    """把词库整成入库用的 JSON。名词为空的行直接丢弃——界面上刚点出来、还没填的空行
    不该让整次保存失败（与 `_parse_terms` 是一对形状规则，放一处才不会读写走偏）。"""
    terms = []
    for item in items or []:
        term = str((item or {}).get("term") or "").strip()
        if not term:
            continue
        terms.append({"term": term, "meaning": str((item or {}).get("meaning") or "").strip()})
    return json.dumps(terms, ensure_ascii=False)


def _world_values(values: dict) -> tuple:
    """写入世界用的四个值（文本 strip + 词库转 JSON）。当前世界与预设共用这一处。"""
    return (
        str(values.get("name") or "").strip(),
        str(values.get("description") or "").strip(),
        str(values.get("rules") or "").strip(),
        _dump_terms(values.get("terms")),
    )


def read_world() -> dict:
    """当前世界（id=1）。行不存在时返回空设定，调用方不必判 None（init_db 会补行）。"""
    con = connect()
    try:
        row = con.execute(
            "SELECT name, description, rules, terms FROM worlds WHERE id=1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {"name": "", "description": "", "rules": "", "terms": []}
    return {
        "name": row["name"],
        "description": row["description"],
        "rules": row["rules"],
        "terms": _parse_terms(row["terms"]),
    }


def write_world(values: dict) -> dict:
    """整体覆盖式写入（表单就是整体提交的），返回写入后的结果。"""
    con = connect()
    try:
        con.execute(
            "UPDATE worlds SET name=?, description=?, rules=?, terms=?, updated_at=? WHERE id=1",
            (*_world_values(values), now()),
        )
        con.commit()
    finally:
        con.close()
    return read_world()


def read_settings() -> dict:
    """运行设置 + 界面偏好。两者同表，一次查询就够。"""
    con = connect()
    try:
        row = con.execute(
            "SELECT model, memory_model, disable_thinking, lan_enabled "
            "FROM app_settings WHERE id=1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {
            "model": "", "memory_model": "", "disable_thinking": False, "lan_enabled": False,
        }
    return {
        "model": row["model"],
        "memory_model": row["memory_model"],
        "disable_thinking": bool(row["disable_thinking"]),
        "lan_enabled": bool(row["lan_enabled"]),
    }


def lan_enabled() -> bool:
    """是否允许局域网来源访问（见 DEVELOPMENT §8.3）。

    与 `thinking_disabled()` 同一个路子：集中读一处，闸门中间件每次请求都问它。
    **默认关**：监听地址可能是 0.0.0.0（端口对外开放），但非本机来源要这道闸门放行。
    """
    con = connect()
    try:
        row = con.execute("SELECT lan_enabled FROM app_settings WHERE id=1").fetchone()
    finally:
        con.close()
    return bool(row["lan_enabled"]) if row else False


def write_lan_enabled(enabled: bool) -> None:
    con = connect()
    try:
        con.execute(
            "UPDATE app_settings SET lan_enabled=?, updated_at=? WHERE id=1",
            (1 if enabled else 0, now()),
        )
        con.commit()
    finally:
        con.close()
