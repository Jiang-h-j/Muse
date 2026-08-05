"""章节创作编排域 ORM 模型：ChapterGenerationRun（编排运行状态，Story 4.2，AR11）。

**基础设施表，非业务表**：AR11 要求「每 step 幂等可重入、状态落 PG（天然断点续跑）」
（epics.md:122、architecture.md:189-193）。这张表持久化五段流水线（V1 四段
context→drafter→reviewer→polisher）的运行状态与各段中间产物，使某段失败/重试时能从断点
续跑、只重跑失败段而非从头重跑四段（每段各费一次 LLM 调用，NFR5 成本累计）。

Epic 4「按需建表：无」指的是**业务表**（章节正文 / chapter_cards——归 Story 4.4 / Epic 5）；
编排运行时状态表是基础设施表，不在该约束范畴（见 4.2 story Dev Notes「断点续跑落地方案」）。

**字段可空/默认策略**：
- 租户列 user_id + project_id：所有业务/编排表必带（architecture.md:295），建索引 + FK。
- chapter_number：第几章（从 1 起）。(user_id, project_id, chapter_number) 复合唯一——
  同一作品同一章至多一条运行记录，重入复用同行（断点续跑幂等键）。
- status：run 级状态 running/succeeded/failed，server_default="running"；值域由 service
  保证（同项目既有无枚举 CHECK 先例，story_bible.status 亦无）。
- steps：JSONB，存各段状态 + 落库产物，形如
  {"context": {"status": "succeeded", "output": "<写作任务书>"},
   "drafter": {"status": "succeeded", "output": "<初稿正文>"}, ...}。
  续跑时读某段 status=="succeeded" 即跳过、直接用其 output 喂下一段。V1 用 JSONB 而非拆列：
  段数/结构 V1 会演进（V2 补 data-agent 第五段），JSONB 免频繁迁移；单条 run 数据量小。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class ChapterGenerationRun(Base, UUIDPKMixin, TimestampMixin):
    """某作品某章的五段流水线运行状态；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible/project 一致）。断点续跑的状态源——编排器每段前查
    steps、跑完写 steps，失败重试从未完成段续跑。
    """

    __tablename__ = "chapter_generation_run"

    # 一作品一章一运行记录：(user_id, project_id, chapter_number) 复合唯一——重入复用同行
    # （断点续跑幂等键）。复合而非单列唯一：贴租户语义、与查询守卫列一致（同 story_bible）。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "chapter_number",
            name="uq_chapter_generation_run_user_project_chapter",
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

    # 第几章（从 1 起）。与 (user_id, project_id) 共同构成断点续跑幂等键。
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # run 级状态：running（进行中）/ succeeded（四段全成）/ failed（某段最终失败）。
    # server_default="running"：建行即视为开跑。值域由 service 保证。
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")

    # 各段状态 + 落库产物（JSONB）。键为段名（context/drafter/reviewer/polisher），值形如
    # {"status": "succeeded"|"failed", "output": "<该段产物文本>"}。续跑复用 succeeded 段的
    # output。新建行时为 None（尚未跑任何段），编排器逐段 update_step 填充。
    steps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 本章想法（可选，Story 4.4 用户填；本 story 编排器接受并透传给 context-agent）。
    # 落库供续跑时重建同一写作任务书（保证重入产出一致）。可空。
    chapter_idea: Mapped[str | None] = mapped_column(Text, nullable=True)
