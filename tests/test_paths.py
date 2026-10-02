r"""路径解析：程序文件（RESOURCE_ROOT）与可变数据（数据根）要分得开（见 DEVELOPMENT §8.4）。

打包后程序目录可能是只读的（Program Files），所以 `config.yaml` / `data/` / `backups/` 必须能
指到别处（壳给 `%APPDATA%\<应用>`，命令行用户给 `--data-dir`）；不指就与程序同目录（绿色版）。

跑法：uv run python tests/test_paths.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from app import config as cfgmod  # noqa: E402
from app import __version__  # noqa: E402

FAILED = []


def check(name, got, want):
    ok = got == want
    if not ok:
        FAILED.append(name)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: {got!r}" + ("" if ok else f" != {want!r}"))


tmp = Path(".test_paths_tmp").resolve()
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()

try:
    # ---- 1. 开发态（不指定数据根）：一切照旧落在仓库里 ----
    cfgmod.set_data_root(None)
    cfgmod.set_config_path(None)
    cfg = cfgmod.get_config()
    check("默认数据根 = 程序目录", cfgmod.data_root(), cfgmod.RESOURCE_ROOT)
    check("默认库目录 = <根>/data", Path(cfg["data_dir"]), cfgmod.RESOURCE_ROOT / "data")
    check("默认备份目录 = <根>/backups",
          Path(cfg["backup"]["dir"]), cfgmod.RESOURCE_ROOT / "backups")
    check("仓库里没有 config.yaml 时用随程序附带的那份",
          cfgmod.config_path(), cfgmod.CONFIG_PATH)

    # ---- 2. 指定数据根（打包版：壳把 %APPDATA% 那个目录传进来）----
    cfgmod.set_data_root(tmp)
    cfg = cfgmod.get_config()
    check("数据根换了，库目录跟着换", Path(cfg["data_dir"]), tmp / "data")
    check("备份目录也跟着换", Path(cfg["backup"]["dir"]), tmp / "backups")
    check("数据根里没有 config.yaml 时仍用附带的那份",
          cfgmod.config_path(), cfgmod.CONFIG_PATH)

    (tmp / "config.yaml").write_text(
        "server: {port: 17999}\ndata_dir: ./my-data\nbackup: {dir: ./my-backups}\n",
        encoding="utf-8")
    cfgmod.set_data_root(tmp)          # 重新定一次让缓存作废
    cfg = cfgmod.get_config()
    check("数据根里的 config.yaml 优先（用户可改这份）", cfgmod.config_path(), tmp / "config.yaml")
    check("配置里的相对路径相对**数据根**解析", Path(cfg["data_dir"]), tmp / "my-data")
    check("备份的相对路径同理", Path(cfg["backup"]["dir"]), tmp / "my-backups")
    check("改动确实生效（端口来自新配置）", cfg["server"]["port"], 17999)

    # 绝对路径原样用（网盘同步目录这类）
    (tmp / "config.yaml").write_text(
        f"data_dir: {tmp / 'abs-data'}\nbackup: {{dir: {tmp / 'abs-backups'}}}\n", encoding="utf-8")
    cfgmod.set_config_path(tmp / "config.yaml")
    cfg = cfgmod.get_config()
    check("绝对路径原样用",
          (Path(cfg["data_dir"]), Path(cfg["backup"]["dir"])),
          (tmp / "abs-data", tmp / "abs-backups"))

    # ---- 3. 显式 --config 优先于数据根里的那份 ----
    other = tmp / "elsewhere.yaml"
    other.write_text("server: {port: 17888}\n", encoding="utf-8")
    cfgmod.set_config_path(other)
    check("显式指定的配置文件优先", (cfgmod.config_path(), cfgmod.get_config()["server"]["port"]),
          (other, 17888))

    # ---- 4. 环境变量 WR_DATA_DIR（壳之外的入口也能指）----
    cfgmod.set_config_path(None)
    cfgmod.set_data_root(None)
    os.environ["WR_DATA_DIR"] = str(tmp / "env-root")
    try:
        check("环境变量能指定数据根", cfgmod.data_root(), tmp / "env-root")
        check("环境变量生效时库也落在它下面",
              Path(cfgmod.get_config()["data_dir"]), tmp / "env-root" / "data")
    finally:
        os.environ.pop("WR_DATA_DIR", None)
    check("去掉环境变量就回到程序目录", cfgmod.data_root(), cfgmod.RESOURCE_ROOT)

    # ---- 5. 懒加载：先定路径再取配置，不能 import 那一刻定死 ----
    cfgmod.set_data_root(tmp / "cache-a")
    check("换数据根后缓存作废（get_config 跟着变）",
          Path(cfgmod.get_config()["data_dir"]), tmp / "cache-a" / "data")

    # ---- 6. 随程序附带的那份 config.yaml 必须是相对路径（否则打包后会指回开发机）----
    shipped = yaml.safe_load(cfgmod.CONFIG_PATH.read_text(encoding="utf-8"))
    check("config.yaml 里的 data_dir 是相对路径",
          Path(shipped["data_dir"]).is_absolute(), False)
    check("config.yaml 里的 backup.dir 是相对路径",
          Path(shipped["backup"]["dir"]).is_absolute(), False)
    check("DEFAULTS 里这两处也是相对路径",
          (Path(cfgmod.DEFAULTS["data_dir"]).is_absolute(),
           Path(cfgmod.DEFAULTS["backup"]["dir"]).is_absolute()), (False, False))

    # ---- 7. run.py 真的把这两个参数接上了（静态守卫：参数少，不上 argparse）----
    run_src = (Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8")
    check("run.py 接 --data-dir / --config 并在读配置前设定",
          'config.set_data_root(_arg_value(args, "--data-dir"))' in run_src
          and 'config.set_config_path(_arg_value(args, "--config"))' in run_src
          and run_src.index("set_data_root(") < run_src.index("cfg = get_config()"), True)
finally:
    cfgmod.set_data_root(None)
    cfgmod.set_config_path(None)
    shutil.rmtree(tmp, ignore_errors=True)

# ---- 8. `--version`（打包后排查版本用）----
out = subprocess.run([sys.executable, "run.py", "--version"], capture_output=True, text=True,
                     encoding="utf-8", cwd=str(Path(__file__).resolve().parent.parent))
check("run.py --version 打印版本号", out.stdout.strip(), __version__)

print()
if FAILED:
    print(f"失败 {len(FAILED)} 项：{FAILED}")
    sys.exit(1)
print("路径解析用例全部通过")
