import httpx
from fastapi import APIRouter, Depends, HTTPException

from .. import ollama_client
from ..database import get_db, now, read_settings
from ..prompts import DEFAULT_SETTINGS, FIELDS
from ..schemas import SettingsIn

router = APIRouter(prefix="/api")


@router.get("/gen-settings")
def get_gen_settings_form():
    """三模式生成要求表单定义与默认值，供前端动态渲染。"""
    return {"fields": FIELDS, "defaults": DEFAULT_SETTINGS}


@router.get("/settings")
def get_settings():
    return read_settings()


@router.put("/settings")
async def update_settings(body: SettingsIn, db=Depends(get_db)):
    if body.model is None and body.memory_model is None:
        raise HTTPException(400, "没有需要更新的字段")
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
    sets.append("updated_at=?")
    vals.append(now())
    vals.append(1)
    db.execute(f"UPDATE app_settings SET {', '.join(sets)} WHERE id=?", vals)
    db.commit()
    return read_settings()


@router.get("/models")
async def get_models():
    try:
        return await ollama_client.list_models()
    except httpx.HTTPError:
        raise HTTPException(502, "无法连接 Ollama，请确认服务已启动")
