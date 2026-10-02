"""手动备份接口（见 DEVELOPMENT §5.7）。

为什么要有它：自动备份只在**启动时**做一份。正聊到一半、或刚导入了一大批角色时想要一个
明确的还原点，重启应用显然不合适。

走的是与自动备份**同一套** `make_backup()`（在线备份接口 + 校验），只是文件名换成 `manual-`
前缀并跳过轮转——手动的不会被"保留 7 天"那套清理删掉（见 `app/backup.py` 的模块说明）。
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import backup, database
from ..config import get_config

router = APIRouter(prefix="/api")


@router.post("/backup")
def create_backup():
    """现在备份一份，返回文件名/大小/所在目录（界面据此显示"备份到哪了"）。"""
    cfg = get_config()
    opts = cfg.get("backup") or {}
    backup_dir = opts.get("dir")
    if not backup_dir:
        raise HTTPException(400, "配置里没有备份目录（backup.dir）")
    db_path = database.current_db_file(cfg["data_dir"])
    if not Path(db_path).exists():
        raise HTTPException(400, "数据库还不存在，暂时没什么可备份的")
    path = backup.make_backup(db_path, backup_dir, opts.get("days", backup.DEFAULT_DAYS), manual=True)
    if path is None:
        raise HTTPException(500, "备份失败：详情见后端日志（data 目录或备份目录不可写、磁盘满等）")
    return {"file": path.name, "size": path.stat().st_size, "dir": str(path.parent)}
