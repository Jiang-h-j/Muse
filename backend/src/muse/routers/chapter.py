"""章节创作路由（Story 4.3，AR2：router 仅校验入参 + 分发，业务在 chapter_service）。

章节创作挂在 project 层级下（prefix /api/projects）：
- POST /{project_id}/chapters/plan-stage：触发「幕后生成首个阶段规划」ARQ 任务（AC1/AC6）——
  前端 confirm 成功后调用，返 200 + taskId，前端连 2.1 的 GET /api/tasks/{taskId}/events
  消费 SSE。confirm 端点/事务不被 LLM 阻塞（FR17）；触发前租户守卫 + confirmed 前置校验。
- GET  /{project_id}/chapters/stage-plan：取已落库的首个阶段规划（AC2 重进恢复）——有则返
  200 + 阶段规划、无则 204（尚未生成，前端连 SSE 等就绪）。

**非流式提交**（同 explore/settle）：POST 返 taskId，SSE 消费端点由 2.1 已建、本 story 复用
不重建。依赖 CurrentUser 自动完成 access token 校验并取当前 User；操作绑定 current_user.id
实现租户隔离；越权/不存在同码 404（业务在 service）。
"""

import uuid

from fastapi import APIRouter, Response

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.chapter import (
    ChapterGenerateRequest,
    ChapterReviseRequest,
    ChapterTextResponse,
    NextStagePlanRequest,
    StagePlanResponse,
)
from muse.schemas.task import TaskSubmitResponse
from muse.services import chapter_service

router = APIRouter(prefix="/api/projects", tags=["chapter"])


