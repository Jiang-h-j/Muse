"""章节创作业务域 DAO：chapter 的读取、upsert 与前序章节列举（Story 4.4）。

延续 story_bible_repo/stage_plan_repo/chapter_generation_repo 约定：repo 只 flush/查询，事务
边界（commit/rollback）归 service/编排器。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供
绕过 user_id 的全表入口。

方法：
- get_chapter：按幂等键 (user_id, project_id, chapter_number) 取章节正文（重进恢复读）。
- upsert_chapter：get-or-create 落库终稿正文（生成完成后写；重生成覆盖同行、升版本）。
- list_recent_chapters：取本作品编号 < before_number 的最近若干**已定稿**章（context-agent
  写前上下文注入前序章节，AC4）。按 chapter_number 降序、limit N，只取 status='finalized'
  （Story 4.7 FR21）。
- list_chapters_by_project：取本作品全部章节（Story 6.1 通读视图组装已定稿章节 + hasUnfinalized
  标记），按 chapter_number 升序。status 过滤交调用方（service），repo 不预定 finalized。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.chapter import Chapter


async def get_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> Chapter | None:
    """按幂等键取本作品本章的终稿正文（二义合一，仿 chapter_generation_repo.get_run）。

    user_id + project_id + chapter_number 同一 where 一次过滤：取不到即 None——「无正文」与
    「不属于我」二义合一，不泄露存在性（NFR3）。对应表复合唯一约束，至多命中一行。
    """
    stmt = select(Chapter).where(
        Chapter.user_id == user_id,
        Chapter.project_id == project_id,
        Chapter.chapter_number == chapter_number,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    text: str,
    revision: int = 1,
    status: str = "draft",
) -> Chapter:
    """get-or-create 落库终稿正文（生成完成后写）：存在则覆盖、不存在则新建行。

    - 已存在（重生成 / ARQ 重试 / 重入复用 succeeded run）：更新 text（幂等——同键重写覆盖不
      新增行，保证「重进不重生成」与重试不产生正文副本）。revision/status 仅在显式传入时覆盖
      （4.4 恒 revision=1/status=draft；4.6 升版、4.7 定稿复用本方法传新值）。
    - 不存在：新建行。

    **不 commit**（事务边界归编排器，与既有 repo 约定一致）。首次并发 insert 撞唯一约束的竞态
    兜底由调用方处理（rollback→重查，照 pipeline.run_chapter_pipeline get-or-create 先例）。
    flush 后 refresh 回填 id/时间戳（避免 MissingGreenlet，同 chapter_generation_repo.create_run）。
    """
    chapter = await get_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if chapter is None:
        chapter = Chapter(
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            text=text,
            revision=revision,
            status=status,
        )
        session.add(chapter)
    else:
        chapter.text = text
        chapter.revision = revision
        chapter.status = status
    await session.flush()
    await session.refresh(chapter)
    return chapter


async def list_recent_chapters(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    before_number: int,
    limit: int = 1,
) -> list[Chapter]:
    """取本作品编号 < before_number 的最近若干已定稿章（写前上下文注入前序章节，AC4）。

    按 chapter_number 降序取前 limit 章（最近的在前）——V1 默认 limit=1（前一章）。**只注入
    status='finalized' 的章节**（Story 4.7 FR21：定稿后当前版本才成为后续章节创作的正式上下文；
    未定稿 draft 不注入，Jianghj 2026-08-05 裁决②）。租户守卫（user_id + project_id）。第一章
    无前序、或前序均未定稿时返空列表（context-agent 仅用全量设定，行为不崩）。
    """
    stmt = (
        select(Chapter)
        .where(
            Chapter.user_id == user_id,
            Chapter.project_id == project_id,
            Chapter.chapter_number < before_number,
            Chapter.status == "finalized",
        )
        .order_by(Chapter.chapter_number.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_chapters_by_project(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[Chapter]:
    """按 (user_id, project_id) 列出全章节，按 chapter_number 升序（Story 6.1）。

    通读视图消费：service 取全量后自行二分（finalized 入 chapters 数组、其他状态置
    hasUnfinalized=True）。**status 不在 repo 层过滤**——service 需要同时拿到两种状态，
    若 repo 只查 finalized 则需两次 SQL。租户守卫（user_id + project_id 双条件，NFR3）。
    无章节时返空列表（新作品 / 全未生成）。
    """
    stmt = (
        select(Chapter)
        .where(
            Chapter.user_id == user_id,
            Chapter.project_id == project_id,
        )
        .order_by(Chapter.chapter_number.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
