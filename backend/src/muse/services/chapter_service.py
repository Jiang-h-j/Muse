"""章节创作业务编排（Story 4.3，AR2：业务在 service，不在 router）。

本 story 提供两个入口（均挂 project 层级）：
- trigger_stage_planning：confirm 成功后触发「幕后生成首个阶段规划」ARQ 任务（AC1/AC6）。
  返回 taskId 供前端连 SSE（POST→taskId→GET /api/tasks/{taskId}/events），confirm 端点/事务
  不被 LLM 阻塞（FR17 用户体感直接进第一章）。触发前做租户守卫 + confirmed 前置校验（不给
  未确认作品排任务）。真实生成在 worker `plan_first_stage`（stage_planner.plan_first_stage）。
- get_first_stage_plan：读已落库的首个阶段规划（AC2 重进恢复 / 断线可恢复）。有则返回、无则
  None——前端进第一章时先拉一次：已生成直接渲染侧栏，未生成则连 SSE 等幕后任务就绪。

**触发范式**照 exploration_service.trigger_guided_settle：create_pool → register_task_owner
（**必先于** enqueue_job，否则 SSE 鉴权 404）→ enqueue_job(name, task_id, uid, pid,
_job_id=task_id) → aclose。租户守卫二义合一 404（NFR3）。事务边界在此层（repo 只 flush）。
"""

import uuid

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core import sse
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.chapter import Chapter
from muse.models.stage_plan import StagePlan
from muse.repositories import (
    chapter_repo,
    project_repo,
    stage_plan_repo,
    story_bible_repo,
)


def _project_not_found() -> ErrorEnvelope:
    """作品不存在 / 不属于我（二义合一 404，NFR3，同 _exploration_not_found）。"""
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在或无权访问。",
        http_status=404,
    )


def _bible_not_confirmed() -> ErrorEnvelope:
    """设定圣经未确认（规划前置未满足 → 400，复用 4.2 steps.py:64 语义）。

    触发阶段规划前校验：无 confirmed 行说明还没确认设定，不该为其排幕后任务。本 story 触发点
    在 confirm 成功后，理论上必有 confirmed 行——此校验为防御（防前端在未确认时误调触发端点）。
    """
    return ErrorEnvelope(
        code="bible_not_confirmed",
        message="请先确认故事设定，再开始创作章节。",
        http_status=400,
    )


def _chapter_out_of_range() -> ErrorEnvelope:
    """章号非法或超出当前阶段规划范围（→ 400）。

    防御 API 直打：路由 int 转换器放行 0 与任意大整数（负数走 404）。生成一个 < 1 或不在
    stage_plan.chapters 范围内的章号会真跑四段流水线真计费、并 upsert 污染 chapter 业务表
    （生成阶段规划里根本不存在的「章」）。前端只在 stage_plan 有对应章时渲染生成表单，正常 UI
    走不到——此校验拦住绕过 UI 的直接调用。
    """
    return ErrorEnvelope(
        code="chapter_out_of_range",
        message="该章节不在当前阶段规划范围内。",
        http_status=400,
    )


