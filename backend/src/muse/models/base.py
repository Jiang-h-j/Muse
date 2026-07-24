"""SQLAlchemy 2.0 声明式 Base 与通用列 mixin。

本 story（1.1）只提供通用地基：id 主键 + created_at/updated_at 时间戳（UTC）。
租户列 user_id / project_id 不在此处——它们是 user/project 表的外键，
分别由 Story 1.2（user）、1.4（project）建表时定义并补 FK，避免此刻 FK 悬空。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类；Base.metadata 即 Alembic autogenerate 的 target。"""


class TimestampMixin:
    """通用时间戳列，数据库侧生成，语义为 UTC。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDPKMixin:
    """UUID 主键。多租户下不可枚举，规避连续整型 ID 的枚举/IDOR 风险。

    default=uuid4 在应用侧生成，插入前即可拿到 id（无需 RETURNING 往返）。
    """

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
