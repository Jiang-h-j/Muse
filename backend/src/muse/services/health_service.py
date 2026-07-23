"""健康检查业务：探活数据库连通性。

示范 AR2 分层——router 不直查 DB，经 service 执行 SELECT 1。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_db_connected(session: AsyncSession) -> bool:
    """执行 SELECT 1 验证 DB 连通；连接失败返回 False。"""
    try:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one() == 1
    except Exception:
        return False
