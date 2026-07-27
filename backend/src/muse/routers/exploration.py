"""探索路由（AR2：router 仅校验入参 + 分发，业务在 exploration_service）。

探索挂在 project 层级下：POST /api/projects/{project_id}/explore（get-or-create 语义）。
依赖 CurrentUser 自动完成 access token 校验并取当前 User；未登录/token 失效在依赖内 401。
所有操作绑定 current_user.id 实现租户隔离；越权/不存在同码 404（业务在 service）。
"""

import uuid

from fastapi import APIRouter

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.exploration import ExplorationSessionResponse
from muse.services import exploration_service

router = APIRouter(prefix="/api/projects", tags=["exploration"])


@router.post("/{project_id}/explore", response_model=ExplorationSessionResponse)
async def enter_exploration(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> ExplorationSessionResponse:
    # get-or-create 幂等入口，返 200（而非恒新建的 201，陷阱⑦）：重复进入/刷新返同一会话。
    # 无 body（AC2）——mode 恒取 project.mode，客户端不传；project_id 非法 UUID 由 FastAPI 自动 422。
    # 越权/不存在在 service 统一 404（陷阱①）。
    exploration = await exploration_service.enter_exploration(
        session, user_id=current_user.id, project_id=project_id
    )
    return ExplorationSessionResponse.model_validate(exploration)
