"""归档域 DAO：chapter_card（章节卡片）的租户守卫读法 + 写路径（Story 5.1 读 / 5.2 写）。

延续 story_bible_repo / chapter_repo 约定：repo 只 flush/查询，事务边界（commit/
rollback）归 service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供任何
绕过 user_id 的全表查询入口。

**方法分层**：
- `get_by_chapter`（5.1）：按幂等键读，二义合一。
- `upsert_chapter_card`（5.2）：按幂等键 get-or-create 五要素，重跑覆盖同行
  不产生副本——是 5.2 chapter-commit 单事务投影的落点。

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
) -> ChapterCard:
    """get-or-create 落库章节卡五要素（Story 5.2 chapter-commit 投影的落点）。

    - 已存在（重跑 / ARQ 重试 / data-agent 断点续跑复用产物再次投影）：**覆盖五要素**
      不留副本——(user_id, project_id, chapter_number) 复合唯一是幂等键（同 chapter.
      upsert_chapter 先例）。
    - 不存在：新建行。

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
            what_happened=what_happened,
            character_changes=character_changes,
            new_facts_clues=new_facts_clues,
            unresolved_hooks=unresolved_hooks,
            end_state=end_state,
        )
        session.add(card)
    else:
        card.what_happened = what_happened
        card.character_changes = character_changes
        card.new_facts_clues = new_facts_clues
        card.unresolved_hooks = unresolved_hooks
        card.end_state = end_state
    await session.flush()
    await session.refresh(card)
    return card