@router.post(
    "/{project_id}/chapters/plan-stage", response_model=TaskSubmitResponse
)
async def plan_stage(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> TaskSubmitResponse:
    """触发幕后生成首个阶段规划（AC1/AC6）：提交语义，返 200 + taskId。

    **无 body**（触发即规划，所需数据由任务从库读 confirmed 设定；project_id 已在路径）。前端在
    confirm 成功、跳第一章后调用本端点拿 taskId，再连 GET /api/tasks/{taskId}/events 消费 SSE
    progress/result（幕后无阻塞，FR17）。租户 404 / 未确认设定 400 由 service 抛 ErrorEnvelope
    交全局 handler；project_id 非法 UUID 由 FastAPI 自动 422。
    """
    task_id = await chapter_service.trigger_stage_planning(
        session, user_id=current_user.id, project_id=project_id
    )
    return TaskSubmitResponse(task_id=task_id)


@router.get("/{project_id}/chapters/stage-plan")
async def get_stage_plan(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    """取已落库的首个阶段规划（AC2 重进恢复）：有则返 200 + 规划、无返 204。

    进第一章时前端先 GET 一次：已生成直接渲染侧栏，未生成（204）则连 SSE 等幕后任务就绪
    （刷新/断线重进不重新生成）。越权/不存在 project → service 抛 404（二义合一）。
    """
    plan = await chapter_service.get_first_stage_plan(
        session, user_id=current_user.id, project_id=project_id
    )
    if plan is None:
        return Response(status_code=204)
    body = StagePlanResponse(
        stage_number=plan.stage_number,
        goal=plan.goal,
        chapters=plan.chapters or [],
    )
    return Response(
        content=body.model_dump_json(by_alias=True),
        media_type="application/json",
    )


@router.post(
    "/{project_id}/chapters/plan-next-stage", response_model=TaskSubmitResponse
)
async def plan_next_stage(
    project_id: uuid.UUID,
    payload: NextStagePlanRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> TaskSubmitResponse:
    """触发幕后生成下一阶段规划（Story 4.7 AC5，FR22）：提交语义，返 200 + taskId。

    body 收可选阶段交界方向（direction）：非空=带方向写下去、空/None=直接继续、收尾声明=规划
    收尾阶段。前端在阶段末章定稿后进阶段交界页，点三按钮之一调本端点拿 taskId，再连
    GET /api/tasks/{taskId}/events 消费 SSE progress/result（幕后无阻塞 FR17，就绪后进下一阶段
    首章）。真实生成走 stage_planner.plan_next_stage（读上一阶段+设定 → LLM 出下一阶段规划）。
    租户 404 / 未确认设定 400 / 无阶段规划 400 no_stage_plan 由 service 抛 ErrorEnvelope 交全局
    handler；project_id 非法由 FastAPI 自动 422。

    **路由顺序**：静态段 plan-next-stage 声明在动态 {chapter_number} 段之前——不会被 int 转换器
    吞（同 plan-stage/stage-plan 静态段范式）。
    """
    task_id = await chapter_service.trigger_next_stage_planning(
        session,
        user_id=current_user.id,
        project_id=project_id,
        direction=payload.direction,
    )
    return TaskSubmitResponse(task_id=task_id)


@router.post(
    "/{project_id}/chapters/{chapter_number}/generate",
    response_model=TaskSubmitResponse,
)
async def generate_chapter(
    project_id: uuid.UUID,
    chapter_number: int,
    payload: ChapterGenerateRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> TaskSubmitResponse:
    """触发真实生成章节正文（AC1/AC3/AC5）：提交语义，返 200 + taskId。

    body 收可选本章想法（chapterIdea，可留空 = 跳过并生成）。前端在 input 态点「生成本章/跳过
    并生成」调用本端点拿 taskId，再连 GET /api/tasks/{taskId}/events 消费 SSE progress/result
    （NFR2 异步，不阻塞、不轮询）。真实生成走 4.2 四段流水线（幂等断点续跑）。租户 404 / 未确认
    设定 400 由 service 抛 ErrorEnvelope 交全局 handler；project_id/chapter_number 非法由
    FastAPI 自动 422。
    """
    task_id = await chapter_service.trigger_chapter_generation(
        session,
        user_id=current_user.id,
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_idea=payload.chapter_idea,
    )
    return TaskSubmitResponse(task_id=task_id)


@router.post(
    "/{project_id}/chapters/{chapter_number}/revise",
    response_model=TaskSubmitResponse,
)
async def revise_chapter(
    project_id: uuid.UUID,
    chapter_number: int,
    payload: ChapterReviseRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> TaskSubmitResponse:
    """触发「改进本章 / 重新生成整章」（Story 4.6）：提交语义，返 200 + taskId。

    body：action="improve"（改进本章，须有整体点评或段落批注，尽量保留现有内容）/"regenerate"
    （重新生成整章，允许空反馈、替换整章）。feedback = 整体点评；annotations = 段落批注列表
    （改进消费、重生忽略）。前端在 reading 态点「改进本章 →」/「重新生成」调用本端点拿 taskId，
    再连 GET /api/tasks/{taskId}/events 消费 SSE progress/result（result 带新 chapterText +
    revision）。改进/重生**强制重跑** 4.2 四段流水线（作废旧 run、不复用旧终稿），版本号递增、
    覆盖同行、不留历史（Jianghj 2026-08-05 决议）。

    租户 404 / 未确认设定 400 / 改进无反馈 400 improve_feedback_required / 本章未生成 400
    chapter_not_generated 由 service 抛 ErrorEnvelope 交全局 handler；非法入参由 FastAPI 自动 422。
    """
    annotations = (
        [a.model_dump() for a in payload.annotations]
        if payload.annotations
        else []
    )
    task_id = await chapter_service.trigger_chapter_revision(
        session,
        user_id=current_user.id,
        project_id=project_id,
        chapter_number=chapter_number,
        action=payload.action,
        feedback=payload.feedback,
        annotations=annotations,
    )
    return TaskSubmitResponse(task_id=task_id)


@router.post(
    "/{project_id}/chapters/{chapter_number}/finalize",
    response_model=ChapterTextResponse,
)
async def finalize_chapter(
    project_id: uuid.UUID,
    chapter_number: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> ChapterTextResponse:
    """定稿本章（Story 4.7 AC1，FR21）：**同步 REST**，直接返回定稿后的章节资源体。

    **无 body**（定稿只改 status、不调 LLM、不入 ARQ、无需 SSE）。前端在 reading 态点「定稿本章 →」
    调本端点，成功后本章 status=finalized——成为后续章节创作的正式上下文（list_recent_chapters
    只读 finalized）、前端隐藏批注/改进按钮。**幂等**：已定稿再调返回同状态、不报错。

    租户 404 / 未确认设定 400 / 本章未生成 400 chapter_not_generated / 章号 <1 chapter_out_of_range
    由 service 抛 ErrorEnvelope 交全局 handler；project_id/chapter_number 非法由 FastAPI 自动 422。
    写后投影 + 章节卡片归 Epic 5 Story 5.2（本端点只置 status）。
    """
    chapter = await chapter_service.finalize_chapter(
        session,
        user_id=current_user.id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    return ChapterTextResponse(
        chapter_number=chapter.chapter_number,
        chapter_text=chapter.text,
        revision=chapter.revision,
        status=chapter.status,
    )


@router.get("/{project_id}/chapters/{chapter_number}")
async def get_chapter(
    project_id: uuid.UUID,
    chapter_number: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    """取已落库的章节终稿正文（AC6 重进恢复）：有则返 200 + 正文、无返 204。

    进第一章 / 刷新时前端先 GET 一次：已生成直接渲染 reading 态，未生成（204）则连 SSE 等就绪
    或显示 input 态（不重新生成）。越权/不存在 project → service 抛 404（二义合一）。

    **路由顺序**：本动态路由声明在 GET /chapters/stage-plan 之后——静态段 stage-plan 先匹配，
    不会被 {chapter_number} 吞（chapter_number 类型为 int，"stage-plan" 也匹配不进本路由）。
    """
    chapter = await chapter_service.get_chapter_text(
        session,
        user_id=current_user.id,
        project_id=project_id,
        chapter_number=chapter_number,
    )
    if chapter is None:
        return Response(status_code=204)
    body = ChapterTextResponse(
        chapter_number=chapter.chapter_number,
        chapter_text=chapter.text,
        revision=chapter.revision,
        status=chapter.status,
    )
    return Response(
        content=body.model_dump_json(by_alias=True),
        media_type="application/json",
    )
