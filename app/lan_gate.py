"""局域网闸门的两半（见 DEVELOPMENT §8.3）。

判据按顺序：

1. **Host 头必须是本机自己的地址或名字**。这一条与开关无关，**本机来源也要过**：
   恶意网页可以把自己的域名解析到 `127.0.0.1`，那样浏览器就当它是同源——校验 Host 才挡得住，
   而它在"来源是回环"这条判据下恰恰是被放行的。
2. 本机来源（回环）直接放行：电脑端那份界面不受影响。
3. 局域网来源：开关关着 → 403；开着 → 必须带对访问码（URL 的 `?k=` / `X-Lan-Token` / Cookie）。

为什么放在应用层而不是"改监听地址 + 重启"：桌面端的开关要能**立即**生效，而重启后端会打断
正在进行的生成。监听地址仍由 `config.yaml server.host` 决定。

拆成 `before()` / `after()` 两半是为了可测：用例装一道与 `main.py` 同款的中间件即可，
不必起整个应用（`create_app()` 会去碰真实的 `data/`）。
"""
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import database, lan_auth
from .net import host_ok, is_loopback

CLOSED_MESSAGE = "电脑端当前没有开启局域网访问（在电脑端的「配置」里打开）"
CODE_MESSAGE = "需要访问码：扫电脑端的「配置」里的二维码，或把那里显示的地址整条打开"
CLAIM_PATH = "/api/lan/claim"


def _html(title: str, body: str, status: int = 403) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title>"
        "<div style='font-family:system-ui;padding:40px;line-height:1.8;max-width:34em'>"
        f"<h2>{title}</h2>{body}</div>",
        status_code=status,
    )


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _closed(request: Request):
    """开关关着。接口回 JSON（前端好显示），页面回一段人话。"""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": CLOSED_MESSAGE}, status_code=403)
    return _html(
        "未开启局域网访问",
        f"<p>{CLOSED_MESSAGE}</p>"
        "<p style='color:#888'>如果你就是这台电脑的使用者，请在本机浏览器里打开 "
        "http://127.0.0.1:17800 并点击顶栏的「配置」。</p>",
    )


def _code_page(status: int) -> HTMLResponse:
    """没带（或带错）访问码时的页面：只有一个输入框，不加载任何外部资源。

    页面本身就是脚本里的一段：`fetch` 提交到领码接口，成功后重载进应用。
    """
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>输入访问码</title>"
        "<style>"
        "body{font-family:system-ui;padding:32px;line-height:1.7;background:#f6f7fb;color:#222}"
        "h2{margin:0 0 8px}p{color:#666;margin:0 0 16px;font-size:14px}"
        "input{font:inherit;font-size:20px;letter-spacing:2px;text-transform:uppercase;"
        "width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #ccd;border-radius:10px}"
        "button{font:inherit;margin-top:14px;width:100%;padding:11px;border:0;border-radius:10px;"
        "background:#4c6ef5;color:#fff}"
        "#msg{color:#c33;min-height:1.4em;margin-top:12px}"
        "</style>"
        "<h2>输入访问码</h2>"
        f"<p>{CODE_MESSAGE}</p>"
        "<input id='code' autocomplete='off' autocapitalize='characters' "
        "autocorrect='off' spellcheck='false' placeholder='例如 K7F2-9QX3'>"
        "<button id='go'>进入</button>"
        "<p id='msg'></p>"
        "<script>"
        "var i=document.getElementById('code'),m=document.getElementById('msg');"
        "function go(){"
        "fetch('/api/lan/claim',{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({code:i.value})}).then(function(r){"
        "if(r.ok){location.replace('/');return null;}"
        "return r.json().catch(function(){return {};}).then(function(d){"
        "m.textContent=d.detail||'访问码不对';});"
        "}).catch(function(){m.textContent='连不上电脑端，检查是否还在同一个网络';});}"
        "document.getElementById('go').onclick=go;"
        "i.addEventListener('keydown',function(e){if(e.key==='Enter')go();});"
        "i.focus();"
        "</script>",
        status_code=status,
    )


def _need_code(request: Request):
    """开关开着，但没带对访问码。"""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": CODE_MESSAGE}, status_code=401)
    if lan_auth.too_many_fails(_ip(request)):
        return _html("试错次数太多", "<p>等一分钟再试，或回电脑端重新扫一次二维码。</p>", status=429)
    return _code_page(401)


def _bad_host(request: Request):
    message = ("这个地址被挡住了：请求的 Host 不是本机自己的地址或名字（防 DNS rebinding）。"
               "请改用局域网 IP 或 localhost 打开。")
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=403)
    return _html("地址不被接受", f"<p>{message}</p>")


def _given_code(request: Request) -> str:
    """这次请求带的访问码：URL 的 `?k=`（二维码用的就是它）> 请求头 > Cookie。"""
    return (
        request.query_params.get("k")
        or request.headers.get("x-lan-token", "")
        or request.cookies.get(lan_auth.COOKIE_NAME, "")
    )


def _set_code_cookie(resp, token: str) -> None:
    # 明文 HTTP 下没有 secure（手机走的是 http://<IP>），HttpOnly 挡住页面脚本读它
    resp.set_cookie(
        lan_auth.COOKIE_NAME, token,
        max_age=lan_auth.COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )


def before(request: Request):
    """闸门第一半：不放行就返回该回的响应；放行返回 None，由调用方继续处理请求。"""
    if not host_ok(request.headers.get("host", "")):
        return _bad_host(request)
    if is_loopback(request.client):
        return None
    if not database.lan_enabled():
        return _closed(request)
    if request.url.path == CLAIM_PATH:
        return None                       # 还没码的人正是靠它进来（校验在路由里）
    stored = database.read_settings()["lan_token"]
    if lan_auth.matches(stored, _given_code(request)):
        lan_auth.clear_fails(_ip(request))
        if request.query_params.get("k") and not request.url.path.startswith("/api/"):
            # 页面带着码进来：换成 Cookie，并把 URL 里的码擦掉（免得留在浏览器历史/截图里）
            clean = request.url.remove_query_params("k")
            resp = RedirectResponse(str(clean), status_code=302)
            resp.headers["Cache-Control"] = "no-store"
            _set_code_cookie(resp, stored)
            return resp
        return None
    return _need_code(request)


def after(request: Request, response):
    """闸门第二半：这次请求是用 `?k=` / 请求头带来的码时，顺手写进 Cookie。"""
    if is_loopback(request.client):
        return response
    given = request.query_params.get("k") or request.headers.get("x-lan-token", "")
    if given:
        stored = database.read_settings()["lan_token"]
        if lan_auth.matches(stored, given):
            _set_code_cookie(response, stored)
    return response
