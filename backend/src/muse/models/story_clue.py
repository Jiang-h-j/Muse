"""探索域 ORM 模型：StoryClue（自由探索的故事线索，2.6）。

架构既定表名 `story_clue`（architecture.md:236「exploration_sessions + exploration_messages +
story_clues」对话与线索持久化统称容器），不可另造。

预设（preset）线索是进入自由探索时播种的 4 个固定槙位（最初的念头/主角/核心冲突/世界与
氛围），对应 Agent 自动整理端点（[[project_muse_free_explore_clues]] 硬性要求 V1 即要 Agent
依对话自动整理）的操作对象；自定义（custom）线索由用户自行增删，Agent 整理端点永不触碰。

`user_edited` 是「用户已编辑优先、不被自动整理覆盖」（AC5 硬约束）的实现核心：一旦用户手动
编辑过某 preset 槙位即置 true，此后 Agent 整理端点只更新 user_edited=false 的槙位、跳过
true 的——确定性强、可测试，不依赖版本号/时间戳比对等脆弱启发式。
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class StoryClue(Base, UUIDPKMixin, TimestampMixin):
    """某探索会话下的一条故事线索（预设槙位或自定义线索）；归属 user+project+session。

    表名单数 snake_case（与 exploration_message/exploration_session 一致）。`kind` 存英文枚举
    （preset/custom），用 String(16) 而非 DB enum——加枚举值免迁移，与 mode 同款。
    """

    __tablename__ = "story_clue"

    # (session_id, clue_key) 复合唯一：preset 槙位在同一会话内至多一条（防重复播种）。
    # custom 行 clue_key 恒 NULL——PostgreSQL 唯一约束视多个 NULL 为互不相同，custom 行之间
    # 及与 preset 行均不冲突（同 exploration_message.question_index 同款技巧，无需 partial index）。
    __table_args__ = (
        UniqueConstraint(
            "session_id", "clue_key", name="uq_story_clue_session_id_clue_key"
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。架构硬规——所有业务表必带 user_id + project_id
    # （architecture.md:295,449）；去规范化冗余，租户过滤免 join session。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )
    # 线索挂会话根：指向 exploration_session 表（2.2）。index 支撑「按会话取全部线索」查询。
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exploration_session.id"), nullable=False, index=True
    )
    # 线索类别：preset（进入自由探索时播种的固定槙位，不可删除）| custom（用户自行增删）。
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # 预设槙位键（仅 preset 有值）：opening/protagonist/conflict/world，供 Agent 整理端点
    # 精确匹配槙位。custom 行恒 NULL（同表唯一约束设计，见 __table_args__ 注释）。
    clue_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 显示名：preset 固定中文名（如「最初的念头」），custom 由用户输入。
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # 线索内容：空串即前端「尚未确定」占位，占位逻辑在前端不在本表。
    value: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # 用户编辑标志（AC5 核心）：一旦用户手动编辑过该线索即置 true，Agent 整理端点跳过 true 的槙位。
    user_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 稳定展示顺序：4 个 preset 播种时按 0-3，custom 追加递增（取本会话现有最大值 +1）。
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
