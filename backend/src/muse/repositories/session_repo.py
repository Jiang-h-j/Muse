"""refresh 会话 DAO：按 token_hash 唯一键直查 + 写入/撤销。

延续 account_repo 约定：repo 只 flush，事务边界（commit/rollback）由 service 编排。
本 story refresh 查询按 token_hash 唯一键直查即可——跨表租户守卫从 1.4（project 带 user_id）起
才实装，此处会话按唯一键定位，不需注入 user_id 守卫。
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.account import RefreshSession


async def create_refresh_session(
    session: AsyncSession, user_id: uuid.UUID, token_hash: str, ttl_seconds: int
) -> RefreshSession:
    """新建 refresh 会话行并 flush；expires_at = now + ttl。是否提交由 service 决定。"""
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    refresh_session = RefreshSession(
        user_id=user_id, token_hash=token_hash, expires_at=expires_at
    )
    session.add(refresh_session)
    await session.flush()
    return refresh_session


async def get_active_by_token_hash(
    session: AsyncSession, token_hash: str
) -> RefreshSession | None:
    """按 token_hash 查**有效**会话：未撤销（revoked_at IS NULL）且未过期。

    过期/已撤销均视为无效返回 None，由 service 抛 token_invalid（AC2）。
    """
    stmt = select(RefreshSession).where(
        RefreshSession.token_hash == token_hash,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > datetime.now(UTC),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_by_token_hash(session: AsyncSession, token_hash: str) -> int:
    """撤销指定 refresh 会话（置 revoked_at=now），返回受影响行数。

    幂等（陷阱⑦）：已撤销/不存在时 rowcount=0，service 据此仍视 logout 成功。
    仅撤销当前未撤销的行（revoked_at IS NULL），避免覆盖历史撤销时间。
    """
    stmt = (
        update(RefreshSession)
        .where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.now(), updated_at=func.now())
    )
    result = cast("CursorResult[object]", await session.execute(stmt))
    return result.rowcount


async def revoke_and_replace(
    session: AsyncSession,
    old_token_hash: str,
    user_id: uuid.UUID,
    new_token_hash: str,
    ttl_seconds: int,
) -> RefreshSession:
    """refresh 轮转（陷阱④防重放）：作废旧 refresh + 下发新 refresh，返回新会话行。

    作为内聚的轮转原语组合 revoke + create，二者共处同一 service 事务（本函数只 flush、不 commit，
    延续 repo 约定）。旧 refresh 一经轮转即失效，重放时 get_active 查不到→service 抛 token_invalid。
    """
    await revoke_by_token_hash(session, old_token_hash)
    return await create_refresh_session(session, user_id, new_token_hash, ttl_seconds)
