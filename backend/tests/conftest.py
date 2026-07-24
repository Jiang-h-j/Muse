"""认证测试共享 fixture：真实 DB 建表 + 每用例清表 + 邀请码种子。

DB 用例沿用 1.1 约定：需先 `docker compose up -d` 起容器并设 `MUSE_DB_READY=1`，否则 skip。
测试用与应用相同 psycopg3 DSN 的**同步**引擎做建表/清表/断言查询——与应用的 async 引擎
分属不同连接与事件循环，互不干扰（避免 async 引擎跨事件循环复用的陷阱）。
"""

import os

# 在 import muse 任何模块（会触发 get_settings 校验）之前注入测试专用强 JWT 密钥。
# 保证测试不依赖某个特定 .env：无论本机 .env 的 DEBUG/JWT_SECRET 为何，测试都用确定配置，
# 且不触发生产弱密钥 fail-fast（Story 1.3 护栏）。setdefault 不覆盖已显式设置的环境变量。
os.environ.setdefault("JWT_SECRET", "test-only-strong-secret-do-not-use-in-prod")
os.environ.setdefault("DEBUG", "true")

from collections.abc import Callable  # noqa: E402
from datetime import datetime  # noqa: E402
from functools import lru_cache  # noqa: E402

import pytest  # noqa: E402
import redis  # noqa: E402
from sqlalchemy import Engine, create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from muse.core.settings import get_settings  # noqa: E402
from muse.models import (
    account,  # noqa: F401, E402  注册 metadata（供 create_all 建表）
    project,  # noqa: F401, E402  注册 metadata（供 create_all 建表）
)
from muse.models.account import InviteCode, User  # noqa: E402
from muse.models.base import Base  # noqa: E402

DB_READY = os.getenv("MUSE_DB_READY") == "1"
requires_db = pytest.mark.skipif(
    not DB_READY, reason="需起容器并设 MUSE_DB_READY=1 才跑 DB 用例"
)


@lru_cache
def _sync_engine() -> Engine:
    """惰性单例：仅在 DB 用例首次请求时连库并幂等建表；离线用例不触发。"""
    engine = create_engine(get_settings().database_url)
    Base.metadata.create_all(engine, checkfirst=True)
    return engine


@lru_cache
def _sync_redis() -> "redis.Redis":
    """同步 Redis 客户端，仅用于测试清理限流计数（独立于应用的 async 单例，无事件循环耦合）。"""
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """每个 DB 用例前清空账户/会话表 + 限流计数，保证用例间隔离。离线用例不碰 DB/Redis。"""
    if not DB_READY:
        return
    with _sync_engine().begin() as conn:
        # refresh_session/project 均有 user_id FK 指向 user，CASCADE 一并清；
        # RESTART IDENTITY 复位序列。
        conn.execute(
            text(
                'TRUNCATE "user", invite_code, refresh_session, project '
                "RESTART IDENTITY CASCADE"
            )
        )
    # 清限流计数键，避免登录失败计数跨用例污染（限流用例天然隔离，无需手动 reset）。
    client = _sync_redis()
    keys = list(client.scan_iter(match="login:fail:*"))
    if keys:
        client.delete(*keys)


@pytest.fixture
def db_engine() -> Engine:
    """供 DB 用例做断言查询的同步引擎。"""
    return _sync_engine()


@pytest.fixture
def make_invite() -> Callable[..., str]:
    """种子邀请码 helper：返回码字符串。可指定过期/已用状态以覆盖 AC2 各分支。"""

    def _make(
        code: str = "TEST-INVITE",
        *,
        expires_at: datetime | None = None,
        used_at: datetime | None = None,
    ) -> str:
        with Session(_sync_engine()) as session:
            session.add(InviteCode(code=code, expires_at=expires_at, used_at=used_at))
            session.commit()
        return code

    return _make


@pytest.fixture
def get_user() -> Callable[[str], User | None]:
    """按邮箱查用户（每次开新会话，读到已提交的最新数据）。"""

    def _get(email: str) -> User | None:
        with Session(_sync_engine()) as session:
            return session.scalar(select(User).where(User.email == email))

    return _get


@pytest.fixture
def make_user() -> Callable[..., User]:
    """种子已注册用户 helper：用真实 argon2 哈希落库，供登录用例用。

    直接同步 hash（测试种子无需走应用的 anyio 线程池）；返回持久化后的 User（含 id/email）。
    """
    from argon2 import PasswordHasher

    hasher = PasswordHasher()

    def _make(email: str = "login@example.com", password: str = "password123") -> User:
        with Session(_sync_engine()) as session:
            user = User(email=email, password_hash=hasher.hash(password))
            session.add(user)
            session.commit()
            session.refresh(user)
            session.expunge(user)
            return user

    return _make


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    """为给定 User 直接签发 access token 并组装 Authorization 头。

    项目里 project 用例只需「已登录身份」，无需每次都走 /login（省一次 argon2 + refresh 落库）。
    直接复用应用的 create_access_token，与 get_current_user 解出的身份严格一致。
    """
    from muse.core.security import create_access_token

    def _headers(user: User) -> dict[str, str]:
        token, _ = create_access_token(user.id)
        return {"Authorization": f"Bearer {token}"}

    return _headers

