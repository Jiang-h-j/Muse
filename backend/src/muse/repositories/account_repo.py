"""账户域 DAO：user / invite_code 的主键/唯一键直查与写入。

本 story 中 user 是租户根，无上游 user_id 守卫可注入（跨表租户守卫从 Story 1.4 project 起）。
故这里只按主键/唯一键查询；事务边界（commit/rollback）交由 service 编排，repo 只 flush。
"""

import uuid
from decimal import Decimal
from typing import cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.account import ByokKey, InviteCode, UsageLedger, User


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


# ---------- 用量流水（Story 1.8）：账户级 tokens/成本记账与聚合 ----------
# 用量属账户域，DAO 扩展本 repo（与 BYOK 同款决策，勿新建 usage_repo.py）。所有查询显式
# 绑定 user_id 租户守卫（NFR3，陷阱⑦）：查他人用量一律等同「自己 0 用量」，不泄露他人用量。
# repo 只 add/flush/查询，**不 commit**——事务边界归 usage_service（account_repo 铁律）。


async def record_usage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    billing_path: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost: Decimal,
    project_id: uuid.UUID | None = None,
    model_name: str | None = None,
) -> UsageLedger:
    """插入一行用量流水（AC1，供 Epic 2 Provider 层调用完 LLM 后记账的写入接口）。

    只 add + flush（拿到应用侧生成的 UUID id），**不 commit**——是否提交由 usage_service 决定
    （repo 只 flush 的事务边界铁律）。billing_path 由调用方按「本次调用是否走 BYOK」传入
    hosted/byok（陷阱⑧）——本 story 只存该列，判定归 Epic 2 Provider 层。
    """
    usage = UsageLedger(
        user_id=user_id,
        project_id=project_id,
        billing_path=billing_path,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=cost,
        model_name=model_name,
    )
    session.add(usage)
    await session.flush()
    return usage


async def sum_hosted_usage(session: AsyncSession, user_id: uuid.UUID) -> int:
    """聚合本人 **托管路径（billing_path="hosted"）** 的已用 tokens（AC2/AC3）。

    护栏与展示都基于 hosted 累计——BYOK 行不占免费额度（NFR5/AC4），故只累计 hosted（陷阱⑧）。
    计量单位为 tokens（SUM(total_tokens)）而非流水行数：一次 LLM 调用记一行、一章 5–10 次调用，
    COUNT(*) 数的是调用不是章（Task 3 高危口径点），tokens 与记账粒度天然对齐。

    where(user_id) 是租户守卫（陷阱⑦）：只累计属于该用户的行。新用户无任何流水时 SUM 空集
    在 PG 返 NULL，用 func.coalesce(..., 0) 兜底返 0（陷阱⑥）——绝不让 None 流到
    remaining = quota - used 的算术里（None 参与算术 → TypeError → 500）。
    """
    stmt = select(
        func.coalesce(func.sum(UsageLedger.total_tokens), 0)
    ).where(
        UsageLedger.user_id == user_id,
        UsageLedger.billing_path == "hosted",
    )
    result = await session.execute(stmt)
    return result.scalar_one()
