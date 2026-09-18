"""数据库备份。

为什么用 SQLite 的在线备份接口而不是直接拷文件：库跑在 WAL 模式下，最近的写入可能还留在
`chatbot.db-wal` 里、尚未并回主文件。只拷 `.db` 会得到一个缺少近期对话的快照——平时看不出来，
真要用它恢复时才发现丢的正是最后那段。`Connection.backup()` 通过连接读取当前已提交状态，
WAL 里的内容一并包含，且在应用正常运行、连接打开时也能安全导出。
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ollama_agent")

PREFIX = "chatbot-"
SUFFIX = ".db"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def existing_backups(backup_dir) -> list[Path]:
    """按时间升序列出已有备份：文件名是定宽时间戳，按名字排序即按时间排序。"""
    return sorted(Path(backup_dir).glob(f"{PREFIX}*{SUFFIX}"))


def has_backup_today(backup_dir, today: str | None = None) -> bool:
    """今天是否已经备过——用来保证"每天首次启动备一份"而不是每次重启都备。"""
    day = today or datetime.now().strftime("%Y%m%d")
    return any(p.name.startswith(f"{PREFIX}{day}") for p in Path(backup_dir).glob(f"{PREFIX}*{SUFFIX}"))


def _remove_file(path: Path) -> None:
    """连同可能的 WAL 边车文件一起删，避免轮转后留下孤立的 -wal/-shm 垃圾。"""
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        try:
            p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("删除备份文件失败（%s）：%s", p.name, e)


def _prune(backup_dir: Path, keep: int) -> int:
    """只保留最近 keep 份，返回删掉的数量。"""
    files = existing_backups(backup_dir)
    if keep <= 0 or len(files) <= keep:
        return 0
    removed = 0
    for old in files[:-keep]:
        try:
            _remove_file(old)
            removed += 1
        except OSError as e:  # 删不掉不该影响备份本身
            log.warning("清理旧备份失败（%s）：%s", old.name, e)
    return removed


def make_backup(db_path, backup_dir, keep: int = 14) -> Path | None:
    """把 db_path 备份进 backup_dir，成功返回备份路径；无需备份或失败返回 None。

    本函数不抛异常：备份是附加保障，失败只记日志，绝不能因此挡住应用启动。
    """
    db_path = Path(db_path)
    if not db_path.exists():
        log.info("跳过备份：数据库还不存在（%s），可能是首次运行或刚重置过", db_path)
        return None

    backup_dir = Path(backup_dir)
    target = backup_dir / f"{PREFIX}{_stamp()}{SUFFIX}"
    tmp = target.with_name(target.name + ".tmp")
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():  # 同一秒内被调用两次：沿用已有那份，不覆盖
            return target
        _remove_file(tmp)

        # 用读写方式打开源库：允许 SQLite 自行处理 WAL 恢复，读取到的才是最新已提交状态
        src = sqlite3.connect(db_path)
        try:
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

        # 校验副本；不通过就丢掉。没校验过的备份不能算备份。
        # 顺手把日志模式改回 DELETE：源库是 WAL，副本会继承这个属性并带出 -wal/-shm
        # 边车文件——那样备份就不是"一个自包含的文件"了，恢复和清理都变麻烦。
        chk = sqlite3.connect(tmp)
        try:
            chk.execute("PRAGMA journal_mode=DELETE")
            verdict = chk.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            chk.close()
        if verdict != "ok":
            _remove_file(tmp)
            log.error("备份校验未通过（%s），已丢弃本次备份", verdict)
            return None

        tmp.replace(target)  # 先写临时名再改名：中途失败不会留下半截文件冒充备份
    except (sqlite3.Error, OSError) as e:
        _remove_file(tmp)
        log.error("备份失败：%s", e)
        return None

    removed = _prune(backup_dir, keep)
    log.info(
        "已备份数据库到 %s（%d 字节）%s",
        target,
        target.stat().st_size,
        f"，同时清理了 {removed} 份旧备份" if removed else "",
    )
    return target
