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


# ---- 建表 ----
# 不做旧库补列（开发阶段直接删库重建），这里只确认 SCHEMA 能在空库上直接建起来
from app.database import SCHEMA  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    con = sqlite3.connect(Path(tmp) / "fresh.db")
    con.executescript(SCHEMA)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for expected in ("characters", "sessions", "messages", "memories", "app_settings",
                     "character_images", "app_prefs"):
        assert expected in tables, f"建表缺少 {expected}：{sorted(tables)}"
    # 新库的 sessions / characters 应当自带全部字段
    assert "title_auto" in {r[1] for r in con.execute("PRAGMA table_info(sessions)")}
    assert "avatar" in {r[1] for r in con.execute("PRAGMA table_info(characters)")}
    con.close()

print("naming._clean 与建表用例全部通过")
