"""认证业务编排（AR2：业务在 service，不在 router）。

- register：校验邀请码 → 校验邮箱 → argon2 哈希 → 单事务内建 user + 原子消费邀请码。
- login/refresh/logout（Story 1.3）：双 token 签发、refresh 轮转、退出作废，见各函数陷阱注释。
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from muse.core.settings import get_settings
from muse.models.account import InviteCode, User
from muse.repositories import account_repo, session_repo
from muse.services import rate_limit

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


# ---------- Story 1.3：登录 / 刷新 / 退出 ----------


class TokenBundle(NamedTuple):
    """service 层的双 token 产出；router 据此组装 TokenResponse。"""

    access_token: str
    expires_in: int
    refresh_token: str


def _invalid_credentials() -> ErrorEnvelope:
    # 邮箱不存在与密码错误**共用同一文案**（AC3），不泄露账号是否存在（陷阱③）。
    # detail.invalid=true 兼容原型登录模式 invalid 分支（app.js:261）。
    return ErrorEnvelope(
        code="invalid_credentials",
        message="邮箱或密码错误，请检查后重试。",
        detail={"invalid": True},
        http_status=401,
    )


def _too_many_attempts() -> ErrorEnvelope:
    # 锁定态（AC4）：detail.locked=true 对接原型 locked 文案（app.js:264）。
    return ErrorEnvelope(
        code="too_many_attempts",
        message="登录尝试次数过多，请稍后再试。",
        detail={"locked": True},
        http_status=429,
    )


def _token_invalid() -> ErrorEnvelope:
    # refresh 失效（过期/被撤销/不存在，AC2）：前端据此跳 #/login?state=expired。
    return ErrorEnvelope(
        code="token_invalid",
        message="会话已过期，请重新登录。",
        detail={"expired": True},
        http_status=401,
    )


async def _issue_tokens(session: AsyncSession, user_id: uuid.UUID) -> TokenBundle:
    """签发 access（无状态 JWT）+ refresh（随机串，哈希落库），返回明文双 token。

    refresh 明文只在此产出一次交给前端，库里只存其 SHA-256 哈希（泄库不可反推）。
    """
    settings = get_settings()
    access_token, expires_in = create_access_token(user_id)
    refresh_plain = generate_refresh_token()
    await session_repo.create_refresh_session(
        session,
        user_id=user_id,
        token_hash=hash_refresh_token(refresh_plain),
        ttl_seconds=settings.refresh_token_ttl_seconds,
    )
    return TokenBundle(access_token, expires_in, refresh_plain)


async def login(session: AsyncSession, email: str, password: str) -> TokenBundle:
    """登录编排（AC1/AC3/AC4）。成功返回双 token；失败抛语义化 ErrorEnvelope。

    顺序严格：① 锁定早拒（陷阱⑥，不进 argon2）→ ② 查 user；不存在也跑一次等时 verify
    消除时序侧信道（陷阱③）→ ③ 校验失败则记失败计数 + 抛 invalid_credentials
    → ④ 成功则清零计数 + 签发双 token。
    """
    # ① 锁定判定在密码校验之前（陷阱⑥）：锁定态直接拒绝，省 argon2 开销且不泄露账号存在性。
    if await rate_limit.is_locked(email):
        raise _too_many_attempts()

    # ② 查 user。不存在时对固定假 hash 跑一次 verify，使「不存在」与「密码错」耗时相近（陷阱③）。
    user = await account_repo.get_user_by_email(session, email)
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_ok = await verify_password(password_hash, password)

    # ③ user 不存在或密码错：共用同一失败路径（措辞/耗时一致，不泄露账号是否存在）。
    if user is None or not password_ok:
        await rate_limit.check_and_incr_login_failure(email)
        raise _invalid_credentials()

    # ④ 成功：清零失败计数 + 签发双 token 并提交（refresh 会话落库）。
    await rate_limit.reset_login_failures(email)
    bundle = await _issue_tokens(session, user.id)
    await session.commit()
    return bundle


async def refresh(session: AsyncSession, refresh_token: str) -> TokenBundle:
    """刷新编排（AC2）：校验 refresh 有效后签发新 access，并轮转 refresh（陷阱④防重放）。

    旧 refresh 一经使用即作废、下发全新 refresh。重放的旧 refresh 查 active 落空即 token_invalid。
    """
    token_hash = hash_refresh_token(refresh_token)
    active = await session_repo.get_active_by_token_hash(session, token_hash)
    if active is None:
        raise _token_invalid()

    settings = get_settings()
    access_token, expires_in = create_access_token(active.user_id)
    new_refresh_plain = generate_refresh_token()
    await session_repo.revoke_and_replace(
        session,
        old_token_hash=token_hash,
        user_id=active.user_id,
        new_token_hash=hash_refresh_token(new_refresh_plain),
        ttl_seconds=settings.refresh_token_ttl_seconds,
    )
    await session.commit()
    return TokenBundle(access_token, expires_in, new_refresh_plain)


async def logout(session: AsyncSession, refresh_token: str) -> None:
    """退出编排（AC5）：作废对应 refresh 会话。幂等（陷阱⑦）——已撤销/不存在也视为成功。"""
    await session_repo.revoke_by_token_hash(session, hash_refresh_token(refresh_token))
    await session.commit()
