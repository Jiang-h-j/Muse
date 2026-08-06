"""归档域 ORM 模型：ChapterCard（章节卡片，Story 5.1 建）。

**业务表**（与 4.2 `ChapterGenerationRun` / 4.3 `StagePlan` 的编排状态表相对，
同 `chapter` / `story_bible` 一档）：承载已定稿章节沉淀出的归档五要素，
是 Epic 5 章节归档页（Story 5.3）与下一章写前上下文注入（Story 5.6 升级，
AR16 消费 `最近 chapter_cards`）的**唯一长期读取源**。

**写路径不在本 story**：Story 5.2 chapter-commit 单事务由 data-agent 从定稿
正文提取事件/状态变化/新增实体，原子投影回本表（AR17）。本 story 只建表
结构 + 最小租户守卫读法，投影逻辑/upsert 写路径归 5.2 service。

**五要素（epics.md:1075 AC 权威命名）**：
- what_happened：本章发生了什么
- character_changes：人物变化
- new_facts_clues：新增事实与线索
- unresolved_hooks：未解决悬念
- end_state：章末状态

前端原型 mock（app.js:3775-3806）写「尚未解决的悬念」是 UI 层中文标签，
DB 列名以 epics AC 为准（`unresolved_hooks`），前端 5.3 消费时自行映射文案。

**五要素全用 `Text NOT NULL server_default=""`**：语义必备但允许空串，
对齐 story_bible 主干列与 story_clue.value 同款「必备但可空串」先例——
投影时 LLM 若某要素产出为空，DB 也能落库而不违反约束。

**clean-room 合规（NFR7）**：章节卡片字段结构借鉴开源项目 webnovel-writer
作为「数据模型参考」clean-room 重实现——只借五要素语义，不复制其 GPL 源码。
正式商用前须创始人做许可证义务与商业形态兼容性评估（architecture.md:250-252,532
附录待定项，同 story_bible，仍未完成；本表为 clean-room 产出，无新增负担）。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class ChapterCard(Base, UUIDPKMixin, TimestampMixin):
    """某作品某章的归档卡片（五要素）；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 story_bible / chapter / stage_plan 一致）。有行 =
    该章已定稿并完成 data-agent 投影；无行 = 该章未定稿或尚未投影（归档页
    前端按「无卡」态展示，不报错）。
    """

    __tablename__ = "chapter_card"

    # 一作品一章一张卡：(user_id, project_id, chapter_number) 复合唯一——
    # data-agent 投影 upsert 同行的幂等键（5.2 单事务 chapter-commit 重跑 /
    # ARQ 重试 max_tries=1 不产生副本），与 `chapter` 表复合唯一键同键位。
    # 复合而非单列唯一：贴租户语义、与查询守卫列一致（同 chapter / stage_plan /
    # chapter_generation_run 全项目先例）。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "chapter_number",
            name="uq_chapter_card_user_project_chapter",
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——业务表必带
    # user_id + project_id；index 支撑「按作品列出全部章节卡」高频查询（5.3 归档页）。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # 第几章（从 1 起），与 `chapter.chapter_number` 对齐（Integer NOT NULL、
    # 不设 server_default）：data-agent 投影时按定稿章号显式写入，不设默认与
    # 首章绑定假象（不同于 stage_plan.stage_number server_default="1" —— 那是
    # 「首阶段」的显式语义，本列无「首章」默认含义）。与 (user_id, project_id)
    # 共同构成幂等键。
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---------- 章节归档五要素（Text NOT NULL server_default=""） ----------
    # 「必备但允许空串」先例（story_bible 主干列 / story_clue.value）：投影 LLM
    # 某要素产空也能落库。
    # ① 本章发生了什么：一段散文式回顾，供归档页与写前上下文直接注入。
    what_happened: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ② 人物变化：本章人物心智/关系/状态发生的变化。
    character_changes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ③ 新增事实与线索：本章新引入的世界事实/物品/证据/暗示（写入 story_thread 候集）。
    new_facts_clues: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ④ 未解决悬念：本章末仍开放、待后续回收的悬念集合（data-agent 同步推送到
    # story_thread.open）。
    unresolved_hooks: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ⑤ 章末状态：本章收尾时主角/环境/关系等的快照（衔接下一章写前上下文）。
    end_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
