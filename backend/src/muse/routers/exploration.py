"""探索路由（AR2：router 仅校验入参 + 分发，业务在 exploration_service / explorer_agent /
free_explorer_agent）。

探索挂在 project 层级下（prefix /api/projects）：
- POST /{project_id}/explore：进入探索（get-or-create 语义，Story 2.2）。
- POST /{project_id}/explore/guided/interpret：引导自述理解流式 SSE（Story 2.3 AC4）——真实
  Explorer Agent 把用户一句话自述凝练为该题答案，逐块 SSE 推送 delta→done→error。
- POST /{project_id}/explore/guided/answers：保存/更新某题位引导答案（Story 2.4，幂等 upsert 200）。
- GET  /{project_id}/explore/guided/answers：恢复本会话全部已答（Story 2.4，题位升序，空态 []）。
- POST /{project_id}/explore/guided/settle：引导收尾触发「整理为故事设定」ARQ 后台任务（Story 2.5
  AC2）——租户守卫 + 登记属主 + 入队 settle_exploration，返 taskId，前端连 2.1 的
  GET /api/tasks/{taskId}/events 消费 SSE（progress/result/error）。非流式提交（非 interpret
  的 EventSourceResponse）——异步模型二分 epics.md:457：settle 走 ARQ 后台任务、interpret 走流式。
- POST /{project_id}/explore/free/messages：自由对话一轮，流式 SSE（Story 2.6 AC2/AC6）——真实
  Free Explorer Agent 多轮对话，delta→done→error，用户消息与 Agent 回复均真实落库。
- GET  /{project_id}/explore/free/messages：恢复本会话全部自由对话消息（Story 2.6 AC6，创建时间
  升序，空态 []）。
- GET/POST /{project_id}/explore/free/clues：列出/新增自定义故事线索（Story 2.6 AC3/AC6）。
- PATCH/DELETE /{project_id}/explore/free/clues/{clue_id}：编辑/删除线索（删除仅限自定义线索）。
- POST /{project_id}/explore/free/clues/refresh：Agent 依对话自动整理线索（Story 2.6 AC5，硬 AC）
  ——同步调用，只更新未被用户编辑的预设槙位。
- POST /{project_id}/explore/free/settle：自由探索触发「整理为故事设定」ARQ 后台任务（Story 2.7
  AC3/AC4）——租户守卫 + **门禁硬校验**（本会话须至少 1 条 free 用户消息，否则 400
  exploration_not_ready）+ 登记属主 + 入队 settle_exploration，返 taskId，前端连 2.1 的
  GET /api/tasks/{taskId}/events 消费 SSE。非流式提交（同 guided/settle，异步模型二分见 epics）。
  门禁硬校验是本 story 相对 2.5 的差异（FR10「补足信息才开放」+ 2.6「不止于前端」先例）。

依赖 CurrentUser 自动完成 access token 校验并取当前 User；未登录/token 失效在依赖内 401。
所有操作绑定 current_user.id 实现租户隔离；越权/不存在同码 404（业务在 service）。guided/free
两模式端点互相串门返 409 mode_mismatch（Story 2.6 AC7，mode 守卫在 service 层）。

交互式流式（受控决策 B，epics.md:457）：interpret / free/messages 走**直连 provider.stream**
逐块推（EventSourceResponse over async gen），**不走 ARQ 的 POST→taskId→GET /events 那套**（那是
批量后台任务模式，2.5/2.7 用）——故不引入 Redis/worker，仅复用 core/sse.format_sse_event 纯编码。
线索整理（free/clues/refresh）同属此类：一次性结构化提炼、非长时生成，同步端点即可。
"""

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, status
from sse_starlette.sse import EventSourceResponse

from muse.core import sse
from muse.core.deps import CurrentUser, SessionDep
from muse.core.errors import ErrorEnvelope, logger
from muse.schemas.exploration import (
    ClueCreateRequest,
    ClueEditRequest,
    ClueResponse,
    ExplorationSessionResponse,
    FreeMessageRequest,
    FreeMessageResponse,
    GuidedAnswerRequest,
    GuidedAnswerResponse,
    GuidedInterpretRequest,
)
from muse.schemas.task import TaskSubmitResponse
from muse.services import exploration_service, explorer_agent, free_explorer_agent

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


