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


async def get_owned_project(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> Project | None:
    """按 id + user_id 一步取本人作品（Story 1.5 改名/删除的通用前置，NFR3）。

    id 与 user_id **写在同一个 where 里一次过滤**是关键（陷阱①）：取不到就返回 None，
    「作品不存在」与「作品不属于我」二义合一——调用方（service）统一转同一个 404，
    攻击者无法据响应差异区分 project_id 是否真实存在（消除 IDOR 侦察面）。
    不要先按 id 查再比对 owner，那样代码里会出现「存在但不属于你」分支，易手滑返回 403。
    """
    stmt = select(Project).where(
        Project.id == project_id, Project.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_project(session: AsyncSession, project: Project) -> None:
    """删除给定 Project（只 delete、不 commit）；事务边界归 service，延续 repo 只 flush 约定。"""
    await session.delete(project)


async def advance_phase(
    session: AsyncSession, project: Project, *, phase: str
) -> Project:
    """推进作品创作阶段 phase（Story 3.5 AC1：确认设定后 explore→chapter）。

    Story 1.6 以来的首个 phase 写入点——此前 phase 仅在建行时写 _INITIAL_PHASE='explore'。
    接收已取到的 Project 实例（service 用 get_owned_project 取，租户守卫已在取行时完成，同
    delete_project 的入参风格）：置 phase、flush，事务边界归 service（不 commit）。

    Story 1.6 据 phase 路由「继续创作」到当前步骤（explore=探索/设定、chapter=章节创作、
    archive=归档）；确认设定即从探索阶段推进到章节创作。V1 不做 phase 状态机校验（无回退
    需求，原型确认后直接进章节、无回退入口）。
    """
    project.phase = phase
    await session.flush()
    return project
