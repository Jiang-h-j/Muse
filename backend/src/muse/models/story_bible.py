"""故事设定域 ORM 模型：StoryBible（设定圣经，12 字段，Story 3.1 建；3.4 加状态位）。

架构既定表名 `story_bible`（architecture.md:227,292「设定圣经条目：唯一创作依据」），
是 Epic 3 的存储根、Epic 4 创作上下文与 Epic 5 归档页的读取源。3.1 建表 12 字段；3.2 写
style_profile；3.3 凝练 12 字段候选卡；**3.4 加 status/revision/changed_fields 三列**，让
「待确认候选卡（pending）→ 确认后只读圣经（confirmed）」在同一行状态流转（3.5 确认只翻
status）。编辑+反馈升版本（3.4）、确认写入（3.5）在后续 story 落地。

**clean-room 合规（NFR7）**：12 字段结构借鉴开源项目 webnovel-writer 作为「数据模型参考」
clean-room 重实现——只借设定产出物的字段语义，不复制其 GPL 源码。正式商用前须创始人做
许可证义务与商业形态兼容性评估（architecture.md:250-252,532 附录待定项，仍未完成）。

**字段可空策略（两种「空」区分）**：
- 通用主干 7 列（genre/core_appeal/protagonist/main_conflict/world_rules/overall_tone/
  opening_hook）语义上必备，但 V1 探索用有限问题集、不保证凑齐（epics.md:723「留空即可、
  不阻塞出卡」）。用 `Text NOT NULL server_default=""` 表达「必备但可存空串」——列恒非
  NULL、3.3 写部分字段不违反约束，与 story_clue.value 同款先例。
- 题材特化 4 列（power_system/golden_finger/romance_line/faction_landscape）用
  `nullable=True`（NULL），表达「该题材不适用/未激活」，区别于主干空串「适用但未填」；
  genre 决定其是否激活（FR12），不匹配的特化列存 NULL、不报错。
- style_profile（Muse 独有、webnovel-writer 无）`nullable=True`：Story 3.2 抽取后写入，
  未锚定文风时为 NULL、系统用默认风格（不阻塞出设定）。
"""

import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin


class StoryBible(Base, UUIDPKMixin, TimestampMixin):
    """某作品的设定圣经（12 字段全文态 V1）；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 project/exploration_session/story_clue 一致）。所有内容字段
    用 Text（不设长度上界，设定条目长度不可预估、V1 全文存）。实体化拆子列/JSONB 属 V2。
    """

    __tablename__ = "story_bible"

    # 一作品一圣经：(user_id, project_id) 复合唯一——一部作品至多一份确认后的设定圣经。
    # 复合而非单 project_id 唯一：贴租户语义、与查询守卫列 (user_id, project_id) 一致
    # （同 exploration_session.py 的唯一约束设计与理由）。
    __table_args__ = (
        UniqueConstraint(
            "user_id", "project_id", name="uq_story_bible_user_id_project_id"
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。架构硬规——所有业务表必带 user_id + project_id
    # （architecture.md:295）；index 支撑「按作品取设定圣经」高频查询。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # ---------- 通用主干 7（必备语义，NOT NULL server_default=""；见模块 docstring） ----------
    # ① 题材：判别列，决定下方题材特化字段是否激活（FR12）。
    genre: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ② 核心吸引力：一句话 + 核心卖点 + 目标阅读体验（并入原型三项为一列）。
    core_appeal: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ③ 主角：姓名 + 核心欲望 + 致命缺陷 flaw，V1 全文单列（不拆子列，实体化属 V2）。
    protagonist: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ④ 主要冲突：+ 反派镜像（反派与主角共享欲望却走反路），V1 全文单列。
    main_conflict: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ⑤ 关键世界规则：世界规模 + 硬约束。
    world_rules: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ⑥ 整体气质。
    overall_tone: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # ⑦ 开篇钩子。
    opening_hook: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # ---------- 题材特化 4（nullable=True，按 genre 激活、不匹配存 NULL） ----------
    # ⑧ 力量体系/境界链（修仙玄幻）。
    power_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ⑨ 金手指（系统爽文）。
    golden_finger: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ⑩ 感情线（言情）。
    romance_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ⑪ 势力格局（设定重题材）。
    faction_landscape: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------- Muse 独有 1（nullable=True） ----------
    # ⑫ 文风锚点：webnovel-writer 完全没有。Story 3.2 抽取作品级 style_profile 后写入，
    # 未锚定时为 NULL、用默认风格。V1 以全文/文本形式存（拆 JSONB 属 V2，见 story 待确认项）。
    style_profile: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------- 候选卡状态位（Story 3.4，落地 3.1 待确认项 2「revision/status 列归属」） ----------
    # 候选卡状态机（受控决策 1：同一行状态位，非另建候选态表）：
    # - draft：行已建、但尚未整理出候选卡——3.2 只锚了文风（upsert_style_profile 建行）却还没
    #   跑 settle 凝练时即此态。**默认值**：建行不显式写 status 即 draft，避免「只锚文风的半成品行」
    #   被 get_pending_by_project 误当候选卡返回（code review 2026-07-29 发现 1）。
    # - pending：3.3 settle 凝练落库的待确认候选卡（可编辑/反馈升版本/刷新恢复，3.4）。
    # - confirmed：Story 3.5 确认后的只读设定圣经（Epic 4 drafter 注入读 confirmed 行）。
    # 一作品一行（uq_story_bible_user_id_project_id）：draft→pending→confirmed 是同行状态流转、
    # 不产生第二行，settle 升 pending / 3.5 确认升 confirmed 均只 UPDATE status（零拷贝、零竞态）。
    # V1 不加 DB CHECK 枚举约束（同项目既有无枚举 CHECK 先例，billing_path 亦无），
    # 值域由 service 保证。
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="draft"
    )
    # 候选卡版本号：settle 首版=1，反馈升版本 +1（AC3）；直接编辑字段不 bump（AC2，受控决策 3）。
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # 本轮变化的字段名列表（snake_case 列名，如 ["protagonist","main_conflict"]），供前端
    # is-updated 高亮「Agent 改了哪些」（AC4）。反馈升版本时写；settle 首版 / 直接编辑为 NULL。
    # JSONB（项目 PG-only）：V1 存字段名数组，够用；结构化 diff 属 V2。
    changed_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
