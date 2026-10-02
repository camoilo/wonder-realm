import logging
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from app import backup, config, database
from app import ollama_boot
from app import __version__
from app.config import get_config

log = logging.getLogger("wonder_realm")


def port_in_use(host: str, port: int) -> bool:
    """端口已有监听：说明应用多半已经在跑，不必重复启动。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def open_browser_later(url: str, delay: float = 1.5) -> None:
    """延后打开浏览器，给 uvicorn 留出绑定端口的时间。"""
    timer = threading.Timer(delay, webbrowser.open, args=(url,))
    timer.daemon = True  # 不阻塞进程退出
    timer.start()


def startup_backup(cfg: dict) -> Path | None:
    """每次启动都留一份备份；开关关掉或库还不存在时跳过（一天多份是正常的）。"""
    opts = cfg.get("backup") or {}
    if not opts.get("on_startup", True):
        return None
    backup_dir = opts.get("dir")
    if not backup_dir:
        return None
    # 本函数在 create_app()/init_db() 之前被调用，那时 DB_PATH 还是空的，所以由 current_db_file()
    # 去推路径（已经初始化过就以 DB_PATH 为准，见它的说明）
    return backup.make_backup(
        database.current_db_file(cfg["data_dir"]), backup_dir, opts.get("days", backup.DEFAULT_DAYS)
    )


def _arg_value(args: list[str], name: str) -> str | None:
    """取 `--name value` 或 `--name=value` 的值；没给返回 None。

    手写而不是上 argparse：这里只有三个开关，参数少、要能容忍未知参数（壳会透传别的开关）。
    """
    for i, a in enumerate(args):
        if a == name:
            return args[i + 1] if i + 1 < len(args) else None
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # --no-browser：给桌面端（Electron）用——它自己开窗口，不要再弹一个系统浏览器。
    # --lan / --no-lan：设置"推送局域网"开关（写进库，立即生效，不用改 config 再重启）。
    # 桌面端有顶栏「配置」按钮，这两个参数是给不带桌面端的命令行用户留的路子（见 §8.3）
    # --data-dir / --config：把可变数据（config.yaml / data / backups）指到别处——打包版由壳
    #   指到用户数据目录（见 §8.4）；不指定就与程序同目录（绿色版）
    args = sys.argv[1:]
    if "--version" in args:
        print(__version__)
        sys.exit(0)
    no_browser = "--no-browser" in args
    # **先定路径再读配置**：get_config() 是懒加载的，这里定完它才第一次算路径
    config.set_config_path(_arg_value(args, "--config"))
    config.set_data_root(_arg_value(args, "--data-dir"))

    cfg = get_config()
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]
    # 监听地址可能是 0.0.0.0，浏览器需要能访问的具体地址
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browser_host}:{port}"
    # 打印路径：装成 exe 后"数据到底写到哪去了"是最常要确认的一件事
    print(f"数据目录：{cfg['data_dir']}（配置：{config.config_path()}）")

    # 无论这次是真的起服务还是"已经在跑"，都先留一份备份。
    # 放在 uvicorn.run() 之前：留下的是上次运行结束时的库，而不是本次启动刚建过表的。
    startup_backup(cfg)

    # init_db 是幂等的（建表/补列/补单行），先建好再改设置；之后 uvicorn 里那次 create_app
    # 再跑一遍不会有副作用
    database.init_db(
        cfg["data_dir"], cfg["ollama"]["model"], cfg["memory"].get("model", ""),
        cfg.get("server", {}).get("lan", False),
    )
    # **每次启动都把"推送局域网"关掉**：局域网是一道安全闸门，上次开着不代表
    # 这次还要开着（换到公共 WiFi 就麻烦了）。想开就在界面里点，或用 `--lan` 显式启动。
    database.write_lan_enabled("--lan" in args)
    if "--lan" in args:
        print("推送局域网：已开启（--lan）")
    elif "--no-lan" in args:
        print("推送局域网：已关闭（--no-lan）")
    else:
        print("推送局域网：已关闭（默认；要用就在界面里打开，或加 --lan 启动）")

    if port_in_use(browser_host, port):
        print(f"端口 {port} 已在监听，服务应该已在运行：{url}")
        if not no_browser:
            webbrowser.open(url)
    else:
        print(f"启动中：{url}" + ("" if no_browser else "（稍后自动打开浏览器）"))
        # 先把 Ollama 弄起来再开浏览器：界面一加载就要拉模型列表，
        # 不先等它的话首屏会闪一句"无法连接 Ollama"（见 DEVELOPMENT §3.4）
        status = ollama_boot.ensure_ollama(
            cfg["ollama"]["base_url"],
            cfg["ollama"].get("auto_start", True),
            # ollama serve 的输出落这里：起不来时原因就在它最后几行（端口被占之类）
            log_path=os.path.join(cfg["data_dir"], "ollama-serve.log"),
        )
        print(ollama_boot.report(status, cfg["ollama"]["base_url"]))
        if not no_browser:
            open_browser_later(url)
        # **直接传 ASGI 对象，不写导入字符串**：`uvicorn.run("app.main:app")` 在 PyInstaller
        # 冻结后找不到模块（导入字符串是运行时才解析的，打包器静态分析看不见）。
        # 这句必须留在这里（而不是模块顶部）：`create_app()` 会读配置，而数据根要先由
        # 上面的参数定下来（见 app/config.py 的懒加载）。
        from app.main import app as asgi_app
        uvicorn.run(asgi_app, host=host, port=port)
