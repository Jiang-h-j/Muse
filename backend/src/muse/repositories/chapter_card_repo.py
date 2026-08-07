"""归档域 DAO：chapter_card（章节卡片）的租户守卫读法 + 写路径（Story 5.1 读 / 5.2 写）。

延续 story_bible_repo / chapter_repo 约定：repo 只 flush/查询，事务边界（commit/
rollback）归 service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何
绕过 user_id 的全表查询入口。

**方法分层**：
- `get_by_chapter`（5.1）：按幂等键读，二义合一。
- `upsert_chapter_card`（5.2）：按幂等键 get-or-create 五要素，重跑覆盖同行
  不产生副本——是 5.2 chapter-commit 单事务投影的落点。
- `list_recent_chapter_cards`（5.2）：按章节号取最近前序章节卡——是 data-agent
  输入注入「最近前序 chapter_card 五要素」作上下文锚点。
- `list_by_project`（5.3）：按 project 列出**全部**章节卡（`chapter_number` 升序）。
  供归档页章节卡片列表与阶段分组消费。

**写路径约定（5.2 新增）**：
- 不 commit（commit 边界归 `chapter_projection_service.chapter_commit` 统一事务）。
- 竞态兜底（并发首建撞唯一约束）由 service 层统一处理（rollback → 整事务回滚重试）。
- flush + refresh 回填 id/时间戳（避免 MissingGreenlet，同 story_bible_repo /
  chapter_repo 既有写路径先例）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.chapter_card import ChapterCard


async def get_by_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> ChapterCard | None:
    """按 (user_id, project_id, chapter_number) 一步取本作品的章节卡（二义合一）。

    user_id 与 project_id 写在同一 where 里一次过滤（同 get_owned_project /
    story_bible_repo.get_by_project 先例）：取不到即 None——「该章尚未投影卡」
    与「不属于我」二义合一，调用方（service）统一按需处理，不泄露作品存在性
    （NFR3）。对应 chapter_card 的 (user_id, project_id, chapter_number) 复合
    唯一约束，至多命中一行。
    """
    stmt = select(ChapterCard).where(
        ChapterCard.user_id == user_id,
        ChapterCard.project_id == project_id,
        ChapterCard.chapter_number == chapter_number,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_chapter_card(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    what_happened: str,
    character_changes: str,
    new_facts_clues: str,
    unresolved_hooks: str,
    end_state: str,
    stage_number: int = 1,
) -> ChapterCard:
    """get-or-create 落库章节卡五要素（Story 5.2 chapter-commit 投影的落点）。

    - 已存在（重跑 / ARQ 重试 / data-agent 断点续跑复用产物再次投影）：**覆盖五要素**
      不留副本——(user_id, project_id, chapter_number) 复合唯一是幂等键（同 chapter.
      upsert_chapter 先例）；**保留首次写入的 stage_number**，重规划后重跑不得改历史归属。
    - 不存在：新建行，写入此章定稿时的 stage_number。

    五要素全部必填但允许空串（对齐模型 `Text NOT NULL server_default=""` ——LLM
    某要素产空也能落库不爆约束，由 service 上游空产守卫挡空产）。

    **不 commit**（事务边界归 `chapter_projection_service.chapter_commit` 统一
    事务）。竞态兜底（并发首建撞唯一约束）由 service 层 rollback → 整事务重试。
    flush 后 refresh 回填 id/时间戳（避免 MissingGreenlet）。
    """
    card = await get_by_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if card is None:
        card = ChapterCard(
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            stage_number=stage_number,
            what_happened=what_happened,
            character_changes=character_changes,
            new_facts_clues=new_facts_clues,
            unresolved_hooks=unresolved_hooks,
            end_state=end_state,
        )
        session.add(card)
    else:
        # 迁移前无法回填的旧卡允许首次补齐归属；一旦有值则永久保留，重规划/重试
        # 传入不同 stage_number 也不能移动历史章节。
        if card.stage_number is None:
            card.stage_number = stage_number
        card.what_happened = what_happened
        card.character_changes = character_changes
        card.new_facts_clues = new_facts_clues
        card.unresolved_hooks = unresolved_hooks
        card.end_state = end_state
    await session.flush()
    await session.refresh(card)
    return card


async def list_recent_chapter_cards(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    before_number: int,
    limit: int = 1,
) -> list[ChapterCard]:
    """取本作品编号 < before_number 的最近若干章节卡（Story 5.2 A7 patch：data-agent
    输入注入「最近前序 chapter_card 五要素」作上下文锚点）。

    按 chapter_number 降序取前 limit 章（最近的在前）——V1 默认 limit=1（前一章）。
    第一章无前序 → 空列表（data-agent 提示「这是第一章」）。租户守卫（user_id +
    project_id 二义合一）。
    """
    stmt = (
        select(ChapterCard)
        .where(
            ChapterCard.user_id == user_id,
            ChapterCard.project_id == project_id,
            ChapterCard.chapter_number < before_number,
        )
        .order_by(ChapterCard.chapter_number.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[ChapterCard]:
    """列出本作品**全部**已定稿的章节卡片（`chapter_number` 升序，Story 5.3）。

    按 (user_id, project_id) 取出全部 `chapter_card` 行，升序排列（用户按写作顺序看）。
    租户守卫（user_id + project_id 二义合一），不泄露其他作品能否有卡（NFR3）。

    `stage_number` 在首次投影时固定历史归属；归档 service 直接据该字段分组，不再
    从可变 `stage_plan.chapters` 反推。迁移前无法回填的 NULL 卡由归档 API 单列展示。

    与 `list_recent_chapter_cards` 的区别：本方法不按 `chapter_number` 过滤/排
    before——取全部已定稿章节（而不只取「最近 N 章」），供归档页一次性列表。
    """
    stmt = (
        select(ChapterCard)
        .where(
            ChapterCard.user_id == user_id,
            ChapterCard.project_id == project_id,
        )
        .order_by(ChapterCard.chapter_number.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
