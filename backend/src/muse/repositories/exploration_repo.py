"""探索域 DAO：exploration_session 的按作品取会话与创建。

命名注意：**不叫 session_repo**——该名已被 auth refresh 会话 DAO 占用
（repositories/session_repo.py），探索会话用 exploration_repo 避免语义撞车。

延续 project_repo/base_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service。所有查询显式绑定 user_id 租户守卫（base_repo 约定，NFR3）——不提供任何绕过
user_id 的全表查询入口。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.exploration_session import ExplorationSession


async def get_session_by_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession | None:
    """按 user_id + project_id 取该作品的探索会话（get-or-create 的 get 步，NFR3）。

    user_id 与 project_id **写在同一个 where 里一次过滤**（仿 project_repo.get_owned_project
    的「二义合一」范式）：取不到即 None，「会话不存在」与「作品不属于我」不产生分支差异。
    (user_id, project_id) 复合唯一（见模型 __table_args__）保证至多一条。
    """
    stmt = select(ExplorationSession).where(
        ExplorationSession.user_id == user_id,
        ExplorationSession.project_id == project_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_session(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, mode: str
) -> ExplorationSession:
    """新建探索会话并 flush（拿应用侧生成的 UUID id）；是否提交由 service 决定。

    mode 由 service 传入 project.mode（AC2 单一事实源，非客户端）。
    """
    exploration_session = ExplorationSession(
        user_id=user_id, project_id=project_id, mode=mode
    )
    session.add(exploration_session)
    await session.flush()
    return exploration_session
