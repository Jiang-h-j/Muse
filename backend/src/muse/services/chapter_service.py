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

**Story 5.2 扩展**：`finalize_chapter` 内部重写为「定稿 + 写后投影」整体流程
（`finalize_and_project_chapter`），保持函数签名/返回类型不变（router 零改）。投影
失败不卡 status——受控决策 2（status 翻转与投影是两个独立事务）。
"""

import logging
import uuid

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core import sse
from muse.core.db import async_session_maker
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.chapter import Chapter
from muse.models.stage_plan import StagePlan
from muse.orchestration import pipeline
from muse.repositories import (
    chapter_card_repo,
    chapter_generation_repo,
    chapter_repo,
    project_repo,
    stage_plan_repo,
    story_bible_repo,
)
from muse.schemas.readthrough import (
    ReadthroughChapter,
    ReadthroughData,
    ReadthroughProject,
)
from muse.services import chapter_projection_service, embedding_projection_service

READTHROUGH_PER_PAGE = 6
"""通读视图每页段数（Story 6.1 AC2/AC7，与 prototype/app/app.js:4579 常数一致）。

唯一分页粒度参数；前端直接消费后端切好的 pages[i]，不再切页（**陷阱⑧：后端分页，
前端不二次分页**）。若日后调整须同步前端（已约定通读视图不提供分页大小调整入口）。
"""

logger = logging.getLogger("muse")


def _project_not_found() -> ErrorEnvelope:
    """作品不存在 / 不属于我（二义合一 404，NFR3，同 _exploration_not_found）。"""
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在或无权访问。",
        http_status=404,
    )


def _split_pages(text: str, per_page: int = READTHROUGH_PER_PAGE) -> list[list[str]]:
    """把章节正文按每 per_page 段切成 pages[i][j] 二维数组（Story 6.1 AC2/AC7，陷阱⑧）。

    分段规则与前端 4.5 分页阅读「双换行 = 分段」一致（app.js chapterPages()）。
    LLM 产物若只有单换行/无空行（防御），把单换行也视作分段符——不让整章塌成 1 段。
    空章返 []（供前端空态分支识别）。
    """
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n\n" in normalized:
        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    else:
        paragraphs = [p.strip() for p in normalized.split("\n") if p.strip()]
    return [paragraphs[i : i + per_page] for i in range(0, len(paragraphs), per_page)]


async def get_readthrough_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> ReadthroughData:
    """组装通读视图聚合 payload（Story 6.1 AC1/AC4/AC5/AC6/AC7）。

    1. 租户守卫：get_owned_project → None 抛 404 二义合一（NFR3）。
    2. 取本作品**全部**章节（chapter_repo.list_chapters_by_project，按 chapter_number
       升序）；状态二分：status="finalized" 的进 chapters、其他（draft）记 hasUnfinalized=True。
       **读全量内存二分而非两次 SQL**（陷阱⑩）：draft 也要用来标 hasUnfinalized。
    3. 章标题（AC2「第 NN 章 · title」）：chapter 表无 title 列（chapters JSONB 才有），
       按 locate_stage_for_chapter 同款累计法——所有 stage_plan 升序累计 chapters 数，
       第 N 章落在哪一段就取那段 chapters[序号-1].title；缺 title / 无规划 → 「第 N 章」兜底。
    4. 分页（AC7 陷阱⑧）：每章 _split_pages(text, READTHROUGH_PER_PAGE)——后端切好
       pages/totalPages 直发，前端不再二次分页。「双换行分段」与前端 4.5 分页阅读一致。
    5. chapters.length=0 不报错、不 404（AC6 前端空态「还没有可通读的已定稿章节」）。

    返回 ReadthroughData `{project, chapters, totalChapters, hasUnfinalized}`。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()

    all_chapters = await chapter_repo.list_chapters_by_project(
        session, user_id=user_id, project_id=project_id
    )
    stage_plans = await stage_plan_repo.list_all_by_project(
        session, user_id=user_id, project_id=project_id
    )

    # 章号 → 章标题：按阶段累计法定位 stage_plan.chapters 内条目（复用 locate_stage_for_chapter
    # 的累计策略）；chapter_number 超出全部规划时拿不到 title，兜底「第 N 章」。
    chapter_titles: dict[int, str] = {}
    offset = 0
    for plan in stage_plans:
        plan_chapters = plan.chapters or []
        for idx, entry in enumerate(plan_chapters):
            global_number = offset + idx + 1
            title = (entry or {}).get("title") if isinstance(entry, dict) else None
            if title:
                chapter_titles[global_number] = str(title)
        offset += len(plan_chapters)

    finalized: list[ReadthroughChapter] = []
    has_unfinalized = False
    for ch in all_chapters:
        if ch.status == "finalized":
            pages = _split_pages(ch.text or "")
            finalized.append(
                ReadthroughChapter(
                    chapter_number=ch.chapter_number,
                    title=chapter_titles.get(
                        ch.chapter_number, f"第 {ch.chapter_number} 章"
                    ),
                    pages=pages,
                    total_pages=len(pages),
                )
            )
        else:
            has_unfinalized = True

    return ReadthroughData(
        project=ReadthroughProject(title=project.title or "未命名小说"),
        chapters=finalized,
        total_chapters=len(finalized),
        has_unfinalized=has_unfinalized,
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


def _no_stage_plan() -> ErrorEnvelope:
    """触发下一阶段规划前尚无任何阶段规划（→ 400，Story 4.7 AC5 前置）。

    下一阶段规划的前提是已有至少一个阶段规划（首阶段 4.3 已生成、用户写完首阶段末章定稿才走到
    阶段交界触发本端点）。无 stage_plan 行说明连首阶段都没规划——正常 UI 走不到。此校验拦住绕过
    UI 对未规划首阶段的作品直接触发下一阶段规划。
    """
    return ErrorEnvelope(
        code="no_stage_plan",
        message="尚无阶段规划，无法规划下一阶段。",
        http_status=400,
    )


def _chapter_already_finalized() -> ErrorEnvelope:
    """定稿后禁止再改进/重生（→ 400，Story 4.7 review patch F1甲）。

    4.5 前端按钮在 chapterFinalized=true 时已隐藏，但「API 直打 / 多 tab / 前端守卫失效」仍可触达
    revise/regenerate。FR21 字面语义：定稿版本是后续章节创作的正式上下文；改进/重生会写新 text
    且 status 退回 draft——若放行，pipeline 写完 draft 新版覆盖 finalized 行，list_recent_chapters
    下一轮就漏取这章、写前上下文断链。后端硬约束：已 finalized → 400，前端按 code 出可读文案。
    """
    return ErrorEnvelope(
        code="chapter_already_finalized",
        message="本章已定稿，无法再改进或重新生成。",
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
    """读已落库的**当前最新阶段**规划（AC2 重进恢复 + Story 4.7 阶段循环）：租户守卫 →
    get_latest_stage。

    **Story 4.7 起取最新阶段**（stage_number 最大的一行），而非固定首阶段——多阶段循环后前端
    须渲染「当前所处阶段」的章骨架 + 阶段末章判断（用当前阶段章数）。首阶段场景（仅 stage_number=1）
    返回结果与旧行为一致。用请求注入 session（只读，无 provider）。返 None = 尚未生成任何阶段
    规划——router 转 204，前端连 SSE 等就绪。越权/不存在 project → 404 二义合一（NFR3）。

    （函数名保留 first 是历史命名；语义自 4.7 起为「最新阶段」，router GET stage-plan 复用。）
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _project_not_found()
    return await stage_plan_repo.get_latest_stage(
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
    # Story 4.7 review patch F1甲：已 finalized 拒改进/重生（前端 4.5 已隐藏按钮，后端硬约束）。
    # 若放行会让 pipeline 写 draft 覆盖 finalized，下一轮 list_recent_chapters 漏取这章，FR21 破功。
    if existing.status == "finalized":
        raise _chapter_already_finalized()
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


async def finalize_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> Chapter:
    """定稿本章 + 写后投影（Story 4.7 AC1/AC2/AC9 + Story 5.2 AR17/AC2/AC3/AC5）。

    **同步 REST，不调 LLM 不入 ARQ 的部分**：把 chapter.status 置 finalized，返回更新后的
    Chapter——保持函数签名/返回类型不变（router 零改、前端只感知「定稿可能稍慢」）。

    **Story 5.2 写后投影（同步等 data-agent + 单事务投影）**：status 翻 finalized 后，
    调 `pipeline.run_chapter_pipeline(run_data_agent_step=True)` 跑第五段 data-agent 从
    定稿正文提取结构化 JSON，再由 `chapter_projection_service.chapter_commit` 在同一事务
    内投影回 story_state / chapter_card / story_thread。

    **受控决策 2（投影失败 ≠ 定稿失败）**：status 翻转与投影是两个独立事务——先
    `upsert_chapter(status="finalized")` + commit（用户已收到定稿成功响应），再独立事务
    跑 data-agent + chapter_commit；投影失败只记 `logger.exception` + run.steps.data_agent
    标 failed，下次定稿（本章或下一章）触发 data-agent 时断点续跑复用 polisher 段产物
    继续投影。**AC2 的「单事务」约束的是「投影内部三表原子性」，不是「status 翻转与投影
    同一事务」**——两者必须分开，否则投影 LLM 抖动会把 status 卡回 draft（FR21 被破坏）。

    **幂等**：
    - 已 `status=="finalized"` 且 `chapter_card` 已落库 → 直接返回现行（投影已完成、不
      重复跑）。
    - 已 `status=="finalized"` 但 `chapter_card` 缺失 → 视为「上次投影失败」→ 继续走
      投影流程（data-agent 断点续跑会复用 run 表 polisher 段产物，不重新调 drafter）。
    - 仍 `status=="draft"` → 正常走「翻 status + 投影」整体流程。

    **前置校验**（沿用 Story 4.7 逻辑）：
    1. 租户守卫（`get_owned_project` → None 抛 404 二义合一，NFR3）。
    2. confirmed 前置（防御，复用 `_bible_not_confirmed`）：无 confirmed bible → 400。
    3. 章号下界校验：`chapter_number < 1` → 400（防御 API 直打）。**不做 stage_plan 长度
       上界校验**——跨多阶段后章号会超首阶段 chapters 长度。
    4. 本章须已有正文（`get_chapter` None → 400 `chapter_not_generated`）。

    定稿后写前上下文会把本章计入前序（list_recent_chapters 只读 finalized，FR21 兑现）；
    章节卡片持久化后，下一章定稿时 data-agent 会从 run.steps.data_agent 断点续跑复用
    提取产物（不重复付费 NFR5）。
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

    # 章号下界（防御 API 直打）。跨阶段章号连续递增，不做上界校验（避免误拦第二阶段章）。
    if chapter_number < 1:
        raise _chapter_out_of_range()

    # 本章须已有正文（reading 态才有定稿按钮）。无 chapter 行 → 400（拦绕过 UI 对未生成章定稿）。
    existing = await chapter_repo.get_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if existing is None:
        raise _chapter_not_generated()

    # 已成功投影的定稿章节直接幂等返回。此路径不再依赖当前阶段计划，避免后来
    # 重规划、删计划影响已经固定归属的历史章节。
    if existing.status == "finalized":
        card = await chapter_card_repo.get_by_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        if card is not None:
            return existing

    # 首次或补偿投影前固定章节归属。早期旧作品可能已有 chapter 正文却尚未落
    # stage_plan，因此无任何规划时兼容写入第 1 阶段；有规划但目标章越界则拒绝，
    # 且必须在 status=draft → finalized 提交前失败，不能留下错误定稿状态。
    stage_plan = await stage_plan_repo.locate_stage_for_chapter(
        session,
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if stage_plan is None:
        existing_plans = await stage_plan_repo.list_all_by_project(
            session, user_id=user_id, project_id=project_id
        )
        if existing_plans:
            raise _chapter_out_of_range()
        stage_number = 1
    else:
        stage_number = stage_plan.stage_number

    if existing.status == "finalized":
        logger.info(
            "finalize 幂等重入：status 已 finalized 但 chapter_card 缺失，"
            "跳过 status 翻转直接走投影断点续跑：project=%s chapter=%s",
            project_id,
            chapter_number,
        )
        chapter = existing
    else:
        # 只改 status，保留 text/revision（upsert 同键覆盖，不新增行）。
        chapter = await chapter_repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            text=existing.text,
            revision=existing.revision,
            status="finalized",
        )
        await session.commit()

    # ---------- Story 5.2 写后投影（独立事务，投影失败不卡 status） ----------
    # 新开独立事务跑 data-agent + chapter_commit——与上方 status 翻转的 session 分开：
    # ① status 已 finalized 落库，用户已收到定稿成功响应；② 投影失败（LLM 抖动 / DB 写
    # 异常 / JSON 解析失败）只记日志、run.steps.data_agent 标 failed，下次断点续跑复用
    # polisher 段产物继续投影。
    try:
        async with async_session_maker() as projection_session:
            # 1. 跑 data-agent（run_chapter_pipeline 第五段，断点续跑复用产物）：
            #    run_data_agent_step=True 时才跑 data_agent 段；其他四段（context/drafter/
            #    reviewer/polisher）已 succeeded 会直接复用产物、不重复付费。
            await pipeline.run_chapter_pipeline(
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_idea=None,
                on_progress=None,  # finalize 不走 SSE（受控决策 3：同步等 data-agent）
                run_data_agent_step=True,
            )

            # 2. 从 run 表读 data-agent 段产物（dict）。
            run = await chapter_generation_repo.get_run(
                projection_session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
            )
            if run is None or run.steps is None:
                raise RuntimeError(
                    f"data-agent 段产物缺失：project={project_id} chapter={chapter_number} "
                    "run 或 run.steps 为 None"
                )
            data_agent_entry = run.steps.get(pipeline.STEP_DATA_AGENT)
            if (
                data_agent_entry is None
                or data_agent_entry.get("status") != "succeeded"
            ):
                raise RuntimeError(
                    f"data-agent 段产物缺失：project={project_id} chapter={chapter_number} "
                    f"steps.data_agent={data_agent_entry}"
                )
            extracted = data_agent_entry.get("output")
            if not isinstance(extracted, dict):
                raise RuntimeError(
                    f"data-agent 段产物类型异常：project={project_id} chapter={chapter_number} "
                    f"output_type={type(extracted).__name__}"
                )

            # 3. 单事务 chapter-commit 投影三表（任一步抛异常 → 整体 rollback）。
            await chapter_projection_service.chapter_commit(
                projection_session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                stage_number=stage_number,
                extracted=extracted,
            )
            await projection_session.commit()

            logger.info(
                "finalize 投影完成：project=%s chapter=%s",
                project_id,
                chapter_number,
            )

            # ---------- Story 5.5 embedding 投影（三表 commit 后、独立事务、失败降级） ----------
            # 受控决策 3 同构「投影失败 ≠ 定稿失败」：向量化 + 写 embedding 在 chapter_commit 三表
            # 单事务**之外**（provider.embed 是外部 HTTP，在事务外调；写 embedding 行走 project_
            # chapter_embeddings 内部自己的独立事务）。chapter_text 用 existing.text（chapter 表
            # 实际入库的定稿正文，陷阱⑥），非 polisher 产物。
            # 独立 try/except 吞异常：embedding 失败只 warning——三表已 commit、status 已 finalized、
            # 用户已收成功响应；embedding 缺失只降级 5.6 RAG 召回质量（退 tsvector），**不阻断定稿、
            # 不回滚已成功的三表投影**。故不复用外层 except（那会 rollback projection_session）。
            try:
                await embedding_projection_service.project_chapter_embeddings(
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_text=existing.text,
                )
            except Exception:  # noqa: BLE001  embedding 失败不阻断定稿（已记日志、三表已落库）
                logger.warning(
                    "finalize embedding 投影失败（不阻断定稿，三表已落库，RAG 退 tsvector）："
                    "project=%s chapter=%s",
                    project_id,
                    chapter_number,
                    exc_info=True,
                )
    except (RuntimeError, ErrorEnvelope) as exc:
        # 投影失败不向上抛（status 已 finalized 保留）——记日志留审计 + 显式 rollback +
        # 显式标 run.steps.data_agent 为 failed（供下次重入识别），下次定稿（本章或下一章）
        # 触发 data-agent 时断点续跑复用 polisher 段产物继续投影。
        # 只对预期异常（RuntimeError / ErrorEnvelope）吞——其他系统错（如 KeyboardInterrupt）
        # 向上抛不掩盖。
        await projection_session.rollback()
        logger.exception(
            "finalize 投影失败（status 已 finalized 保留，下次断点续跑）："
            "project=%s chapter=%s",
            project_id,
            chapter_number,
            exc_info=exc,
        )
        # 显式标 run.steps.data_agent 为 failed（A8 patch：供下次重入识别，避免
        # run.steps.data_agent 仍显示上次的 succeeded 或不存在导致断点续跑误判）。
        try:
            async with async_session_maker() as run_session:
                run = await chapter_generation_repo.get_run(
                    run_session,
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                )
                if run is not None:
                    await chapter_generation_repo.update_step(
                        run_session,
                        run=run,
                        step_name=pipeline.STEP_DATA_AGENT,
                        status="failed",
                        output="",
                    )
                    await run_session.commit()
        except Exception:  # noqa: BLE001  标 failed 失败不阻断主流程（已记日志）
            logger.warning(
                "finalize 投影失败后标 run.steps.data_agent 为 failed 失败（已忽略）："
                "project=%s chapter=%s",
                project_id,
                chapter_number,
                exc_info=True,
            )

    return chapter


async def trigger_next_stage_planning(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    direction: str | None = None,
) -> str:
    """触发「幕后生成下一阶段规划」ARQ 后台任务（Story 4.7 AC5，FR22）。返回 taskId 供前端连 SSE。

    **仿 trigger_stage_planning**（本文件上文），额外做一件事：
    - 须已有至少一个 stage_plan（`get_latest_stage` None → 400 `_no_stage_plan`）：防未规划首
      阶段就触发下一阶段。正常流程首阶段 4.3 已生成、且用户写完首阶段末章定稿才走到这里。

    `direction` 是阶段交界处用户填的走向意愿（可空=直接继续，让 LLM 按设定+前文自然推进；也可
    是收尾声明）。透传给 worker.plan_next_stage → stage_planner.plan_next_stage 注入规划 prompt。
    触发范式同 trigger_stage_planning：register_task_owner 必先于 enqueue_job（陷阱②）。并发去重
    沿用 deferred-work.md:391 defer（前端按钮点击即时忙碌防单页双击）。
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

    # 须已有至少一个阶段规划（防未规划首阶段就触发下一阶段；正常流程首阶段 4.3 已生成）。
    latest = await stage_plan_repo.get_latest_stage(
        session, user_id=user_id, project_id=project_id
    )
    if latest is None:
        raise _no_stage_plan()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队（陷阱②）。direction 以字符串位置参数传给 worker。
        # **F4a _job_id 去重**：同 project 的 plan_next_stage 复用 job_id，双 tab/重复点击第二次
        # 入队 ARQ 返 None 不重复跑——避免两 worker 都读 latest、都算 next=prev+1、都 INSERT
        # 撞唯一键、last-write-wins 静默覆盖（4.7 review patch F4a）。每 project 一次只允许一个
        # in-flight 下一阶段规划，符合语义（末章定稿 → 交界 → 三按钮之一应只跑一次）；下一阶段再
        # 触发时本 job 已结束可重发。注意：虽 _job_id 复用，ARQ 每次返是否真入队；为简化 service
        # 仍生成新 task_id（pub/sub 频道键+SSE 属主键，不可枚举 uuid4），重复触发时新 task_id 的
        # SSE 频道不会有事件，前端走「无终态兜底」错误态——可接受（重复触发的 client 自兜底）。
        # 真正去重靠 ARQ _job_id。
        await sse.register_task_owner(pool, task_id, uid)
        await pool.enqueue_job(
            "plan_next_stage",
            task_id,
            uid,
            pid,
            direction,
            _job_id=f"{pid}:plan_next_stage",
        )
    finally:
        await pool.aclose()
    return task_id
