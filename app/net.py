"""来源地址判定。

单独一个小模块是为了避开循环 import：局域网闸门在 `app/main.py`（它是 create_app 里注册的
中间件），而"只有本机能改推送开关"在 `app/routes/settings.py`——两边都要判回环，谁 import 谁
都会成环（main 要 import 路由）。见 DEVELOPMENT §8.3。
"""
import socket
import time

# 本机来源：回环地址。uvicorn 在双栈下可能给出 IPv4 映射形式（::ffff:127.0.0.1）
LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}

# 本机自己的名字/地址，10 秒缓存一次：换 WiFi、插网线都会变，但不该每来一个请求就查一次 DNS
_CACHE: dict = {"at": 0.0, "hosts": frozenset()}
_CACHE_TTL = 10.0


def is_loopback(client) -> bool:
    """请求是否来自本机（`request.client`）。client 为 None 时按"不是本机"处理。"""
    return bool(client) and client.host in LOOPBACK


def local_hosts() -> frozenset[str]:
    """本机自己的名字与地址：只有它们出现在 Host 头里，才算"确实是在访问这台机器"。

    取不到就退回只有回环那一组（调用方据此仍能挡住陌生域名）。
    """
    now = time.monotonic()
    if now - _CACHE["at"] < _CACHE_TTL and _CACHE["hosts"]:
        return _CACHE["hosts"]
    hosts = set(LOOPBACK)
    try:
        name = socket.gethostname().lower()
        hosts.add(name)
        hosts.add(f"{name}.local")      # 有些环境用 mDNS 名字访问
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            hosts.add(str(info[4][0]).lower())
    except OSError:
        pass
    _CACHE.update(at=now, hosts=frozenset(hosts))
    return _CACHE["hosts"]


def host_ok(host_header: str) -> bool:
    """Host 头是不是"本机"（见 DEVELOPMENT §8.3 的安全一节）。

    防的是 DNS rebinding：恶意网页把自己的域名解析到 127.0.0.1 / 局域网 IP，浏览器就当它与
    本应用同源，于是"来源是回环"这条判据会放它进来。Host 头是页面改不了的那个字段，校验它就够了。

    只认本机地址/名字，不认域名——所以给这台机器配了 DDNS 域名、或经反向代理访问的场景会被挡下，
    那种情况请用局域网 IP 或 localhost。
    """
    name = (host_header or "").strip().lower()
    if not name:
        return False
    if name.startswith("["):                     # IPv6 字面量：[::1]:17800
        end = name.find("]")
        host = name[1:end] if end > 0 else name
    elif name.count(":") == 1:                   # IPv4 / 名字 + 端口
        host = name.rsplit(":", 1)[0]
    else:                                        # 裸 IPv6（::1）
        host = name
    return host in local_hosts()
