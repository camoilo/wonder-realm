import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import ollama_client
from .config import get_config
from .database import init_db, read_settings
from .lan_gate import after as gate_after
from .lan_gate import before as gate_before
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
log = logging.getLogger("wonder_realm")


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

    app = FastAPI(title="Wonder Realm（奇想界域）", lifespan=lifespan)

    @app.middleware("http")
    async def no_store(request, call_next):
        # 本地单用户应用：禁用 HTTP 缓存，避免改版后浏览器沿用旧资源
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.middleware("http")
    async def lan_gate(request, call_next):
        """局域网闸门：判据都在 `app/lan_gate.py`（Host 校验 / 开关 / 访问码，见 §8.3）。

        放在应用层而不是"改监听地址 + 重启"：桌面端的配置按钮要能**立即**开关，
        而重启后端会打断正在进行的生成。监听地址仍由 `config.yaml server.host` 决定
        （默认 0.0.0.0）：端口对外开放，但放不放行由这道闸门说了算。
        """
        blocked = gate_before(request)
        if blocked is not None:
            return blocked
        return gate_after(request, await call_next(request))

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
