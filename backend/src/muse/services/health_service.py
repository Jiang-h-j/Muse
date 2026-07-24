"""健康检查业务：探活数据库连通性。

示范 AR2 分层——router 不直查 DB，经 service 执行 SELECT 1。
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("muse")


async def check_db_connected(session: AsyncSession) -> bool:
    """执行 SELECT 1 验证 DB 连通；连接失败返回 False（保留供离线契约测试）。"""
    try:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one() == 1
    except Exception:
        # 记录异常以区分「DB 挂了」与「DSN/驱动配错」；对外仍降级为 False 由 router 决定状态码。
        logger.warning("数据库探活失败", exc_info=True)
        return False
