"""账户域 DAO：user / invite_code 的主键/唯一键直查与写入。

本 story 中 user 是租户根，无上游 user_id 守卫可注入（跨表租户守卫从 Story 1.4 project 起）。
故这里只按主键/唯一键查询；事务边界（commit/rollback）交由 service 编排，repo 只 flush。
"""

import uuid
from typing import cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.account import InviteCode, User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    """新建 user 并 flush（拿到应用侧生成的 UUID id）；是否提交由 service 决定。"""
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    await session.flush()
    return user


async def get_invite_code(session: AsyncSession, code: str) -> InviteCode | None:
    result = await session.execute(select(InviteCode).where(InviteCode.code == code))
    return result.scalar_one_or_none()


async def mark_invite_used(session: AsyncSession, code: str, user_id: uuid.UUID) -> int:
    """条件 UPDATE 消费邀请码：仅当未使用且未过期时置为已用（陷阱③）。

    返回受影响行数——=1 表示本次抢到，校验与消费在同一原子语句内完成，杜绝并发下同码被用两次；
    =0 表示已被他人抢用或恰好过期，service 据此判失败并回滚整个事务。
    """
    stmt = (
        update(InviteCode)
        .where(
            InviteCode.code == code,
            InviteCode.used_at.is_(None),
            InviteCode.expires_at.is_(None) | (InviteCode.expires_at > func.now()),
        )
        .values(used_by=user_id, used_at=func.now(), updated_at=func.now())
    )
    # UPDATE 语句的 execute 返回 CursorResult，其 rowcount 即受影响行数（=1 表示抢到）。
    result = cast("CursorResult[object]", await session.execute(stmt))
    return result.rowcount