def _free_chat_event_stream(
    *, user_id: uuid.UUID, project_id: uuid.UUID, user_message: str
) -> AsyncIterator[dict[str, str]]:
    """把 Free Explorer Agent 的正文增量编码为 SSE 事件流：delta×N → done →（异常时）error。

    结构照搬 `_interpret_event_stream`（Dev Notes「SSE 编码范式照搬」），只替换调用的编排
    函数（`stream_free_chat` 替代 `interpret_guided_answer`）：delta 累积正文块、空产兜底
    改发 error（不发空 done）、ErrorEnvelope 透传 code/message、未预期异常泛化为
    generate_failed + 日志记完整栈但不外泄。
    """

    async def _gen() -> AsyncIterator[dict[str, str]]:
        parts: list[str] = []
        try:
            async for delta in free_explorer_agent.stream_free_chat(
                user_id=user_id,
                project_id=project_id,
                user_message=user_message,
            ):
                parts.append(delta)
                yield sse.format_sse_event("delta", {"text": delta})
            answer = "".join(parts)
            if not answer.strip():
                logger.warning("自由对话流式产出为空，改发 error 而非空 done")
                yield sse.format_sse_event(
                    "error",
                    {"code": "generate_failed", "message": "生成失败，请稍后重试。"},
                )
                return
            yield sse.format_sse_event("done", {"text": answer})
        except ErrorEnvelope as exc:
            logger.warning("自由对话流式失败（业务错误）：%s", exc.code)
            yield sse.format_sse_event(
                "error", {"code": exc.code, "message": exc.message}
            )
        except Exception:
            logger.exception("自由对话流式失败（未预期错误）")
            yield sse.format_sse_event(
                "error",
                {"code": "generate_failed", "message": "生成失败，请稍后重试。"},
            )

    return _gen()


