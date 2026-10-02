import os
import sys

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import lan_auth, ollama_boot, ollama_client
from .. import __version__
from ..config import get_config
from ..database import (
    get_db,
    now,
    read_settings,
    write_disable_thinking,
    write_lan_enabled,
    write_lan_token,
)
from ..limits import LIMITS
from ..net import is_loopback
from ..prompts import DEFAULT_SETTINGS, FIELDS
from ..schemas import LanClaimIn, SettingsIn

router = APIRouter(prefix="/api")


@router.get("/version")
def get_version():
    """应用版本（单一来源在 `app/__init__.py`）。界面在配置面板底部显示它。

    `packaged` 说明这次跑的是打包后的 exe 还是源码——排查"数据到底写到哪去了"时要看它。
    """
    return {"version": __version__, "packaged": bool(getattr(sys, "frozen", False))}


@router.get("/limits")
def get_limits():
    """各输入框的字数上限。前端据此设 maxlength 并显示右下角实时计数。"""
    return LIMITS


@router.get("/gen-settings")
def get_gen_settings_form():
    """三模式生成要求表单定义与默认值，供前端动态渲染。"""
    return {"fields": FIELDS, "defaults": DEFAULT_SETTINGS}


@router.get("/settings")
def get_settings():
    return read_settings()


@router.put("/settings")
async def update_settings(body: SettingsIn, request: Request, db=Depends(get_db)):
    if (body.model is None and body.memory_model is None
            and body.disable_thinking is None and body.lan_enabled is None):
        raise HTTPException(400, "没有需要更新的字段")
    # "推送局域网"只允许在本机改：手机端（哪怕已经被放行）不该能开关这道闸门（见 §8.3）
    if body.lan_enabled is not None and not is_loopback(request.client):
        raise HTTPException(403, "只有这台电脑上能改「推送局域网」")
    # 只在真要改模型名时才去查已安装列表：list_models() 会逐模型查能力，
    # 单纯切"思考模式"不该白跑这一圈
    if body.model is not None or body.memory_model is not None:
        try:
            installed = {m["name"] for m in await ollama_client.list_models()}
        except httpx.HTTPError:
            raise HTTPException(502, "无法连接 Ollama，请确认服务已启动")
        for value in (body.model, body.memory_model):
            if value and value not in installed:
                raise HTTPException(400, f"模型未安装：{value}")
    sets, vals = [], []
    if body.model is not None:
        sets.append("model=?")
        vals.append(body.model)
    if body.memory_model is not None:
        sets.append("memory_model=?")
        vals.append(body.memory_model)
    if sets:
        sets.append("updated_at=?")
        vals.append(now())
        vals.append(1)
        db.execute(f"UPDATE app_settings SET {', '.join(sets)} WHERE id=?", vals)
        db.commit()
    if body.disable_thinking is not None:
        write_disable_thinking(body.disable_thinking)
    if body.lan_enabled is not None:
        write_lan_enabled(body.lan_enabled)
        # 打开时若还没有访问码就补一个（已经有了就留着，重新开关不该把手机踢下线）；
        # 关掉时清空：那道闸门一关，已经发出去的 Cookie 也一并作废（见 §8.3）
        if body.lan_enabled and not read_settings()["lan_token"]:
            write_lan_token(lan_auth.new_code())
        elif not body.lan_enabled:
            write_lan_token("")
    return read_settings()


@router.post("/lan/claim")
def claim_lan_access(body: LanClaimIn, request: Request):
    """用访问码换一张 Cookie（手机端首次进来、或访问码换过之后）。

    它是闸门里**唯一**不需要码就能到达的接口：没码的人正是靠它进来。所以校验与限速都在这里：
    码错记一次失败，同一来源一分钟内错够 `lan_auth.FAIL_LIMIT` 次就 429。
    """
    ip = request.client.host if request.client else ""
    if lan_auth.too_many_fails(ip):
        raise HTTPException(429, "试错次数太多，请等一分钟再试")
    stored = read_settings()["lan_token"]
    if not lan_auth.matches(stored, body.code):
        lan_auth.note_fail(ip)
        raise HTTPException(401, "访问码不对")
    lan_auth.clear_fails(ip)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        lan_auth.COOKIE_NAME, stored,
        max_age=lan_auth.COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )
    return resp


@router.post("/lan/regenerate")
def regenerate_lan_token(request: Request):
    """换一个访问码：旧设备要重新扫码。只有本机能做（和开关同一条理由）。"""
    if not is_loopback(request.client):
        raise HTTPException(403, "只有这台电脑上能换访问码")
    return {"lan_token": write_lan_token(lan_auth.new_code())}


@router.get("/models")
async def get_models():
    try:
        return await ollama_client.list_models()
    except httpx.HTTPError:
        raise HTTPException(502, "无法连接 Ollama，请确认服务已启动")


@router.post("/ollama/ensure")
def ensure_ollama_now():
    """让 Ollama 现在就可用（界面上那个「重试」键调它）。

    为什么需要这个：自启只在 `run.py` 启动时做一次。如果后端本来就在跑（端口被占、run.py 直接
    退出），而 Ollama 后来挂了/被关了，那就没人再去拉它——此时界面只能靠重启应用，太别扭。
    这里按需再跑一遍同一套确保逻辑（短超时：这是用户点了一下在等），并把原因捎回去。
    """
    cfg = get_config()
    base_url = cfg["ollama"]["base_url"]
    status = ollama_boot.ensure_ollama(
        base_url,
        cfg["ollama"].get("auto_start", True),
        timeout=20.0,
        log_path=os.path.join(cfg["data_dir"], "ollama-serve.log"),
    )
    return {"status": status, "text": ollama_boot.report(status, base_url)}
