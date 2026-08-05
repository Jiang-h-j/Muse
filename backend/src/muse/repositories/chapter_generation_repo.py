"""章节创作编排域 DAO：chapter_generation_run 的读取与逐段状态更新（Story 4.2，AR11）。

延续 story_bible_repo/project_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service/编排器。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供绕过 user_id 的全表入口。

方法：
- get_run：按幂等键 (user_id, project_id, chapter_number) 取运行记录（断点续跑读状态）。
- create_run：新建运行记录（首次开跑）。竞态兜底（并发首建撞唯一约束）由 service 处理。
- update_step：写某段的状态 + 产物到 steps JSONB（跑完一段即落库供续跑）。
- mark_run_status：更新 run 级状态（running→succeeded/failed）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from muse.models.chapter_generation import ChapterGenerationRun


async def get_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> ChapterGenerationRun | None:
    """按幂等键取本作品本章的运行记录（二义合一，仿 story_bible_repo.get_by_project）。

    user_id + project_id + chapter_number 同一 where 一次过滤：取不到即 None——「无运行记录」
    与「不属于我」二义合一，不泄露存在性（NFR3）。对应表复合唯一约束，至多命中一行。
    """
    stmt = select(ChapterGenerationRun).where(
        ChapterGenerationRun.user_id == user_id,
        ChapterGenerationRun.project_id == project_id,
        ChapterGenerationRun.chapter_number == chapter_number,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_idea: str | None = None,
) -> ChapterGenerationRun:
    """新建运行记录（首次开跑）：status=running（server_default）、steps=None。

    **不 commit**（事务边界归编排器）。flush 后 refresh 回填 id/时间戳（server_default/onupdate
    走 DB func.now()，flush 后属性 expired，下游序列化触发懒加载会抛 MissingGreenlet——仿
    story_bible_repo.upsert_style_profile 的 refresh 处理）。并发首建撞唯一约束的竞态兜底由
    service（rollback→重查）处理，照 style_anchor_agent 先例。
    """
    run = ChapterGenerationRun(
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_idea=chapter_idea,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def update_step(
    session: AsyncSession,
    *,
    run: ChapterGenerationRun,
    step_name: str,
    status: str,
    output: str,
) -> ChapterGenerationRun:
    """写某段的状态 + 产物到 steps JSONB（跑完一段即落库，供断点续跑复用）。

    幂等：同段重写覆盖（重试成功后覆盖旧状态），其余段不受影响。**须 flag_modified**——
    SQLAlchemy 对 JSONB 的**原地字典修改**默认不追踪脏（mutable 未开），不标记则 flush 不写回
    （踩坑：直接 run.steps[k]=v 后 commit 无效）。故 copy → 改 → 整体赋值 + flag_modified。

    **不 commit**（事务边界归编排器）。flush 后 refresh 回填 updated_at。
    """
    steps = dict(run.steps) if run.steps else {}
    steps[step_name] = {"status": status, "output": output}
    run.steps = steps
    flag_modified(run, "steps")
    await session.flush()
    await session.refresh(run)
    return run


async def mark_run_status(
    session: AsyncSession,
    *,
    run: ChapterGenerationRun,
    status: str,
) -> ChapterGenerationRun:
    """更新 run 级状态（running→succeeded/failed）。

    **不 commit**（事务边界归编排器）。flush 后 refresh 回填 updated_at。
    """
    run.status = status
    await session.flush()
    await session.refresh(run)
    return run
