"""归档域 ORM 模型：StoryState（主角状态 / 世界规则 / 当前阶段快照，Story 5.1 建）。

**业务表**：每作品一份**当前快照**——主角的心境/伤势/资源/关系网、世界规则当前
生效版本（含修订追加）、当前所处叙事位置。是 Epic 4 写前上下文（context-agent）
的注入要素之一（AR16），也是长程一致性（NFR4「状态/世界规则不穿帮」）的落点。

**V1 全文存储**：三列均 `Text NOT NULL server_default=""`（必备但可空串，同
story_bible 主干列与 story_clue.value 先例）——由 data-agent 每章定稿按整段
叙事文本写入/演进。V2 实体化（拆子列/JSONB）属长期演进，不在本 story。

**写路径不在本 story**：Story 5.2 chapter-commit 单事务投影。本 story 只建
表结构 + 最小租户守卫读法（`get_by_project`），投影逻辑归 5.2 service。

**关键字段语义**：
- `protagonist_state`：主角当前状态快照（心境/伤势/资源/关系网等 V1 全文）。
- `world_rules_state`：世界规则当前生效快照（含 data-agent 每章追加修订，
  V1 全文追加式覆盖旧值）。
- `current_stage`：当前所处**叙事位置简述**（如「程野刚进入第七码头地下档案
  库」）。**不是 FK 到 `stage_plan.stage_number`**——`stage_plan` 是编排中间
  态（4.2/4.3 「基础设施表 vs 业务表」分层已论证），`story_state.current_stage`
  是业务快照，由 data-agent 每章自由写入/演进，V1 不强耦合（受控决策 2）。

**clean-room 合规**：与 story_bible 同——借 webnovel-writer state 存储面语义，
clean-room 重实现；GPL 义务评估挂账项目级（见 5.1 story 待确认项 1）。
"""

import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class StoryState(Base, UUIDPKMixin, TimestampMixin):
    """某作品的故事状态当前快照（一作品一份）；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible / chapter_card / story_thread 一致）。
    「当前快照」语义上唯一——多行无意义（只保留最新状态，历史演进由
    chapter_card.end_state 与 story_thread.last_touched_chapter_number 侧写）。
    """

    __tablename__ = "story_state"

    # 一作品一份当前快照：(user_id, project_id) 复合唯一——data-agent 投影
    # UPSERT 同行 UPDATE（5.2 单事务 chapter-commit 重跑 / ARQ 重试不产生副本），
    # 与 story_bible 复合唯一同先例。复合而非单列唯一：贴租户语义、与查询守卫列
    # 一致（全项目先例）。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            name="uq_story_state_user_id_project_id",
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——业务表必带
    # user_id + project_id；index 支撑「按作品取当前快照」高频查询（写前上下文
    # 注入每章都读）。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # ---------- 三列快照（Text NOT NULL server_default=""，必备但可空串） ----------
    # 主角当前状态快照（心境/伤势/资源/关系网等 V1 全文）。data-agent 每章定稿
    # 按整段叙事文本写入/演进。
    protagonist_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # 世界规则当前生效快照（含修订追加）。story_bible.world_rules 是「初始设定」，
    # 本列是「当前生效」——data-agent 每章按需追加修订、覆盖旧值。两列分工：
    # story_bible.world_rules 回答「我当初想怎么定」、story_state.world_rules_state
    # 回答「写到第 N 章为止实际生效的是哪些」。
    world_rules_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # 当前所处**叙事位置简述**（如「程野刚进入第七码头地下档案库」）。data-agent
    # 每章自由写入/演进；V1 不 FK 到 stage_plan.stage_number（受控决策 2——
    # 叙事快照 ≠ 编排状态）。
    current_stage: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
