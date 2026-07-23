"""数据库：SQLAlchemy 2.0 async engine 与 session。

DSN 使用 psycopg3 async（postgresql+psycopg://），非 asyncpg——与 Alembic env.py 保持一致。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from muse.core.settings import get_settings


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)


engine: AsyncEngine = _create_engine()

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI 依赖：提供一个 async 会话，请求结束自动关闭。"""
    async with async_session_maker() as session:
        yield session
