"""世界设定（右侧面板的"世界设定"）：**和"我的设定"同一套约定** —— `worlds` 表里
**id=1 是当前世界**、**id>1 是保存下来的世界预设**（见 DEVELOPMENT §2.4 世界设定）。

四项全可选：全空就等于没有世界设定，提示词里连标题都不会出现（同 `_user_block` 的做法）。
**世界名称不进提示词**——它只用来让自己在界面上认出这一份设定；
描述 / 规则 / 词库进提示词，注入位置在角色设定**之前**：世界是最外层的框架。

用哪份世界由绑定决定：聊天与沉浸两种模式跟着**角色**（`characters.world_id`），
导演模式跟着**会话**（`sessions.world_id`）——所以导演会话各有各的世界。
"""
from fastapi import APIRouter, HTTPException

from ..database import (
    add_world_preset,
    delete_world_preset,
    list_world_presets,
    read_world,
    read_world_by_id,
    update_world_preset,
    write_world,
)
from ..schemas import WorldIn

router = APIRouter(prefix="/api")


@router.get("/world")
def get_world():
    return read_world()


@router.put("/world")
def update_world(body: WorldIn):
    """表单整体提交，所以整体覆盖；空串就是"这一项不填"。

    文本 strip 与"丢掉名词为空的行"在 `database.write_world` 里做——读写是一对形状规则，
    放一处才不会出现"写进去的行读出来是坏的"。
    """
    return write_world(body.model_dump())


@router.get("/world/presets")
def get_world_presets():
    """已保存的世界预设（新的在前）。每项含整份世界设定（词库也在）+ 绑定了它的角色。

    `characters` 只用来显示"这条世界预设给了哪些角色"；改绑定在角色那侧
    （`PUT /api/characters/{id}` 带 world_id），导演会话则存在 `sessions.world_id`。
    """
    return list_world_presets()


@router.post("/world/presets")
def create_world_preset(body: WorldIn):
    """把当前世界存成一条新预设。名字不能为空——列表里就靠它辨认。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "先给世界设定填个名字，才能存为预设")
    return add_world_preset(body.model_dump() | {"name": name})


@router.put("/world/presets/{preset_id}")
def update_world_preset_route(preset_id: int, body: WorldIn):
    """覆盖一条世界预设（弹窗里的「保存」）。只动 id>1 那一行，当前世界不受影响。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "先给世界设定填个名字，才能保存预设")
    saved = update_world_preset(preset_id, body.model_dump() | {"name": name})
    if saved is None:
        raise HTTPException(404, "世界预设不存在")
    return saved


@router.delete("/world/presets/{preset_id}")
def remove_world_preset(preset_id: int):
    # id<=1 是"当前世界"本身，不是预设
    if preset_id <= 1 or read_world_by_id(preset_id) is None:
        raise HTTPException(404, "世界预设不存在")
    delete_world_preset(preset_id)
    return {"ok": True}
