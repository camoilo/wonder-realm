import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from .. import ollama_client
from ..database import (
    get_db,
    now,
    read_settings,
    write_disable_thinking,
    write_lan_enabled,
)
from ..limits import LIMITS
from ..net import is_loopback
from ..prompts import DEFAULT_SETTINGS, FIELDS
from ..schemas import SettingsIn

router = APIRouter(prefix="/api")


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
    return read_settings()


@router.get("/models")
async def get_models():
    try:
        return await ollama_client.list_models()
    except httpx.HTTPError:
        raise HTTPException(502, "无法连接 Ollama，请确认服务已启动")
