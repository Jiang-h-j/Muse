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
    chapter_generation_repo,
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


def _improve_feedback_required() -> ErrorEnvelope:
    """改进本章无任何反馈（→ 400，Story 4.6 AC1 后端守卫）。

    「改进本章」要求具体反馈（FR20「要求具体反馈并尽量保留现有内容」）：无整体点评且无段落批注
    时无从改起。前端已用 canImprove 禁用按钮（app.js:3112），此校验拦住绕过 UI 的直接调用。
    重生（regenerate）允许空反馈，不走此校验。
    """
    return ErrorEnvelope(
        code="improve_feedback_required",
        message="请先填写整体点评或段落批注，再改进本章。",
        http_status=400,
    )


def _chapter_not_generated() -> ErrorEnvelope:
    """改进/重生前本章尚无已生成正文（→ 400，Story 4.6 前置）。

    改进/重生的前提是本章已生成过正文（reading 态才有修订按钮）。无 chapter 行说明还没生成——
    正常 UI 走不到（input 态无修订按钮）。此校验拦住绕过 UI 对未生成章调修订（真跑流水线真计费、
    且无「上一版正文」可保留）。
    """
    return ErrorEnvelope(
        code="chapter_not_generated",
        message="本章尚未生成，无法改进或重新生成。",
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


async def trigger_chapter_revision(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    action: str,
    feedback: str | None = None,
    annotations: list[dict] | None = None,
) -> str:
    """触发「改进本章 / 重新生成整章」ARQ 后台任务（Story 4.6）。返回 taskId 供前端连 SSE。

    **完整仿 trigger_chapter_generation**（本文件上文），额外做三件事：
    1. 改进守卫（AC1）：action="improve" 且 feedback 空白且 annotations 空 → 400
       improve_feedback_required（重生 action="regenerate" 不校验，允许空反馈）。
    2. 前置：本章须已有正文（get_chapter None → 400 chapter_not_generated）；读出旧 revision
       供递增（target_revision = 旧 + 1）、读出旧正文 previous_text 供改进注入。
    3. **强制重跑（AC3 核心）**：reset_run 作废旧 chapter_generation_run（清 steps + status→
       running），使 worker 里 run_chapter_pipeline 重跑全四段而非复用旧 succeeded 终稿。

    触发范式同 trigger_chapter_generation：register_task_owner 必先于 enqueue_job（陷阱②）。
    并发去重/限流沿用 deferred-work.md:391 defer（本 story 不做，前端按钮 disabled 防单页双击）。
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

    # 章号范围校验（防御 API 直打，同 trigger_chapter_generation）。
    if chapter_number < 1:
        raise _chapter_out_of_range()
    stage_plan = await stage_plan_repo.get_stage_plan(
        session, user_id=user_id, project_id=project_id
    )
    chapters = (stage_plan.chapters if stage_plan else None) or []
    if chapter_number > len(chapters):
        raise _chapter_out_of_range()

    # 改进守卫（AC1）：改进须有反馈（整体点评或段落批注其一）；重生允许空反馈。
    normalized_annotations = annotations or []
    has_feedback = bool((feedback or "").strip())
    has_annotations = bool(normalized_annotations)
    if action == "improve" and not has_feedback and not has_annotations:
        raise _improve_feedback_required()

    # 前置：本章须已生成正文（reading 态才有修订按钮）。读旧 revision 递增 + 旧正文供改进注入。
    existing = await chapter_repo.get_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if existing is None:
        raise _chapter_not_generated()
    target_revision = existing.revision + 1
    previous_text = existing.text

    # 强制重跑（AC3 核心）：作废旧 run（清 steps + status→running），使 pipeline 重跑全四段。
    # **不覆盖 chapter_idea**（code review 修）：改进/重生的反馈都经 revision_input 单独注入
    # （worker→pipeline→context-agent 的 revision_block，且 revision_input 随 ARQ job 参数持久化、
    # 重入一致）。若把 feedback 写进 run.chapter_idea，pipeline 的 effective_idea 会让 context-agent
    # 的 idea_block 与 revision_block **双重渲染同段 feedback**、语义标签冲突。保留原 chapter_idea
    # （首次生成的本章想法）作背景即可。无 run 行（正文存在但 run 缺失，如迁移残留）→ 不 reset
    # （pipeline 会新建 run 重跑），不阻断。
    run = await chapter_generation_repo.get_run(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if run is not None:
        await chapter_generation_repo.reset_run(session, run=run)
    await session.commit()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # revise_chapter 任务参数：action/feedback/annotations（JSON-safe list[dict]）+
        # previous_text（改进注入用）+ target_revision（落库版本号）。_job_id=task_id 不去重
        # （同 generate_chapter，并发缺口沿用 deferred-work.md:391 defer）。
        await pool.enqueue_job(
            "revise_chapter",
            task_id,
            uid,
            pid,
            chapter_number,
            action,
            feedback,
            normalized_annotations,
            previous_text,
            target_revision,
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
    """读已落库的章节终稿正文（AC6 重进恢复）：租户守卫 → chapter_repo.get_chapter.

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
