"""章节创作编排域 DAO：stage_plan 的读取与 upsert（Story 4.3，FR17）。

延续 story_bible_repo/chapter_generation_repo 约定：repo 只 flush/查询，事务边界
（commit/rollback）归 service。所有查询显式绑定 user_id 租户守卫（NFR3）——不提供绕过
user_id 的全表入口。

方法：
- get_stage_plan：按幂等键 (user_id, project_id, stage_number) 取阶段规划（重进恢复读）。
- get_latest_stage：取本作品当前最新阶段规划（stage_number 最大的一行，Story 4.7 阶段循环）。
- upsert_stage_plan：get-or-create 落库阶段规划（幕后任务生成完成后写；重生成覆盖同行）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.stage_plan import StagePlan


async def get_stage_plan(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    stage_number: int = 1,
) -> StagePlan | None:
    """按幂等键取本作品本阶段的规划（二义合一，仿 chapter_generation_repo.get_run）。

    user_id + project_id + stage_number 同一 where 一次过滤：取不到即 None——「无阶段规划」
    与「不属于我」二义合一，不泄露存在性（NFR3）。对应表复合唯一约束，至多命中一行。
    stage_number 默认 1（本 story 只有首阶段）。
    """
    stmt = select(StagePlan).where(
        StagePlan.user_id == user_id,
        StagePlan.project_id == project_id,
        StagePlan.stage_number == stage_number,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_stage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StagePlan | None:
    """取本作品当前最新阶段规划（stage_number 最大的一行，Story 4.7 阶段循环）。

    按 stage_number 降序取第一行——多阶段循环后返回「当前所处阶段」的规划（前端渲染当前阶段章
    骨架 + 阶段末章判断、下一阶段规划读上一阶段承接）。租户守卫（user_id + project_id）。无任何
    阶段规划返 None（连首阶段都没生成）。
    """
    stmt = (
        select(StagePlan)
        .where(
            StagePlan.user_id == user_id,
            StagePlan.project_id == project_id,
        )
        .order_by(StagePlan.stage_number.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_stage_plan(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    goal: str,
    chapters: list[dict[str, str]],
    stage_number: int = 1,
) -> StagePlan:
    """get-or-create 落库阶段规划（生成完成后写）：存在则覆盖、不存在则新建行。

    - 已存在（重生成 / 重入）：更新 goal + chapters（幂等——同键重写覆盖不新增行，保证「重进
      不重生成」的落库侧一致；重生成场景后续 story 可复用）。
    - 不存在：新建行（stage_number 默认 1）。

    **不 commit**（事务边界归 service，与既有 repo 约定一致）。首次并发 insert 撞唯一约束的
    竞态兜底由 service 处理（rollback→重查转 UPDATE，照 story_settle_agent/pipeline 先例）。
    flush 后 refresh 回填 id/时间戳（避免 MissingGreenlet，同 chapter_generation_repo.create_run）。
    """
    plan = await get_stage_plan(
        session,
        user_id=user_id,
        project_id=project_id,
        stage_number=stage_number,
    )
    if plan is None:
        plan = StagePlan(
            user_id=user_id,
            project_id=project_id,
            stage_number=stage_number,
            goal=goal,
            chapters=chapters,
        )
        session.add(plan)
    else:
        plan.goal = goal
        plan.chapters = chapters
    await session.flush()
    await session.refresh(plan)
    return plan
