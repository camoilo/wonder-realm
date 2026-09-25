import logging
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from app import backup, database
from app import ollama_boot
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
    # 本函数在 create_app()/init_db() 之前被调用，那时 DB_PATH 还是空的，所以从配置推路径。
    # 若已经初始化过（例如测试里先建了库，或将来有别的调用点），以 DB_PATH 为准——
    # 它才是应用真正在写的那个文件；两者若不一致，从配置推出来的可能是另一个库。
    db_path = database.DB_PATH or database.db_file(cfg["data_dir"])
    return backup.make_backup(db_path, backup_dir, opts.get("days", 14))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # --no-browser：给桌面端（Electron）用——它自己开窗口，不要再弹一个系统浏览器。
    # --lan / --no-lan：设置"推送局域网"开关（写进库，立即生效，不用改 config 再重启）。
    # 桌面端有顶栏「配置」按钮，这两个参数是给不带桌面端的命令行用户留的路子（见 §8.3）
    args = sys.argv[1:]
    no_browser = "--no-browser" in args
    cfg = get_config()
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]
    # 监听地址可能是 0.0.0.0，浏览器需要能访问的具体地址
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browser_host}:{port}"

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
        uvicorn.run("app.main:app", host=host, port=port)
