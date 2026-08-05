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
    ChapterTextResponse,
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
