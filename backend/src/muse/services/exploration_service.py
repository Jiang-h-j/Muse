"""探索业务编排（AR2：业务在 service，不在 router）。

enter_exploration 是「进入探索」的 get-or-create 编排：先校验 project 属当前 user
（越权=不存在，统一 404），已有会话直接返回（AC1 幂等 / AC3 mode 不改写），否则以
project.mode 建会话（AC2 单一事实源）并 commit。

并发竞态（陷阱②）：两请求同时 miss→双 insert，第二条撞 (user_id, project_id) 唯一约束
IntegrityError；此层 rollback 后重查返回已存在会话——只靠应用层「先查后建」在并发下必漏
（TOCTOU），唯一约束 + 重查是最终防线。

事务边界在此层（repo 只 flush）；业务错误抛 ErrorEnvelope 交全局 handler。
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.models.exploration_session import ExplorationSession
from muse.repositories import exploration_repo, project_repo


def _exploration_not_found() -> ErrorEnvelope:
    # 复用 project 的 404 语义（探索挂在 project 下，作品不存在即探索不存在，不新造 code）。
    # 越权与不存在共用同一 404（陷阱①）：不区分「不属于我」与「不存在」、不返回 403，
    # 不泄露 project_id 是否真实存在（消除 IDOR 侦察面，NFR3）。
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在。",
        http_status=404,
    )


async def enter_exploration(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession:
    """进入探索的 get-or-create 编排（AC1/AC2/AC3/AC5）。返回该作品的探索会话根。"""
    # 1. 先校验 project 属当前 user（防对他人 project 建会话，AC5 陷阱①）。
    #    id+user_id 同一 where「二义合一」，取不到统一 404（越权=不存在）。
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()

    # 2. get：已有会话直接返回（AC1 幂等 / AC3 已存在会话 mode 不改写）。
    existing = await exploration_repo.get_session_by_project(session, user_id, project_id)
    if existing is not None:
        return existing

    # 3. create：mode 取自 project.mode（AC2，非客户端）。并发下第二插入撞唯一约束，
    #    rollback 后重查返回先到者建的会话（陷阱② 最终防线）。
    try:
        created = await exploration_repo.create_session(
            session, user_id=user_id, project_id=project_id, mode=project.mode
        )
        await session.commit()
        return created
    except IntegrityError:
        await session.rollback()
        existing = await exploration_repo.get_session_by_project(
            session, user_id, project_id
        )
        if existing is None:
            # 唯一约束触发却重查不到：状态异常（非预期路径），交全局 handler 兜底 500。
            raise
        return existing
