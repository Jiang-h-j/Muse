"""通读视图路由（Story 6.1，AR2：router 仅校验入参 + 分发，业务在 chapter_service）。

通读视图挂在 project 层级（prefix /api/projects/{project_id}/readthrough）：
- GET /：取**完整通读聚合 payload**——所有已定稿章节（按 chapter_number 升序），
  每章后端已按 READTHROUGH_PER_PAGE=6 切好 pages；附带 hasUnfinalized 标记告诉前端
  「还有未定稿章」（不阻塞阅读，**陷阱⑪**）。

**非流式**（同 GET stage-plan / GET archive）：一次性 JSON 响应
（`ReadthroughResponse`），不做 SSE；通读不走任务编排。依赖 `CurrentUser` 完成
access token 校验并取当前 User；操作绑定 current_user.id 实现租户隔离；
越权/不存在 project 由 service 抛 404 二义合一（NFR3，不泄露作品存在性）。
"""

import uuid

from fastapi import APIRouter

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.readthrough import ReadthroughResponse
from muse.services import chapter_service

router = APIRouter(
    prefix="/api/projects/{project_id}/readthrough",
    tags=["readthrough"],
)


@router.get(
    "",
    response_model=ReadthroughResponse,
)
async def get_readthrough(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> ReadthroughResponse:
    """取通读视图聚合 payload（AC1/AC2/AC4/AC5/AC6/AC7）。

    前端进通读页（`#/projects/:id/readthrough`）调本端点一次拿到全部已定稿章节的
    分页正文，章内/跨章翻页全在前端完成（不再回源）。空集返 `chapters=[]`、
    `totalChapters=0`——前端走「还没有可通读的已定稿章节」空态而非 404（AC6，
    **陷阱⑪**）。project_id 非法 UUID → FastAPI 自动 422。
    """
    return await chapter_service.get_readthrough_summary(
        session,
        user_id=current_user.id,
        project_id=project_id,
    )
