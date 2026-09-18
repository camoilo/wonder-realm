import socket
import threading
import webbrowser

import uvicorn

from app.config import get_config


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


if __name__ == "__main__":
    cfg = get_config()
    host = cfg["server"]["host"]
    port = cfg["server"]["port"]
    # 监听地址可能是 0.0.0.0，浏览器需要能访问的具体地址
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browser_host}:{port}"

    if port_in_use(browser_host, port):
        print(f"端口 {port} 已在监听，服务应该已在运行，直接打开浏览器：{url}")
        webbrowser.open(url)
    else:
        print(f"启动中，稍后自动打开浏览器：{url}")
        open_browser_later(url)
        uvicorn.run("app.main:app", host=host, port=port)
