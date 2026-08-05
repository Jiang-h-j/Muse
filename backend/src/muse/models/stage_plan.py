"""章节创作编排域 ORM 模型：StagePlan（首个阶段规划，Story 4.3，FR17/NFR4）。

**基础设施/运行时状态表，非业务表**：承 4.2 `ChapterGenerationRun` 先例（AR11 运行状态落 PG），
Epic 4「按需建表：无」指**业务表**（章节正文 / chapter_cards——归 4.4 / Epic 5），编排运行时
状态表不在该约束范畴（同 chapter_generation.py 论证）。

本表持久化「幕后生成的首个阶段规划」——阶段目标 + 该阶段各章骨架（title + brief 列表），使
用户确认设定后异步生成的阶段规划**落库可恢复**（刷新/断线重进第一章不重新生成、省 LLM 成本
NFR5）。阶段规划是 4.4 正文生成的**上游纲领**（更高层、更轻的 LLM 调用），与 4.2 四段正文
流水线是不同产物、不同粒度。

**字段可空/默认策略**：
- 租户列 user_id + project_id：所有编排表必带（architecture.md:295），建索引 + FK。
- stage_number：第几个阶段（从 1 起）。本 story 只写首阶段（=1）；(user_id, project_id,
  stage_number) 复合唯一——一作品一阶段至多一行，**留阶段循环扩展位**供 4.7（FR22 阶段循环
  幕后推进，本 story 不做）。
- goal：阶段目标文本（Text NOT NULL）。LLM 产出的首阶段总体方向。
- chapters：JSONB，各章骨架列表，形如 [{"title": "...", "brief": "..."}]。**章数由 LLM 按
  剧情定、不写死上限**（NFR4 长程一致性按几百章设计，epics.md:935）。V1 用 JSONB 而非拆行/
  拆列：章骨架结构轻、单条数据量小、免频繁迁移（同 chapter_generation_run.steps 论证）。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class StagePlan(Base, UUIDPKMixin, TimestampMixin):
    """某作品某阶段的幕后阶段规划（阶段目标 + 章节骨架）；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible/chapter_generation_run 一致）。有行 = 该阶段已生成
    落库（前端可直接渲染），无行 = 尚未生成（前端显示加载/占位态）。
    """

    __tablename__ = "stage_plan"

    # 一作品一阶段一行：(user_id, project_id, stage_number) 复合唯一——重入复用同行（幂等键，
    # 保证「重进不重生成」）。复合而非单列唯一：贴租户语义、与查询守卫列一致（同
    # chapter_generation_run）。留 stage_number 扩展位供 4.7 阶段循环。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "stage_number",
            name="uq_stage_plan_user_project_stage",
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——编排表必带 user_id+project_id。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # 第几个阶段（从 1 起）。本 story 只写首阶段=1；与 (user_id, project_id) 共同构成幂等键。
    # server_default="1"：建行即默认首阶段。
    stage_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )

    # 阶段目标：LLM 产出的首阶段总体方向文本。Text 不设长度上界（规划文本长度不可预估）。
    goal: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # 章节骨架（JSONB）：[{"title": "第一章标题", "brief": "本章要写什么"}, ...]。章数由 LLM
    # 按剧情定、不写死（NFR4）。新建行时至少含 1 章（service 空产守卫保证非空才落库）。
    chapters: Mapped[list | None] = mapped_column(JSONB, nullable=True)
