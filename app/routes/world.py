"""世界设定（右侧面板的"世界设定"）：**全局一份**，三种模式都注入提示词。

四项全可选：全空就等于没有世界设定，提示词里连标题都不会出现（同 `_user_block` 的做法）。
**世界名称不进提示词**——它只用来让自己在界面上认出这一份设定（用户明确要求）；
描述 / 规则 / 词库进提示词，注入位置在角色设定**之前**：世界是最外层的框架。
"""
from fastapi import APIRouter

from ..database import read_world, write_world
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
