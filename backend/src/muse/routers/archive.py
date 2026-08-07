"""归档页路由（Story 5.3，AR2：router 仅校验入参 + 分发，业务在 archive_service）。

归档页挂在 project 层级下（prefix /api/projects/{project_id}/archive）：
- GET /：取**完整归档页聚合数据**（story_bible + 各阶段 + 各阶段章节卡片），
  不拆多个端点。

**非流式**（同 GET stage-plan / GET story-bible-confirmed）：一次性返回
  JSON body（`ArchiveSummaryResponse`），不做 SSE。依赖 `CurrentUser` 自动完成
  access token 校验并取当前 User；操作绑定 `current_user.id` 实现租户隔离；
  越权/不存在同码 404（业务在 service）。
"""

import uuid

from fastapi import APIRouter

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.archive import ArchiveSummaryResponse
from muse.services import archive_service

router = APIRouter(
    prefix="/api/projects/{project_id}/archive",
    tags=["archive"],
)


@router.get(
    "",
    response_model=ArchiveSummaryResponse,
)
async def get_archive(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> ArchiveSummaryResponse:
    """取已确认设定圣经 + 按阶段分组章节卡片 → 返回完整归档页聚合数据（AC1/AC2/AC3）。

    前端在「继续创作」→ 归档（`#/projects/:id/archive`）时调用本端点，一次获取
    设定圣经区 + 阶段列表（含各阶段章节卡片 summary）。越权/不存在 → service 404
    （二义合一，不泄露作品存在性 NFR3）。project_id 非法 UUID → FastAPI 自动 422。
    """
    return await archive_service.get_archive_summary(
        session,
        user_id=current_user.id,
        project_id=project_id,
    )