async def trigger_stage_planning(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> str:
    """触发「幕后生成首个阶段规划」ARQ 后台任务（AC1/AC6）。返回 taskId 供前端连 SSE。

    1. 租户守卫（陷阱①）：get_owned_project → None 抛 404（二义合一，NFR3）。
    2. confirmed 前置（防御）：无 confirmed bible → 400 bible_not_confirmed（不给未确认作品
       排任务；正常流程 confirm 成功后触发，必有 confirmed 行）。
    3. taskId = uuid4 hex（不可枚举，陷阱⑤，与 tasks.py:38 同款）。
    4. register_task_owner **必须在 enqueue_job 之前**（陷阱②，tasks.py:43-47 已论证）：否则
       worker 可能在属主键写入前就发首个事件、SSE 端点鉴权读不到属主而对合法属主误返 404。
    5. ARQ pool 每次 create_pool + aclose（照 exploration_service.trigger_guided_settle 范式）；
       user_id/project_id 以 str 位置参数传给 worker（plan_first_stage 自读设定生成）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()

    # confirmed 前置校验（防御）：正常流程 confirm 后触发必有 confirmed 行。
    bible = await story_bible_repo.get_confirmed_by_project(
        session, user_id=user_id, project_id=project_id
    )
    if bible is None:
        raise _bible_not_confirmed()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # _job_id=task_id：stable id 作 pubsub 频道键；user_id/project_id 传给 worker 供生成。
        await pool.enqueue_job(
            "plan_first_stage", task_id, uid, pid, _job_id=task_id
        )
    finally:
        await pool.aclose()
    return task_id


async def get_first_stage_plan(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> StagePlan | None:
    """读已落库的首个阶段规划（AC2 重进恢复）：租户守卫 → get_stage_plan（首阶段=1）。

    用请求注入 session（只读，无 provider）。返 None = 尚未生成（幕后任务未完成 / 未触发）——
    router 转 204，前端连 SSE 等就绪。越权/不存在 project → 404 二义合一（NFR3）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()
    return await stage_plan_repo.get_stage_plan(
        session, user_id=user_id, project_id=project_id
    )


async def trigger_chapter_generation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_idea: str | None = None,
) -> str:
    """触发「真实生成章节正文」ARQ 后台任务（Story 4.4 AC1/AC5）。返回 taskId 供前端连 SSE。

    **完整仿 trigger_stage_planning**（本文件上文）：
    1. 租户守卫：get_owned_project → None 抛 404（二义合一，NFR3）。
    2. confirmed 前置（防御）：无 confirmed bible → 400 bible_not_confirmed（不给未确认作品
       排生成任务；正常流程确认设定后才进创作）。
    3. taskId = uuid4 hex（不可枚举，与 tasks.py:38 同款）。
    4. register_task_owner **必须在 enqueue_job 之前**（陷阱②）：否则 SSE 端点鉴权读不到属主。
    5. ARQ pool 每次 create_pool + aclose；chapter_number（位置）+ chapter_idea 透传给
       worker.generate_chapter（worker.py:195-202 签名：ctx, task_id, user_id, project_id,
       chapter_number, chapter_idea=None）。真实生成在 pipeline.run_chapter_pipeline（幂等
       可断点续跑；重复触发同章复用同 run，不重复付费 NFR5）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()

    # confirmed 前置校验（防御）：正常流程确认设定后才进创作，必有 confirmed 行。
    bible = await story_bible_repo.get_confirmed_by_project(
        session, user_id=user_id, project_id=project_id
    )
    if bible is None:
        raise _bible_not_confirmed()

    # 章号范围校验（防御 API 直打）：chapter_number 须 >= 1 且落在首个阶段规划的章数范围内。
    # 无阶段规划（尚未生成）时也拦——不给「阶段规划都没有」的作品排生成任务。前端正常流程只在
    # stage_plan 有对应章时才渲染生成表单，此校验拦住绕过 UI 的越界调用（防真计费 + 污染业务表）。
    if chapter_number < 1:
        raise _chapter_out_of_range()
    stage_plan = await stage_plan_repo.get_stage_plan(
        session, user_id=user_id, project_id=project_id
    )
    chapters = (stage_plan.chapters if stage_plan else None) or []
    if chapter_number > len(chapters):
        raise _chapter_out_of_range()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # _job_id=task_id：task_id 作 pubsub 频道键 + SSE 属主键（不可枚举 uuid4）。
        # **注意**：task_id 每次调用都是全新 uuid4，故 _job_id 并不提供「同章重复触发去重」——
        # 两次并发触发会产生两个不同 _job_id、两条并行 pipeline、双倍 LLM 计费（与 2.1/2.5/3.3
        # 触发端点同款全项目共性缺口，deferred-work.md「Story 4.4」+ L163/191/208 已登记，归开放
        # 注册前加固批次：前端提交去重 + 触发端点限流 + 稳定 _job_id / run 级并发锁）。
        # chapter_number 位置参数、chapter_idea 传入。
        await pool.enqueue_job(
            "generate_chapter",
            task_id,
            uid,
            pid,
            chapter_number,
            chapter_idea,
            _job_id=task_id,
        )
    finally:
        await pool.aclose()
    return task_id


async def get_chapter_text(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> Chapter | None:
    """读已落库的章节终稿正文（AC6 重进恢复）：租户守卫 → chapter_repo.get_chapter。

    用请求注入 session（只读，无 provider）。返 None = 尚未生成（生成任务未完成 / 未触发）——
    router 转 204，前端连 SSE 等就绪或显示 input 态。越权/不存在 project → 404 二义合一（NFR3）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()
    return await chapter_repo.get_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
