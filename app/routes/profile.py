"""用户本人的设定（右侧面板的"我的设定"）。

`user_profile` 表里 **id=1 是当前设定**、**id>1 是保存下来的预设**（见 DEVELOPMENT §2.3 我的设定）：
同一个主体一行数据，复用同一张表即可，既不用为预设另开一张，也不必改表结构。
姓名/身份/外观会注入聊天与沉浸两种模式的提示词，头像是数据 URL，跟着数据库一起备份；
导演模式不使用它（见 DEVELOPMENT §2.3 我的设定）。
"""
from fastapi import APIRouter, HTTPException

from ..database import (
    add_preset,
    delete_preset,
    list_presets,
    read_profile,
    read_profile_by_id,
    update_preset,
    write_profile,
)
from ..schemas import ProfileIn

router = APIRouter(prefix="/api")


@router.get("/profile")
def get_profile():
    return read_profile()


@router.put("/profile")
def update_profile(body: ProfileIn):
    # 表单整体提交，所以整体覆盖；空串就是"这一项不填"
    return write_profile(
        {
            "name": body.name.strip(),
            "identity": body.identity.strip(),
            "appearance": body.appearance.strip(),
            "avatar": body.avatar,
        }
    )


@router.get("/profile/presets")
def get_presets():
    """已保存的预设（新的在前）。每项就是一份完整设定，含头像。"""
    return list_presets()


@router.post("/profile/presets")
def create_preset(body: ProfileIn):
    """把当前表单存成一条预设。名字不能为空——它就是下拉里显示的那一项。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "先给「我的设定」填个名字，才能存为预设")
    return add_preset(
        {
            "name": name,
            "identity": body.identity.strip(),
            "appearance": body.appearance.strip(),
            "avatar": body.avatar,
        }
    )


@router.put("/profile/presets/{preset_id}")
def update_preset_route(preset_id: int, body: ProfileIn):
    """用当前表单覆盖一条已有预设（面板上的「保存预设」）。

    预设是"另存的一份设定"，与当前配置（id=1）互不影响：这里只改 id>1 那一行，
    所以覆盖预设不会让"当前使用的设定"跟着变。
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "先给「我的设定」填个名字，才能保存预设")
    saved = update_preset(
        preset_id,
        {
            "name": name,
            "identity": body.identity.strip(),
            "appearance": body.appearance.strip(),
            "avatar": body.avatar,
        },
    )
    if saved is None:
        raise HTTPException(404, "预设不存在")
    return saved


@router.delete("/profile/presets/{preset_id}")
def remove_preset(preset_id: int):
    # id<=1 是"当前设定"本身，不是预设，删了等于把当前设定清掉
    if preset_id <= 1 or read_profile_by_id(preset_id) is None:
        raise HTTPException(404, "预设不存在")
    delete_preset(preset_id)
    return {"ok": True}