@router.post("/{project_id}/explore/free/messages")
async def send_free_message(
    project_id: uuid.UUID,
    payload: FreeMessageRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> EventSourceResponse:
    """自由对话一轮流式 SSE（AC2/AC6）：真实 Free Explorer Agent 多轮对话。

    **先预检再建流**（同 interpret 范式）：EventSourceResponse 一旦返回即提交 HTTP 200，之后
    无法再改状态码。故租户 404 / mode 守卫 409 / 护栏 429 在此**预检阶段**用请求 session 校验；
    预检通过后才返回 SSE 流。流内错误走 error 事件。流式生成用独立 session 自管
    （free_explorer_agent，陷阱⑩），不占用此请求 session。
    """
    await free_explorer_agent.preflight_free_chat(
        session, user_id=current_user.id, project_id=project_id
    )
    return EventSourceResponse(
        _free_chat_event_stream(
            user_id=current_user.id,
            project_id=project_id,
            user_message=payload.content,
        )
    )


@router.get(
    "/{project_id}/explore/free/messages",
    response_model=list[FreeMessageResponse],
)
async def list_free_messages(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> list[FreeMessageResponse]:
    """恢复本会话全部自由对话消息（AC6）：按创建时间升序；空会话/无消息返 []（200，非 404）。

    越权/不存在在 service 统一 404；mode 不匹配 409；非法 UUID 自动 422。供前端进自由探索页
    回填对话记录（前端接线 defer 至前端集成切片，受控决策 A）。
    """
    messages = await exploration_service.list_free_messages(
        session, user_id=current_user.id, project_id=project_id
    )
    return [FreeMessageResponse.model_validate(m) for m in messages]


@router.get(
    "/{project_id}/explore/free/clues",
    response_model=list[ClueResponse],
)
async def list_clues(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> list[ClueResponse]:
    """列出本会话全部故事线索（预设槙位 + 自定义，AC3/AC6）：按 display_order 升序；空态 []。"""
    clues = await exploration_service.list_clues(
        session, user_id=current_user.id, project_id=project_id
    )
    return [ClueResponse.model_validate(c) for c in clues]


@router.post(
    "/{project_id}/explore/free/clues",
    response_model=ClueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_clue(
    project_id: uuid.UUID,
    payload: ClueCreateRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ClueResponse:
    """新增自定义故事线索（AC3）：201，display_order 取本会话现有最大值 +1。"""
    clue = await exploration_service.create_custom_clue(
        session,
        user_id=current_user.id,
        project_id=project_id,
        label=payload.label,
        value=payload.value,
    )
    return ClueResponse.model_validate(clue)


@router.patch(
    "/{project_id}/explore/free/clues/{clue_id}",
    response_model=ClueResponse,
)
async def edit_clue(
    project_id: uuid.UUID,
    clue_id: uuid.UUID,
    payload: ClueEditRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ClueResponse:
    """编辑线索（AC3）：置 user_edited=true（AC5「用户编辑优先」的写入侧）。value 允许空串
    （代表清空为「尚未确定」，占位逻辑在前端）；label 提供时才改名并校验非空有界——但 preset
    线索的 label 不可改（400 preset_label_immutable，其固定中文标签是整理端点匹配键）。
    """
    clue = await exploration_service.edit_clue(
        session,
        user_id=current_user.id,
        project_id=project_id,
        clue_id=clue_id,
        value=payload.value,
        label=payload.label,
    )
    return ClueResponse.model_validate(clue)


@router.delete(
    "/{project_id}/explore/free/clues/{clue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_clue(
    project_id: uuid.UUID,
    clue_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    """删除自定义线索（AC3）：仅限 kind="custom"，preset 尝试删除返 400 clue_not_deletable
    （同 delete_project/byok 既有约定，204 无响应体）。
    """
    await exploration_service.delete_clue(
        session, user_id=current_user.id, project_id=project_id, clue_id=clue_id
    )


@router.post(
    "/{project_id}/explore/free/clues/refresh",
    response_model=list[ClueResponse],
)
async def refresh_clues(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> list[ClueResponse]:
    """Agent 依对话自动整理线索（AC5，硬 AC）：同步端点、非 ARQ——一次性结构化提炼，非长时生成。

    只更新未被用户编辑（user_edited=false）的预设槙位；自定义线索永不被本端点触碰。无副作用地
    反复调用是安全的（重复调用幂等收敛）。触发时机（每轮对话后自动调用还是用户点按钮）是前端
    编排决定，defer 至前端集成切片——本端点只交付可被随时安全调用的整理原语。

    返回整理后的完整线索列表（而非仅更新的槙位映射）：前端据此一次性刷新整个线索区，无需
    再额外调 GET clues。
    """
    await free_explorer_agent.extract_clues(
        user_id=current_user.id, project_id=project_id
    )
    clues = await exploration_service.list_clues(
        session, user_id=current_user.id, project_id=project_id
    )
    return [ClueResponse.model_validate(c) for c in clues]


@router.post(
    "/{project_id}/explore/free/settle", response_model=TaskSubmitResponse
)
async def settle_free_exploration(
    project_id: uuid.UUID, current_user: CurrentUser, session: SessionDep
) -> TaskSubmitResponse:
    """自由探索触发「整理为故事设定」ARQ 后台任务（AC3/AC4）：提交语义，返 200 + taskId。

    **非流式**（陷阱③）：POST→taskId 提交（同 guided/settle），前端拿 taskId 后连 2.1 的
    GET /api/tasks/{taskId}/events 消费 SSE——**不返 EventSourceResponse**（那是 interpret /
    free/messages 的交互式流式模式；settle 是 ARQ 后台任务模式，epics.md:457 二分）。SSE 消费
    端点由 2.1 已建，本 story 复用、不重建（陷阱⑪）。

    **门禁硬校验（AC4，本 story 相对 2.5 的差异）**：service 层在租户守卫 + mode 守卫之后，再校验
    本会话至少有 1 条 free 用户消息，否则 400 exploration_not_ready（不入队、不登记属主、不返
    taskId）。门禁「补足信息才开放」是 user story 核心 benefit（FR10），且延续 2.6「模式独立在数据
    写入层真正落地不止于前端」先例，故后端做实（前端 disabled + 后端 400 双防线）。

    无 body（触发即整理，凝练所需数据由任务自己从库读；project_id 已在路径）；project_id 非法
    UUID 由 FastAPI 自动 422。越权/不存在在 service 统一 404（陷阱①，先于门禁）。整理任务体复用
    settle_exploration 任务（真实 12 字段凝练，Story 3.3 已接入；free 材料=对话+线索）。
    """
    task_id = await exploration_service.trigger_free_settle(
        session, user_id=current_user.id, project_id=project_id
    )
    return TaskSubmitResponse(task_id=task_id)


