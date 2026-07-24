"""注册测试共享 fixture：真实 DB 建表 + 每用例清表 + 邀请码种子。

DB 用例沿用 1.1 约定：需先 `docker compose up -d` 起容器并设 `MUSE_DB_READY=1`，否则 skip。
测试用与应用相同 psycopg3 DSN 的**同步**引擎做建表/清表/断言查询——与应用的 async 引擎
分属不同连接与事件循环，互不干扰（避免 async 引擎跨事件循环复用的陷阱）。
"""

import os
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from muse.core.settings import get_settings
from muse.models import account  # noqa: F401  注册 metadata（供 create_all 建表）
from muse.models.account import InviteCode, User
from muse.models.base import Base

DB_READY = os.getenv("MUSE_DB_READY") == "1"
requires_db = pytest.mark.skipif(
    not DB_READY, reason="需起容器并设 MUSE_DB_READY=1 才跑注册 DB 用例"
)


@lru_cache
def _sync_engine() -> Engine:
    """惰性单例：仅在 DB 用例首次请求时连库并幂等建表；离线用例不触发。"""
    engine = create_engine(get_settings().database_url)
    Base.metadata.create_all(engine, checkfirst=True)
    return engine


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """每个 DB 用例前清空账户表，保证用例间数据隔离。离线用例不碰 DB。"""
    if not DB_READY:
        return
    with _sync_engine().begin() as conn:
        conn.execute(text('TRUNCATE "user", invite_code RESTART IDENTITY CASCADE'))


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
