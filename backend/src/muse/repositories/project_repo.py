"""作品域 DAO：project 的创建与「列出我的作品」。

延续 account_repo/session_repo 约定：repo 只 flush，事务边界（commit/rollback）由 service
编排。所有查询显式绑定 user_id 租户守卫（base_repo 约定，NFR3）——本 repo 不提供任何
绕过 user_id 的全表查询入口。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.project import Project


async def create_project(
    session: AsyncSession, user_id: uuid.UUID, title: str, mode: str, phase: str
) -> Project:
    """新建 project 并 flush（拿到应用侧生成的 UUID id）；是否提交由 service 决定。"""
    project = Project(user_id=user_id, title=title, mode=mode, phase=phase)
    session.add(project)
    await session.flush()
    return project


async def list_projects_by_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Project]:
    """列出当前用户的全部作品，按 updated_at 倒序（最近更新在前，AC2）。

    where(user_id) 是租户守卫（NFR3）——只返回属于该用户的作品；列表恰好为空时返回 []
    （AC3 空态是真实空列表的自然产物，无需特判）。二级键 id 保证同一 updated_at
    （同刻/并发创建）下顺序确定，不随请求抖动。
    """
    stmt = (
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
