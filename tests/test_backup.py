"""数据库备份：自动与手动两类文件的名字、保留天数、以及"手动的不被自动清理"。

用临时目录 + 临时库，绝不碰仓库里的 data/ 与 backups/。
（`POST /api/backup` 只查路由在不在：真调一次会往真实备份目录里写一份，不适合放进用例。）

跑法：uv run python tests/test_backup.py
"""
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import backup  # noqa: E402
from app.config import load_config  # noqa: E402
from app.routes import backup as backup_routes  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


def q(path, sql):
    """读一条。**显式关连接**：Windows 上没关的连接会锁住文件，末尾的临时目录就删不干净。"""
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


tmp = Path(".test_backup_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
db_dir = tmp / "data"
store_dir = tmp / "backups"
db_dir.mkdir()

db_path = db_dir / "chatbot.db"
con = sqlite3.connect(db_path)
con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, note TEXT)")
con.execute("INSERT INTO t(note) VALUES('hello')")
con.commit()
con.close()

# ---- 1. 自动备份：名字是 chatbot-<时间戳>.db，内容可用 ----
auto = backup.make_backup(db_path, store_dir, days=7)
check("自动备份的名字带 chatbot- 前缀与 .db 后缀",
      (auto.name.startswith(backup.PREFIX), auto.suffix), (True, ".db"))
check("时间戳能解析出今天（清理就是按它算的）",
      backup._date_of(auto), datetime.now().date())
check("自动备份里找得到那条数据", q(auto, "SELECT note FROM t"), "hello")
check("备份副本不是 WAL（是一个自包含的文件）",
      q(auto, "PRAGMA journal_mode").lower(), "delete")

# ---- 2. 手动备份：名字与自动的分开，而且不轮转 ----
manual = backup.make_backup(db_path, store_dir, days=0, manual=True)
check("手动备份带 manual- 前缀（与自动的分得清）",
      (manual.name.startswith(backup.MANUAL_PREFIX),
       manual.name.startswith(backup.PREFIX)), (True, False))
check("手动备份内容同样可用", q(manual, "SELECT note FROM t"), "hello")
check("days=0（本该一份不留）也动不了手动备份", manual.exists(), True)
check("existing_backups() 只列自动备份（清理只针对它们）",
      [p.name for p in backup.existing_backups(store_dir)], [auto.name])

# ---- 3. 保留 7 天：超期删、期内留，手动的一律不动 ----
today = datetime.now().date()


def fake(prefix: str, days_ago: int) -> Path:
    p = store_dir / f"{prefix}{(today - timedelta(days=days_ago)).strftime('%Y%m%d')}-120000.db"
    p.write_bytes(b"x")
    return p


stale = [fake(backup.PREFIX, d) for d in (10, 8)]
fresh = [fake(backup.PREFIX, d) for d in (6, 3)]
old_manual = fake(backup.MANUAL_PREFIX, 2000)      # 很久以前手动备的一份

backup.make_backup(db_path, store_dir, days=7, manual=True)
check("手动备份不轮转：超期的自动备份一份没动", [p.exists() for p in stale], [True, True])

backup.make_backup(db_path, store_dir, days=7)
check("自动备份按 7 天清理：超期的删掉", [p.exists() for p in stale], [False, False])
check("7 天以内的留着", [p.exists() for p in fresh], [True, True])
check("手动备份始终不被自动清理删掉（点名要的那份）", old_manual.exists(), True)

# ---- 4. 同一秒里连备两次：另存一份，不覆盖 ----
a = backup.make_backup(db_path, store_dir, manual=True)
b = backup.make_backup(db_path, store_dir, manual=True)
check("同一秒的第二份另起名字", (a != b, b.exists()), (True, True))

# ---- 5. 库不存在时不炸（备份是附加保障，不该挡住启动） ----
check("库不存在时返回 None",
      backup.make_backup(db_dir / "nope.db", store_dir, days=7), None)

shutil.rmtree(tmp, ignore_errors=True)

# ---- 6. 保留天数的默认值与配置 ----
check("代码默认保留 7 天", backup.DEFAULT_DAYS, 7)
check("配置默认保留 7 天", load_config()["backup"]["days"], 7)

# ---- 7. 手动备份接口在（真调会往真实备份目录写一份，所以只查路由）----
from fastapi import FastAPI  # noqa: E402

app = FastAPI()
app.include_router(backup_routes.router)
check("有「手动备份」的接口", "post" in app.openapi().get("paths", {}).get("/api/backup", {}), True)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("备份用例全部通过")
