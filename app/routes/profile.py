"""用户本人的设定（右侧面板的"我的设定"）。

全局单行，与角色/会话无关：姓名、身份、外观会注入角色两模式的提示词，
头像是数据 URL，跟着数据库一起备份。自由情境模式不使用它（见 10.35）。
"""
from fastapi import APIRouter

from ..database import read_profile, write_profile
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
