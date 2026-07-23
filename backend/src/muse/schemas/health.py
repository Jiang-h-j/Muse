"""健康检查 schema：验证 snake_case → camelCase 边界转换（db_connected → dbConnected）。"""

from muse.schemas.base import CamelModel


class HealthResponse(CamelModel):
    status: str
    db_connected: bool  # API 边界输出为 dbConnected
