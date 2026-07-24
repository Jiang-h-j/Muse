"""注册业务编排（AR2：业务在 service，不在 router）。

编排 register：校验邀请码 → 校验邮箱 → argon2 哈希 → 单事务内建 user + 原子消费邀请码。
原子性与并发兜底见函数内注释（陷阱③④）。
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.core.security import hash_password
from muse.models.account import InviteCode, User
from muse.repositories import account_repo

logger = logging.getLogger("muse")


def _invalid_invite() -> ErrorEnvelope:
    # detail 附 invalid:true 兼容原型注册模式 invalid 分支（app.js:262），
    # 前端据此跳 #/register?state=invalid。
    return ErrorEnvelope(
        code="invalid_invite",
        message="邀请码无效、已使用或已过期。",
        detail={"invalid": True},
        http_status=400,
    )


def _email_conflict() -> ErrorEnvelope:
    # 不泄露密码/内部细节（AC3）：仅告知邮箱已注册。
    return ErrorEnvelope(
        code="email_conflict",
        message="该邮箱已被注册。",
        http_status=409,
    )


def _invite_is_usable(invite: InviteCode) -> bool:
    """预检邀请码是否可用：未被使用且未过期。仅用于尽早对无效码返回；

    真正的一次性门禁在 mark_invite_used 的条件 UPDATE 里（陷阱③），此处预检不保证原子性。
    """
    if invite.used_at is not None:
        return False
    if invite.expires_at is None:
        return True
    return invite.expires_at > datetime.now(UTC)


def _is_email_unique_violation(exc: IntegrityError) -> bool:
    """判断 IntegrityError 是否确为 user.email 唯一约束冲突。

    仅收窄到 email 约束才转 email_conflict；其它完整性错误应重抛，避免误报掩盖真实故障。
    psycopg3 在 exc.orig.diag.constraint_name 暴露约束名（Postgres 默认 user_email_key）。
    """
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    return constraint == "user_email_key"


def _mask_email(email: str) -> str:
    """邮箱掩码：仅保留首字符与域名，避免 PII 明文入日志（如 a***@example.com）。"""
    local, _, domain = email.partition("@")
    masked_local = local[0] + "***" if local else "***"
    return f"{masked_local}@{domain}" if domain else masked_local


async def register(session: AsyncSession, invite_code: str, email: str, password: str) -> User:
    """注册编排。成功返回已持久化的 User；失败抛语义化 ErrorEnvelope，且不留脏数据。"""
    # ① 邀请码预检：不存在/已用/已过期即早失败，账号不创建、邀请码状态不变（AC2）。
    invite = await account_repo.get_invite_code(session, invite_code)
    if invite is None or not _invite_is_usable(invite):
        raise _invalid_invite()

    # ② 邮箱预检：已存在直接冲突（AC3）。此步在消费邀请码之前，故邮箱冲突不消耗邀请码。
    if await account_repo.get_user_by_email(session, email) is not None:
        raise _email_conflict()

    # ③ argon2 哈希（绝不明文，AC1）。哈希在线程池执行，不阻塞事件循环。
    password_hash = await hash_password(password)

    # ④ 单事务：建 user → 原子消费邀请码。任一步失败整体回滚，不留半截数据。
    try:
        user = await account_repo.create_user(session, email=email, password_hash=password_hash)
    except IntegrityError as exc:
        # 并发兜底（陷阱④）：预检到落库之间他人抢注了同邮箱，DB 唯一约束触发。
        # 仅当确为 email 唯一约束才转 email_conflict；其它约束冲突重抛交全局 handler，
        # 避免把无关的完整性错误误报成「邮箱已注册」而掩盖真实故障。
        await session.rollback()
        if _is_email_unique_violation(exc):
            logger.info("注册并发邮箱冲突，已回滚：email=%s", _mask_email(email))
            raise _email_conflict() from None
        raise

    # 条件 UPDATE 消费邀请码：rowcount=1 才算抢到（陷阱③）。=0 说明预检后被他人抢用/刚过期，
    # 回滚整个事务（含刚建的 user），避免建了账号却没占住邀请码。
    consumed = await account_repo.mark_invite_used(session, invite_code, user.id)
    if consumed != 1:
        await session.rollback()
        logger.info("邀请码并发消费失败，已回滚")
        raise _invalid_invite()

    await session.commit()
    return user
