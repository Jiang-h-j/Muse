"""探索路由（AR2：router 仅校验入参 + 分发，业务在 exploration_service / explorer_agent）。

探索挂在 project 层级下（prefix /api/projects）：
- POST /{project_id}/explore：进入探索（get-or-create 语义，Story 2.2）。
- POST /{project_id}/explore/guided/interpret：引导自述理解流式 SSE（Story 2.3 AC4）——真实
  Explorer Agent 把用户一句话自述凝练为该题答案，逐块 SSE 推送 delta→done→error。
- POST /{project_id}/explore/guided/answers：保存/更新某题位引导答案（Story 2.4，幂等 upsert 200）。
- GET  /{project_id}/explore/guided/answers：恢复本会话全部已答（Story 2.4，题位升序，空态 []）。
- POST /{project_id}/explore/guided/settle：引导收尾触发「整理为故事设定」ARQ 后台任务（Story 2.5
  AC2）——租户守卫 + 登记属主 + 入队 settle_guided_exploration，返 taskId，前端连 2.1 的
  GET /api/tasks/{taskId}/events 消费 SSE（progress/占位 result/error）。非流式提交（非 interpret
  的 EventSourceResponse）——异步模型二分 epics.md:457：settle 走 ARQ 后台任务、interpret 走流式。

依赖 CurrentUser 自动完成 access token 校验并取当前 User；未登录/token 失效在依赖内 401。
所有操作绑定 current_user.id 实现租户隔离；越权/不存在同码 404（业务在 service）。

交互式流式（受控决策 B，epics.md:457）：interpret 走**直连 provider.stream** 逐块推
（EventSourceResponse over async gen），**不走 ARQ 的 POST→taskId→GET /events 那套**（那是批量
后台任务模式，2.5/2.7 用）——故不引入 Redis/worker，仅复用 core/sse.format_sse_event 纯编码。
"""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from muse.core import sse
from muse.core.deps import CurrentUser, SessionDep
from muse.core.errors import ErrorEnvelope, logger
from muse.schemas.exploration import (
    ExplorationSessionResponse,
    GuidedAnswerRequest,
    GuidedAnswerResponse,
    GuidedInterpretRequest,
)
from muse.schemas.task import TaskSubmitResponse
from muse.services import exploration_service, explorer_agent

router = APIRouter(prefix="/api/projects", tags=["exploration"])


