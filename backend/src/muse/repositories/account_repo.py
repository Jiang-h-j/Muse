"""账户域 DAO：user / invite_code 的主键/唯一键直查与写入。

本 story 中 user 是租户根，无上游 user_id 守卫可注入（跨表租户守卫从 Story 1.4 project 起）。
故这里只按主键/唯一键查询；事务边界（commit/rollback）交由 service 编排，repo 只 flush。
"""

import uuid
from typing import cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.account import ByokKey, InviteCode, User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """按主键查用户；鉴权依赖用它从 access token 的 sub 还原当前 User（Story 1.3）。"""
    return await session.get(User, user_id)


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


# ---------- BYOK（Story 1.7）：账户级自带 API Key 的存取 ----------
# 所有查询显式绑定 user_id 租户守卫（NFR3，陷阱⑤）——越权读/改/删他人 Key 一律等同
# 「未绑定/删 0 行」，不泄露他人是否绑定。repo 只 flush/delete，事务边界归 byok_service。


async def get_byok_by_user(session: AsyncSession, user_id: uuid.UUID) -> ByokKey | None:
    """按 user_id 查本人 BYOK（唯一约束下至多一条）。

    where(user_id) 是租户守卫：只返回属于该用户的记录，取不到即 None（未绑定/越权同义），
    调用方无从区分「他人存在但不属于我」——消除存在性侦察面（AC4）。
    """
    result = await session.execute(select(ByokKey).where(ByokKey.user_id == user_id))
    return result.scalar_one_or_none()


async def upsert_byok(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider: str,
    encrypted_key: str,
    key_suffix: str,
) -> ByokKey:
    """绑定/替换本人 BYOK（AC1/AC3 upsert 语义）：存在则覆盖、不存在则插入，只 flush。

    先 get 再分支最直白（并发替换极低概率，与 rename/delete 的 check-then-act 同风险级，
    加固 deferred 到「开放注册/多端并发前」）。替换时 updated_at 由 TimestampMixin 的
    onupdate=func.now() 在 UPDATE 时自动刷新（勿手动赋 func.now()——那会给内存态留下 SQL
    子句对象而非 datetime；时间戳的拉回由 service commit 后 session.refresh 负责）。
    """
    existing = await get_byok_by_user(session, user_id)
    if existing is not None:
        existing.provider = provider
        existing.encrypted_key = encrypted_key
        existing.key_suffix = key_suffix
        await session.flush()
        return existing
    byok = ByokKey(
        user_id=user_id,
        provider=provider,
        encrypted_key=encrypted_key,
        key_suffix=key_suffix,
    )
    session.add(byok)
    await session.flush()
    return byok


async def delete_byok(session: AsyncSession, user_id: uuid.UUID) -> int:
    """条件删除本人 BYOK（AC3 解绑），返回受影响行数；只 delete 不 commit。

    where(user_id) 租户守卫：只删自己的，删不到他人（rowcount=0）。返回 rowcount 供 service
    判断（但 service 侧解绑幂等，删 0 行也算成功）。
    """
    stmt = delete(ByokKey).where(ByokKey.user_id == user_id)
    result = cast("CursorResult[object]", await session.execute(stmt))
    return result.rowcount
