"""Pydantic V2 API 边界基类：DB snake_case ↔ API camelCase 的唯一转换点（AR4）。

所有对外 response/request schema 继承 CamelModel，即自动在 API 边界产出/接受 camelCase，
内部字段保持 snake_case。转换只收敛在 schema 层，禁止在 DB / repository 两端手写不一致字段名。

时间字段一律用 UTCDateTime（AR5）：统一序列化为带 `Z` 后缀的 ISO 8601 UTC 字符串
（如 2026-07-24T08:00:00Z），而非 Pydantic 默认的 `+00:00`。凡对外输出时间的 schema
字段都应标注为 UTCDateTime，收敛该约定于此、勿在各 schema 手写序列化器。
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _to_iso8601_z(value: datetime) -> str:
    """datetime → ISO 8601 UTC 带 Z 后缀。naive datetime 视为 UTC。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[datetime, PlainSerializer(_to_iso8601_z, return_type=str)]
"""API 边界时间类型：序列化为 `2026-07-24T08:00:00Z` 形态的 ISO 8601 UTC（AR5）。"""


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
