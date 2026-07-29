"""探索域 ORM 模型：ExplorationMessage（引导问答记录 + 自由对话消息，两种写入语义共表）。

2.4 的答案落库：把引导探索的每题答案从内存态（前端 explorationHistory JS 变量，
刷新即丢）真实持久化。表名遵循架构既定 exploration_message（architecture.md:236,293，
「对话与线索持久化」统称容器），引导答案是其 V1 落地形态——不自造 exploration_answer。

2.6 按 2.4 docstring 预告扩展：自由探索对话（追加式对话流，role/content）在本表新增列
落地，不另建表——`kind` 列区分两种写入语义。引导是 6 定长题位、重选覆盖（question_index
定点键）；自由是追加式流、每条独立存在（role/content，无定点覆盖语义）。guided 行的
role/content 恒 NULL，free 行的 question_index/question/answer/answer_type 恒 NULL——
两种语义共表但互不填充对方专属列，靠 kind 分派读写路径。

answer_type 是引导作答路径的领域事实（非为 2.6 预留）：选项作答（不调 LLM）与自述作答
（经 2.3 interpret 凝练）是两条本质不同的作答路径，持久化时区分是自然的领域记录，也让前端
恢复回填未来可直接读 answer_type 更健壮。后端只存/取、不推断类型（后端不镜像题库，无法匹配
value），answer_type 由前端按作答路径明确传入。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class ExplorationMessage(Base, UUIDPKMixin, TimestampMixin):
    """某探索会话下的一条记录：引导题位答案，或自由对话消息；归属 user+project+session。

    表名单数 snake_case（与 exploration_session/project/user 一致）。`kind` 存英文枚举
    （guided/free），`answer_type`/`role` 同样存英文枚举——均用 String(16) 而非 DB enum，
    加枚举值免迁移，与 mode 同款。
    """

    __tablename__ = "exploration_message"

    # (session_id, question_index) 复合唯一：答案属于「某次探索会话」的某题位，同会话同题位
    # 至多一条 = 重选即覆盖（upsert on_conflict_do_update 的定点键，AC4/AC5）。用 session_id
    # 而非 project_id——更贴领域（答案归属探索会话），且与 2.6「一 project 多次探索」潜在扩展
    # 一致（V1 一 project 一 session，无差异）。**free 行 question_index 恒 NULL**——
    # PostgreSQL 唯一约束视多个 NULL 为互不相同，free 行之间、free 行与 guided 行均不冲突
    # （无需 partial index，同 story_clue.clue_key 同款技巧）。
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "question_index",
            name="uq_exploration_message_session_id_question_index",
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。架构硬规——所有业务表必带 user_id + project_id
    # （architecture.md:295,449）；去规范化冗余，租户过滤免 join session。index 支撑按作品查询。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )
    # 答案挂会话根：指向 exploration_session 表（2.2）。index 支撑「按会话取全部答案」恢复查询。
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exploration_session.id"), nullable=False, index=True
    )
    # 写入语义分派（2.6 新增）：guided（引导定长题位）| free（自由追加式对话流）。
    # server_default 供已有测试库回填历史行；新代码写入恒显式传值，不依赖此默认。
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="guided"
    )
    # 引导题位（0-based，guided-only）：重选覆盖的定点键（与 session_id 复合唯一）。free 行恒 NULL。
    question_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 题干（guided-only）：前端从 explorationQuestions[view].question 传，后端不镜像题库
    # （延续 2.3 受控决策）。free 行恒 NULL。
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 完整一句话答案（guided-only）：选项 value 或自述凝练结果。free 行恒 NULL。
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 作答路径领域事实（guided-only）：option（选项作答，不调 LLM）| custom（自述作答，经 2.3
    # interpret）。free 行恒 NULL。
    answer_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 消息角色（free-only）：user（用户发言）| agent（Agent 回复）。guided 行恒 NULL。
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 消息正文（free-only）：自由对话的一条完整消息文本。guided 行恒 NULL。
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
