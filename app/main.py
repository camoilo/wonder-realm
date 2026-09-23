import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ollama_client
from .config import get_config
from .database import init_db, lan_enabled, read_settings
from .net import is_loopback
from .routes import (
    characters,
    chat,
    memories,
    messages,
    profile,
    sessions,
    settings,
    world,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ollama_agent")


def _lan_forbidden(path: str):
    """局域网来源被闸门拦下时的回应。

    接口请求回 JSON（前端好显示），页面请求回一段人话——手机浏览器直接打开时，
    看到"电脑端没有开启局域网访问"比一串 403 JSON 明白得多。
    """
    message = "电脑端当前没有开启局域网访问（在电脑端的「配置」里打开）"
    if path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=403)
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        "<title>未开启局域网访问</title>"
        "<div style='font-family:system-ui;padding:40px;line-height:1.8'>"
        "<h2>未开启局域网访问</h2>"
        f"<p>{message}</p>"
        "<p style='color:#888'>如果你就是这台电脑的使用者，请在本机浏览器里打开 "
        "http://127.0.0.1:17800 并点击顶栏的「配置」。</p></div>",
        status_code=403,
    )


def create_app():
    cfg = get_config()
    init_db(
        cfg["data_dir"],
        cfg["ollama"]["model"],
        cfg["memory"].get("model", ""),
        cfg.get("server", {}).get("lan", False),
    )

    @asynccontextmanager
    async def lifespan(_app):
        try:
            models = {m["name"] for m in await ollama_client.list_models()}
        except httpx.HTTPError:
            log.warning("Ollama 服务不可达：%s", cfg["ollama"]["base_url"])
            yield
            return
        current = read_settings()["model"]
        if not current:
            # 首次使用（或用户还没选过）：不预选任何模型，等他在顶栏选
            log.info("还没有选择模型，请在顶栏选择一个已安装的模型")
        elif current in models:
            log.info("当前模型：%s", current)
        else:
            log.warning("模型 %s 未安装，请在界面右上角切换已安装的模型", current)
        yield

    app = FastAPI(title="多模式对话机器人", lifespan=lifespan)

    @app.middleware("http")
    async def no_store(request, call_next):
        # 本地单用户应用：禁用 HTTP 缓存，避免改版后浏览器沿用旧资源
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.middleware("http")
    async def lan_gate(request, call_next):
        """局域网闸门：开关关掉时非本机来源一律 403，本机永远放行（见 §8.3）。

        为什么放在应用层而不是"改监听地址 + 重启"：桌面端的配置按钮要能**立即**开关，
        而重启后端会打断正在进行的生成。监听地址仍由 `config.yaml server.host` 决定
        （默认 0.0.0.0）：端口对外开放，但放不放行由这道闸门说了算。
        """
        if not lan_enabled() and not is_loopback(request.client):
            return _lan_forbidden(request.url.path)
        return await call_next(request)

    app.include_router(characters.router)
    app.include_router(settings.router)
    app.include_router(profile.router)
    app.include_router(world.router)
    app.include_router(sessions.router)
    app.include_router(messages.router)
    app.include_router(memories.router)
    app.include_router(chat.router)
    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