@router.post("/{project_id}/explore", response_model=ExplorationSessionResponse)
async def enter_exploration(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> ExplorationSessionResponse:
    # get-or-create 幂等入口，返 200（而非恒新建的 201，陷阱⑦）：重复进入/刷新返同一会话。
    # 无 body（AC2）——mode 恒取 project.mode，客户端不传；project_id 非法 UUID 由 FastAPI 自动 422。
    # 越权/不存在在 service 统一 404（陷阱①）。
    exploration = await exploration_service.enter_exploration(
        session, user_id=current_user.id, project_id=project_id
    )
    return ExplorationSessionResponse.model_validate(exploration)


def _interpret_event_stream(
    *, user_id: uuid.UUID, project_id: uuid.UUID, question: str, free_text: str
) -> AsyncIterator[dict[str, str]]:
    """把 Explorer Agent 的正文增量编码为 SSE 事件流：delta×N → done →（异常时）error。

    - delta：正文增量，payload `{text: <片段>}`，逐块推给前端实时拼接。
    - done：终态，payload `{text: <完整凝练答案>}`，供前端把该题答案纳入探索。
    - error：流已开始后（HTTP 200 已提交、状态码不可改）现实化的错误经此推送，分三类：
      · 结构化业务错误（ErrorEnvelope，如独立 session 重校验时护栏触顶、provider 明确 5xx）：
        透传其面向用户的 `{code, message}`——与预检阶段 HTTP 错误 envelope 同源（三要素本
        就面向用户、不含内部细节），前端可按 code 分支（如 quota_exceeded 引导绑 key）。
      · 未预期异常（Exception，如断连/未知错误）：**泛化**为 generate_failed + 通用文案，
        原始 exc 只 logger.exception 记录、不外泄（承 2.1 patch「内部信息不外泄」）。
      · 空产兜底：流正常结束却无任何正文（推理档把 max_tokens 吃光挤空正文的残留，陷阱⑥）
        ——不发空 done（否则前端把空答案纳入该题），改发 generate_failed error 让用户重试。
    流建立前的错误（租户 404/护栏 429）已在端点预检阶段走 HTTP 状态，不到这里（Task 3 错误映射）。

    payload camelCase（architecture.md:336）；复用 core/sse.format_sse_event 纯 JSON 编码。
    reasoning 片段在 explorer_agent 内已静默丢弃，此处只见 content 正文。
    """

    async def _gen() -> AsyncIterator[dict[str, str]]:
        parts: list[str] = []
        try:
            async for delta in explorer_agent.interpret_guided_answer(
                user_id=user_id,
                project_id=project_id,
                question=question,
                free_text=free_text,
            ):
                parts.append(delta)
                yield sse.format_sse_event("delta", {"text": delta})
            answer = "".join(parts)
            if not answer.strip():
                # 空产兜底：provider 未产出任何正文（快档推理把 max_tokens 吃光、正文被挤空，
                # 陷阱⑥的极端残留）——不发 done.text="" 让前端纳入空答案，改发 error 让用户重试。
                logger.warning("引导自述理解流式产出为空，改发 error 而非空 done")
                yield sse.format_sse_event(
                    "error",
                    {"code": "generate_failed", "message": "生成失败，请稍后重试。"},
                )
                return
            # 正常收尾：拼完整答案作 done.text（供前端纳入该题答案）。
            yield sse.format_sse_event("done", {"text": answer})
        except ErrorEnvelope as exc:
            # 结构化业务错误（护栏/租户/provider 明确错误）是预期内可现实化的错误：不打 ERROR
            # 级堆栈（避免污染告警），warning 记 code 供排查。透传 code/message——message 是
            # ErrorEnvelope 面向用户的三要素之一（与 HTTP envelope 同源），不外泄内部细节。
            logger.warning("引导自述理解流式失败（业务错误）：%s", exc.code)
            yield sse.format_sse_event(
                "error", {"code": exc.code, "message": exc.message}
            )
        except Exception:
            # provider 中途异常（如 5xx/断连）等未预期错误：原始 exc 完整入日志、对外泛化。
            logger.exception("引导自述理解流式失败（未预期错误）")
            yield sse.format_sse_event(
                "error",
                {"code": "generate_failed", "message": "生成失败，请稍后重试。"},
            )

    return _gen()


@router.post("/{project_id}/explore/guided/interpret")
async def interpret_guided_answer(
    project_id: uuid.UUID,
    payload: GuidedInterpretRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> EventSourceResponse:
    """引导自述理解流式 SSE（AC4）：真实 Explorer Agent 凝练用户自述为该题答案。

    **先预检再建流**（Task 3 错误映射）：EventSourceResponse 一旦返回即提交 HTTP 200，之后无法
    再改状态码。故租户 404 / 护栏 429 在此**预检阶段**用请求 session 校验、抛 ErrorEnvelope 交全局
    handler 转正确 HTTP 状态；预检通过后才返回 SSE 流。流内的错误（provider 异常）走 error 事件。

    freeText 空/纯空白 → 422 由 GuidedInterpretRequest 的 _NonBlankText 自动校验（FastAPI 在进入
    本函数前完成）。流式生成用独立 session 自管（explorer_agent，陷阱⑩），不占用此请求 session。
    """
    # 预检：租户守卫 + 护栏（流建立前，产出正确 HTTP 状态）。
    await explorer_agent.preflight_interpret(
        session, user_id=current_user.id, project_id=project_id
    )
    return EventSourceResponse(
        _interpret_event_stream(
            user_id=current_user.id,
            project_id=project_id,
            question=payload.question,
            free_text=payload.free_text,
        )
    )


@router.post(
    "/{project_id}/explore/guided/answers", response_model=GuidedAnswerResponse
)
async def save_guided_answer(
    project_id: uuid.UUID,
    payload: GuidedAnswerRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> GuidedAnswerResponse:
    """保存/更新某题位引导答案（AC5）：常规 REST CRUD，非流式。

    返 200（幂等 upsert，非恒 201，陷阱⑦）——重复保存/改答返同题位最新态。project_id 非法 UUID
    由 FastAPI 自动 422；越权/不存在在 service 统一 404（陷阱①）；body 字段校验由 Pydantic 完成
    （answerType Literal / questionIndex ge=0 / question,answer 非空有界，陷阱⑧）。
    无 SSE/provider/ARQ——本端点不调 LLM、不需 Redis（陷阱⑨）。
    """
    message = await exploration_service.save_guided_answer(
        session,
        user_id=current_user.id,
        project_id=project_id,
        question_index=payload.question_index,
        question=payload.question,
        answer=payload.answer,
        answer_type=payload.answer_type,
    )
    return GuidedAnswerResponse.model_validate(message)


@router.get(
    "/{project_id}/explore/guided/answers",
    response_model=list[GuidedAnswerResponse],
)
async def list_guided_answers(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> list[GuidedAnswerResponse]:
    """恢复本会话全部已答（AC5）：按题位升序列表；空会话/未答返 []（200，非 404，陷阱⑥）。

    越权/不存在在 service 统一 404（陷阱①）；非法 UUID 自动 422。供前端进探索页回填
    explorationHistory（前端接线 defer 至前端集成切片，受控决策 A）。
    """
    messages = await exploration_service.list_guided_answers(
        session, user_id=current_user.id, project_id=project_id
    )
    return [GuidedAnswerResponse.model_validate(m) for m in messages]


@router.post(
    "/{project_id}/explore/guided/settle", response_model=TaskSubmitResponse
)
async def settle_guided_exploration(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> TaskSubmitResponse:
    """引导收尾触发「整理为故事设定」ARQ 后台任务（AC2）：提交语义，返 200 + taskId。

    **非流式**（陷阱③）：这是 POST→taskId 提交（照 tasks.py:30 demo 范式），前端拿 taskId 后连
    2.1 的 GET /api/tasks/{taskId}/events 消费 SSE——**不返 EventSourceResponse**（那是 2.3
    interpret 的交互式流式模式；settle 是 ARQ 后台任务模式，epics.md:457 二分）。SSE 消费端点由
    2.1 已建，本 story 复用、不重建（陷阱⑪）。

    无 body（触发即整理，凝练所需数据由任务自己从库读；project_id 已在路径）；project_id 非法
    UUID 由 FastAPI 自动 422。越权/不存在在 service 统一 404（陷阱①）。整理任务体只推占位 result
    （真实 LLM 12 字段凝练是 Story 3.3，受控决策 B）。
    """
    task_id = await exploration_service.trigger_guided_settle(
        session, user_id=current_user.id, project_id=project_id
    )
    return TaskSubmitResponse(task_id=task_id)
