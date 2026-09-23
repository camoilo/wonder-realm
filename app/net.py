"""来源地址判定。

单独一个小模块是为了避开循环 import：局域网闸门在 `app/main.py`（它是 create_app 里注册的
中间件），而"只有本机能改推送开关"在 `app/routes/settings.py`——两边都要判回环，谁 import 谁
都会成环（main 要 import 路由）。见 DEVELOPMENT §8.3。
"""

# 本机来源：回环地址。uvicorn 在双栈下可能给出 IPv4 映射形式（::ffff:127.0.0.1）
LOOPBACK = {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def is_loopback(client) -> bool:
    """请求是否来自本机（`request.client`）。client 为 None 时按"不是本机"处理。"""
    return bool(client) and client.host in LOOPBACK
