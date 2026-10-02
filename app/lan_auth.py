"""局域网访问码：非本机来源要带对码才放行（见 DEVELOPMENT §8.3）。

为什么不是账号密码：这是本机单用户应用，目标体验是"手机扫一下就进来"。所以访问码是
**一把钥匙**——只存在库里、只在电脑端的「配置」面板显示（二维码里也带着它），关掉闸门即清空，
换一个就作废旧设备。

手工输入要宽容：忽略大小写、空格与连字符（`K7F2-9QX3` 与 `k7f29qx3` 等价），
字母表里也去掉了 0/O/1/I/L 这几个最容易认错的字符。

试错按来源限速：明文 HTTP 下码是能被抓包看到的，限速挡的是"在门口一个个试"。
"""
import hmac
import secrets
import time

# 去掉了 0 O 1 I L：手输时最容易认错的几个（少 5 个字符，25 选 8 仍是 1.5e11 量级）
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LEN = 8
# 存进 Cookie 的名字，手机首次带码进来后就不必再带
COOKIE_NAME = "wr_lan"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 天；换码/关闸门后这张 Cookie 立刻失效
# 同一来源在这个窗口里最多试错几次
FAIL_LIMIT = 5
FAIL_WINDOW = 60.0

_fails: dict[str, list[float]] = {}


def new_code() -> str:
    """新的访问码（只在这里生成，见 `database.write_lan_token`）。"""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def normalize(text: str) -> str:
    """手输的宽容处理：统一大写、去掉空格与连字符之类的分隔符。"""
    return "".join(c for c in (text or "").upper() if c.isalnum())


def matches(stored: str, given: str) -> bool:
    """给出来的码对不对。等时比较；库里没码时一律不放行（关着的时候本来也到不了这里）。"""
    stored, given = normalize(stored), normalize(given)
    return bool(stored) and hmac.compare_digest(stored, given)


def _recent(ip: str) -> list[float]:
    hits = [t for t in _fails.get(ip, []) if time.monotonic() - t < FAIL_WINDOW]
    _fails[ip] = hits
    return hits


def too_many_fails(ip: str) -> bool:
    return len(_recent(ip)) >= FAIL_LIMIT


def note_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.monotonic())


def clear_fails(ip: str) -> None:
    _fails.pop(ip, None)
