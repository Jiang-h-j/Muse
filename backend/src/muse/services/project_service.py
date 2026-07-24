"""作品业务编排（AR2：业务在 service，不在 router）。

- create_project：标题归一化（留空回落「未命名小说」）→ 落库归属当前 user_id → commit。
- list_projects：取当前用户的作品（按 updated_at 倒序，租户隔离在 repo 层保证）。
事务边界在此层（repo 只 flush）；无业务错误分支——空列表是自然结果，故障走全局 handler。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

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
