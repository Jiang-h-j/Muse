"""作品域 ORM 模型：Project（用户的一部小说）。

project 是首张带 user_id 的业务表（NFR3 行级隔离的落地起点）：所有查询/写入都经
repositories 层强制绑定 user_id 租户守卫。字段保持精简够用——只落真实态
（title/mode/phase），不建 attention/detail/action 等展示派生列（由前端按 phase 派生），
updated 复用 TimestampMixin 的 updated_at，勿另建冗余列。
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class Project(Base, UUIDPKMixin, TimestampMixin):
    """一部小说；归属某个 user（租户根）。

    mode/phase 存**英文枚举**（guided/free、explore/chapter/archive），中文展示是
    前端的事——存中文会让 phase 路由判断（Story 1.6）脆弱难维护。列用 String 而非
    DB enum 类型，与现有 models 风格一致、加枚举值时免迁移。
    """

    __tablename__ = "project"

    # 租户外键：指向 user 表（1.2 已建）。index 支撑「列出我的作品」高频按 user_id 过滤。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 标题留空由 service 回落「未命名小说」，落库时恒非空。
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # 创建入口模式：guided（引导探索）/ free（自由探索）。
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # 创作阶段：explore/chapter/archive；新建初始 explore，Story 1.6 据此路由「继续创作」。
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="explore")
