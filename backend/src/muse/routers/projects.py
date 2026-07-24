"""作品路由（AR2：router 仅校验入参 + 分发，业务在 project_service）。

POST/GET/PATCH/DELETE /api/projects 均依赖 CurrentUser——鉴权入口（core/deps）自动完成
access token 校验并取当前 User；未登录/token 失效在依赖内 401。所有操作绑定 current_user.id
实现租户隔离；单作品操作（PATCH/DELETE）按 project_id 取本人作品，越权/不存在同码 404。
"""

import uuid

from fastapi import APIRouter, status

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.project import (
    ProjectCreateRequest,
    ProjectRenameRequest,
    ProjectResponse,
)
from muse.services import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest, current_user: CurrentUser, session: SessionDep
) -> ProjectResponse:
    # 入参已由 Pydantic 校验（mode 枚举 / title 长度）；归属当前用户落库在 service（AC1）。
    project = await project_service.create_project(
        session, user_id=current_user.id, mode=payload.mode, title=payload.title
    )
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user: CurrentUser, session: SessionDep
) -> list[ProjectResponse]:
    # 仅返回当前用户的作品，按 updated_at 倒序（AC2）；无作品时返回 []（AC3 空态）。
    projects = await project_service.list_projects(session, user_id=current_user.id)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.patch("/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: uuid.UUID,
    payload: ProjectRenameRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ProjectResponse:
    # PATCH 部分更新语义（陷阱④）；project_id 非法 UUID 由 FastAPI 自动 422。
    # 越权/不存在在 service 统一 404（陷阱①）；返回刷新后含新 updatedAt 的资源（AC1）。
    project = await project_service.rename_project(
        session, project_id=project_id, user_id=current_user.id, title=payload.title
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> None:
    # 204 No Content 不带响应体（陷阱⑤）：不设 response_model、函数返回 None。
    # 越权/不存在在 service 统一 404（陷阱①）；真实删除（AC2）。
    await project_service.delete_project(
        session, project_id=project_id, user_id=current_user.id
    )
