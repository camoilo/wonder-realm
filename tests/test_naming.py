import shutil
import sqlite3
import sys
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

# 用工作区里的临时目录而不是 tempfile.TemporaryDirectory()：系统临时目录在受限沙箱下
# 连清理都会 PermissionError，测试会以一个与断言无关的错误失败（新版 Python 的
# TemporaryDirectory 在删除时还要 chmod，同样被拒）
tmp = Path(__file__).resolve().parent.parent / ".test_naming_tmp"
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
try:
    con = sqlite3.connect(tmp / "fresh.db")
    con.executescript(SCHEMA)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for expected in ("characters", "sessions", "messages", "memories", "app_settings",
                     "character_images", "user_profile", "world"):
        assert expected in tables, f"建表缺少 {expected}：{sorted(tables)}"
    # 偏好已并入 app_settings，不该再有 app_prefs（见 10.46）
    assert "app_prefs" not in tables, f"app_prefs 应已并入 app_settings：{sorted(tables)}"
    # 新库的 sessions / characters 应当自带全部字段
    assert "title_auto" in {r[1] for r in con.execute("PRAGMA table_info(sessions)")}
    columns = {r[1] for r in con.execute("PRAGMA table_info(characters)")}
    assert {"avatar", "locked"} <= columns, f"characters 缺字段：{sorted(columns)}"
    settings_columns = {r[1] for r in con.execute("PRAGMA table_info(app_settings)")}
    assert "disable_thinking" in settings_columns, f"app_settings 缺字段：{sorted(settings_columns)}"
    con.close()
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("naming._clean 与建表用例全部通过")
