"""探索域 ORM 模型：ExplorationSession（一部作品的探索会话根）。

2.2 的会话根：新建作品选定 guided/free 后进入探索，为「user + project」维护恰好一个
会话根。字段与 mode 无关（引导/自由共用同一根，差异只在后续对话/线索的产出过程，
2.3-2.7），产出终点统一到 Epic 3 story_bible——故本表**不为两模式分设列**，也不含
status/title 等派生态（YAGNI）；对话（exploration_message，2.4）、线索（story_clue，2.6）
是后续按需建的独立表，不在此表。

mode 取自 project.mode（后端单一事实源），非客户端所传——service 建会话时读 project.mode
落库，接口无 mode 入参，从数据通道上根除「模式中途切换」（AC2/AC3）。

guidance_state（2.8 新增）：自由探索的设定导航状态（JSONB），记录 7 项通用主干字段的
完成度（missing/filled/skipped）、当前待补字段、当前问题文本与 readyToSettle 布尔位。
只服务 free 模式——guided 会话恒 NULL，不写、不读。**不与 story_clue 合并**
（architecture.md L237 已定档的职责边界）：story_clue 仍是用户可编辑事实展示区，
guidance_state 只是完成度与下一问的后端事实源。
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class ExplorationSession(Base, UUIDPKMixin, TimestampMixin):
    """某作品的探索会话根；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 project/user/byok_key 一致）。mode 存英文枚举
    （guided/free），用 String(16) 而非 DB enum——加枚举值免迁移，与 project.mode 同款。
    """

    __tablename__ = "exploration_session"

    # 一作品一会话：(user_id, project_id) 复合唯一是 AC1 幂等在并发下的最终防线——
    # 两请求同时 miss→双 insert 时，第二条撞唯一约束 IntegrityError，service 兜底重查
    # 返回已存在会话（只靠应用层「先查后建」在并发下必漏，TOCTOU）。复合而非单 project_id
    # 唯一：更贴租户语义、且与查询守卫列 (user_id, project_id) 一致。
    __table_args__ = (
        UniqueConstraint(
            "user_id", "project_id", name="uq_exploration_session_user_id_project_id"
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。index 支撑「按作品取会话」高频查询。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )
    # 探索模式：guided（引导）/ free（自由）。取自 project.mode，会话建后不可改写（AC2/AC3）。
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # 自由探索设定导航状态（2.8 新增）：{fields:{7项主干key:missing/filled/skipped},
    # current_field, current_question, ready_to_settle}。nullable、无 server_default——
    # 只服务 free 模式，guided 会话恒 NULL；free 会话在 enter_exploration 首次创建时初始化。
    guidance_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
