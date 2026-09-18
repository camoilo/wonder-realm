import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.naming import _clean


def run_case(name, got, expected):
    assert got == expected, f"{name}: got {got!r}, want {expected!r}"


run_case("plain", _clean("深夜便利店的相遇", 12), "深夜便利店的相遇")
run_case("prefix", _clean("标题：深夜便利店的相遇", 12), "深夜便利店的相遇")
run_case("prefix-half", _clean("标题:深夜便利店的相遇", 12), "深夜便利店的相遇")
run_case("quotes", _clean("“深夜便利店的相遇”", 12), "深夜便利店的相遇")
run_case("trailing-punct", _clean("深夜便利店的相遇。", 12), "深夜便利店的相遇")
run_case("multiline", _clean("深夜便利店\n这是解释", 12), "深夜便利店")
run_case("padded", _clean("  深夜便利店  ", 12), "深夜便利店")
run_case("too-long", _clean("这是一个非常非常非常长的标题需要截断", 12), "这是一个非常非常非常长的")
run_case("think-residue", _clean("<think>思考中</think>深夜便利店", 12), "深夜便利店")
run_case("unclosed-think", _clean("<think>还在推理", 12), "")
run_case("empty", _clean("", 12), "")
run_case("blank", _clean("   \n  ", 12), "")
run_case("punct-only", _clean("。。。", 12), "")
run_case("keep-inner-punct", _clean("雨夜,书店", 12), "雨夜,书店")


# ---- 旧库补列迁移 ----
from app.database import SCHEMA, _migrate  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "old.db"
    con = sqlite3.connect(db)
    # 造一个没有 title_auto 的旧库
    con.execute(
        "CREATE TABLE sessions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, character_id INTEGER,"
        "title TEXT NOT NULL DEFAULT '新会话', gen_settings TEXT NOT NULL DEFAULT '{}',"
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    con.execute(
        "INSERT INTO sessions(mode, title, created_at, updated_at) "
        "VALUES('free_scenario','旧会话','2026-01-01T00:00:00','2026-01-01T00:00:00')"
    )
    con.commit()
    _migrate(con)
    _migrate(con)  # 重复执行应当幂等
    cols = {r[1] for r in con.execute("PRAGMA table_info(sessions)")}
    assert "title_auto" in cols, f"迁移后缺少 title_auto：{cols}"
    row = con.execute("SELECT title, title_auto FROM sessions").fetchone()
    assert row == ("旧会话", 0), f"存量会话不应被自动改名，实际 {row!r}"
    # 全量 schema 也应能直接建在新库上
    con.executescript(SCHEMA)
    con.close()

print("naming._clean 与数据库迁移用例全部通过")
