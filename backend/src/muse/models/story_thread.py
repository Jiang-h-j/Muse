"""归档域 ORM 模型：StoryThread（未回收伏笔/线索，Story 5.1 建）。

**业务表**：承载长篇故事里所有「埋了但还没收」的伏笔与线索。是 Epic 4 创作
长程一致性（NFR4「几百章不穿帮」）的关键一致性面之一——每章定稿 data-agent
从定稿正文提取新线索 INSERT 本表（或 UPDATE `last_touched_chapter_number`
作「再提一记」）、回收的伏笔翻 `status='resolved'`、`abandoned` 留给后续 V2
手动放弃路径。

**写路径不在本 story**：Story 5.2 chapter-commit 单事务统一投影。本 story
只建表结构 + 最小租户守卫读法（`list_open_by_project` 供 5.6 RAG 召回与
5.3 归档页消费），投影逻辑归 5.2 service。

**关键字段语义**：
- `content` (Text NOT NULL server_default="")：线索/伏笔的事实描述全文
  （data-agent 凝练产物；空串允许——LLM 产空可落库不炸约束，由 service 上游
  空产守卫挡住）。
- `status` (Text NOT NULL server_default="open")：`open` / `resolved` /
  `abandoned` 三值；**不加 DB CHECK 枚举约束**——值域由 service 保证（与
  `chapter.status` / `story_bible.status` / `project.billing_path` 全项目无
  枚举 CHECK 先例一致）。
- `introduced_chapter_number` (Integer NOT NULL)：第几章埋的。
- `resolved_chapter_number` (Integer | NULL)：第几章收的。未收 = NULL
  （`nullable=True` 表「未发生」语义，对齐 story_bible 特化列「不适用 =
  NULL」先例）。
- `last_touched_chapter_number` (Integer NOT NULL)：最近一次推进/提及的
  章号。新增时 = `introduced_chapter_number`；后续每章定稿 data-agent 重提
  时同步推到此章号。**为 5.6 RAG「N 章未回收伏笔」召回与归档页按最近活跃
  度排序的核心排序依据**——章号距当前章节越大、`status='open'`，越该被
  context-agent 注入提醒。

**无复合唯一约束**：一作品可同时存在多条 open thread（片断级、无自然幂等
键），故仅 `id` 主键。5.2 投影时用 `last_touched_chapter_number` + 内容
哈希/匹配在 service 层自行去重，避免重跑产生重复 thread。

**clean-room 合规**：与 story_bible 同——借 webnovel-writer story_threads /
urgent_loops 语义，clean-room 重实现；GPL 义务评估挂账项目级（见 5.1 story
待确认项 1）。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class StoryThread(Base, UUIDPKMixin, TimestampMixin):
    """某作品的一条未回收伏笔/线索；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible / chapter_card 一致）。同一 (user_id,
    project_id) 允许多行并存——每条 open thread 是独立的伏笔/线索实体。
    """

    __tablename__ = "story_thread"

    # 不建复合唯一约束（见模块 docstring）：thread 是「事件片断」，无自然幂等
    # 键，5.2 由 service 用 (project_id, last_touched_chapter_number, 内容)
    # 自行匹配去重。仅列级索引由 SQLAlchemy `index=True` 自动生成 ix_*。

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——业务表必带
    # user_id + project_id；index 支撑「按作品列出 open threads」高频查询
    # (list_open_by_project）。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # 线索/伏笔描述全文（data-agent 从定稿正文凝练产物）。Text 不设长度上界；
    # ``NOT NULL server_default=""`` 允许空串落库（LLM 产空由 service 空产守卫
    # 在上游挡住，DB 层不爆约束——同 story_clue.value 先例）。
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # 伏笔状态：open（未回收）/ resolved（已回收）/ abandoned（已放弃，V2）。
    # server_default="open"：新增 thread 默认未回收。不加 DB CHECK 枚举——值域
    # 由 service 保证（全项目既有无枚举 CHECK 先例，同 chapter.status）。
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")

    # 第几章埋的（从 1 起）。与 chapter.chapter_number 对齐（Integer NOT NULL、
    # 不设 server_default）：投影时显式赋值。
    introduced_chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # 第几章收的；未回收 = NULL。nullable=True 表「未发生」语义（区别于 0/空串
    # 语义模糊），对齐 story_bible 特化列先例。data-agent 回收时显式写入章号。
    resolved_chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 最近一次推进/提及的章号。新增时 = introduced_chapter_number；后续每章
    # data-agent 重提及时同步推到此章号。是 5.6 RAG「N 章未回收伏笔」召回的排序
    # 指标（章号越旧、status=open 的 thread 越该提醒）与 5.3 归档页活跃度排序。
    # 不设 server_default——业务上必须由 service 显式赋值（防「忘了推进」被默认值
    # 掩盖）。
    last_touched_chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
