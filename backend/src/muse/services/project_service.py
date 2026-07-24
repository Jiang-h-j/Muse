"""作品业务编排（AR2：业务在 service，不在 router）。

- create_project：标题归一化（留空回落「未命名小说」）→ 落库归属当前 user_id → commit。
- list_projects：取当前用户的作品（按 updated_at 倒序，租户隔离在 repo 层保证）。
- rename_project/delete_project（Story 1.5）：按 id 取本人作品，取不到统一 404
  （越权=不存在，陷阱①）；改名复用 _normalize_title 且改后 refresh 拉回 updated_at（陷阱②）。
事务边界在此层（repo 只 flush/delete）；业务错误抛 ErrorEnvelope 交全局 handler。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.models.project import Project
from muse.repositories import project_repo

# 标题留空时的回落值（原型 app.js:1745-1746：value.trim() || "未命名小说"）。
_DEFAULT_TITLE = "未命名小说"
# 新建作品的初始阶段（AC1）：Story 1.6 据 phase 路由「继续创作」。
_INITIAL_PHASE = "explore"


def _normalize_title(title: str | None) -> str:
    """标题归一化：去首尾空白，纯空白/None 回落「未命名小说」。"""
    normalized = (title or "").strip()
    return normalized or _DEFAULT_TITLE


def _project_not_found() -> ErrorEnvelope:
    # 越权与不存在共用同一 404（陷阱①）：不区分「不属于我」与「不存在」，不返回 403，
    # 不泄露 project_id 是否真实存在（消除 IDOR 侦察面，NFR3）。改名/删除共用此工厂。
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在。",
        http_status=404,
    )


async def create_project(
    session: AsyncSession, user_id: uuid.UUID, mode: str, title: str | None
) -> Project:
    """新建作品编排（AC1）。返回已持久化的 Project（含 id/updated_at）。"""
    project = await project_repo.create_project(
        session,
        user_id=user_id,
        title=_normalize_title(title),
        mode=mode,
        phase=_INITIAL_PHASE,
    )
    await session.commit()
    return project


async def list_projects(session: AsyncSession, user_id: uuid.UUID) -> list[Project]:
    """列出当前用户的全部作品，按 updated_at 倒序（AC2）；无作品时返回 []（AC3）。"""
    return await project_repo.list_projects_by_user(session, user_id)


async def rename_project(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, title: str | None
) -> Project:
    """改名编排（AC1）。取不到（不存在/越权）统一抛 404；返回刷新后的 Project。

    改后须 refresh（陷阱②）：updated_at 带 onupdate=func.now()，由 DB 在 UPDATE 时计算，
    commit 后 ORM 内存态不会自动同步新时间戳，须 session.refresh 拉回，否则响应里的
    updatedAt 仍是旧值（AC1「返回更新后的 ProjectResponse」含刷新时间）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()
    project.title = _normalize_title(title)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """删除编排（AC2）。取不到（不存在/越权）统一抛 404；否则真实删除并 commit。"""
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()
    await project_repo.delete_project(session, project)
    await session.commit()
