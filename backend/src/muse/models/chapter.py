"""章节创作业务域 ORM 模型：Chapter（章节终稿正文，Story 4.4）。

**业务表**（与 4.2 `ChapterGenerationRun` / 4.3 `StagePlan` 的编排状态表相对）：Epic 4「按需
建表：无」指的是复用 Epic 3 `story_bible` + 编排状态落 PG（epics.md:858）；而**章节正文正身**
是 deferred-work.md:342 明确「正文落业务表全留 4.4」的本 story 交付面。

`ChapterGenerationRun.steps.polisher.output` 是**编排中间产物**（断点续跑用，随 run 表演进），
不适合作正文正身的长期读取源——阅读（4.5）/改进（4.6）/定稿（4.7）/写前上下文前序注入都读本
表。故本表持久化终稿正文，与编排状态表分层（chapter_generation.py:1-9 已界定「基础设施表 vs
业务表」）。

**字段可空/默认策略**：
- 租户列 user_id + project_id：所有业务表必带（architecture.md:295），建索引 + FK。
- chapter_number：第几章（从 1 起）。(user_id, project_id, chapter_number) 复合唯一——一作品
  一章至多一行，重生成 upsert 同行（幂等键，与 chapter_generation_run 同键语义）。
- text：终稿正文（Text NOT NULL，server_default=""）。= 流水线 polisher 段产物。
- revision：草稿版本号（Int，server_default="1"）。4.4 只写 1；4.6「改进本章」升版复用本列。
- status：章节状态 draft/finalized（Text，server_default="draft"）。4.4 只写 draft；4.7
  「定稿本章」置 finalized 复用本列。值域由 service 保证（同 story_bible.status 无枚举 CHECK）。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class Chapter(Base, UUIDPKMixin, TimestampMixin):
    """某作品某章的终稿正文；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible/stage_plan/chapter_generation_run 一致）。有行 = 该章
    已生成落库（前端可直接渲染 reading 态），无行 = 尚未生成（前端显示 input 态 / 连 SSE 等就绪）。
    """

    __tablename__ = "chapter"

    # 一作品一章一行：(user_id, project_id, chapter_number) 复合唯一——重生成 upsert 同行
    # （幂等键，保证「重进不重生成」与 ARQ 重试不产生正文副本）。复合而非单列唯一：贴租户语义、
    # 与查询守卫列一致（同 chapter_generation_run / stage_plan）。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "chapter_number",
            name="uq_chapter_user_project_number",
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——业务表必带 user_id+project_id。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # 第几章（从 1 起）。与 (user_id, project_id) 共同构成幂等键。
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # 终稿正文（流水线 polisher 段产物）。Text 不设长度上界（章节正文长度不可预估）。
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # 草稿版本号：4.4 恒 1；4.6「改进本章」重生成升版复用本列（server_default="1"）。
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )

    # 章节状态：draft（草稿）/ finalized（已定稿）。4.4 恒 draft；4.7「定稿本章」置
    # finalized 复用本列。值域由 service 保证（server_default="draft"）。
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
