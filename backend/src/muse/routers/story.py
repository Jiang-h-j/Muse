"""故事设定路由（AR2：router 仅校验入参 + 分发，业务在 style_anchor_agent / story_settle_agent）。

设定挂在 project 层级下（prefix /api/projects）：
- GET  /{project_id}/style-anchor/samples：列出预置文风样本库（Story 3.2 AC1）——后端做样本库
  单一事实源，避免前后端样本漂移。无需鉴权外的租户校验（样本库是全局常量、非用户数据）。
- POST /{project_id}/style-anchor：文风锚点抽取（Story 3.2 AC2/AC3）——库选 sampleId 或粘贴
  sampleText，真实抽取 style_profile 并 upsert 到 story_bible，返 200 + StyleProfileResponse。
- GET   /{project_id}/story-profile：取待确认候选卡（Story 3.4 AC6 恢复）——有 pending 卡返 200 +
  卡、无返 204（刷新/断线重连恢复；确认后 3.5 翻 confirmed 则本端点返 204 表待确认态已清）。
- PATCH /{project_id}/story-profile：直接编辑候选卡字段（Story 3.4 AC2）——无 LLM 同步改字段值、
  revision 不变，返 200 + 新卡。
- POST  /{project_id}/story-profile/revise：反馈升版本（Story 3.4 AC3/AC4）——真实同一凝练 Agent
  按反馈重生成、revision 递增、标变化字段，返 200 + 新卡。
- POST  /{project_id}/story-profile/confirm：确认设定（Story 3.5 AC1）——pending 卡翻 confirmed 只读
  圣经 + 作品 phase explore→chapter（同一事务），返 200 + confirmed 卡。
- POST  /{project_id}/story-profile/discard：回到探索丢弃（Story 3.5 AC3）——删 pending 行，返 204；
  幂等（无卡可丢也 204）。

**非流式**（受控决策 3/2）：文风抽取、候选卡编辑/反馈升版本都是一次性结构化操作、非长时生成，
同步端点即可（同 free/clues/refresh，exploration.py），不引入 Redis/worker/SSE。settle（ARQ）是
探索收尾的批量后台触发，本文件的 story-profile 端点是「已在看卡时的即时操作」，交互形态不同。

依赖 CurrentUser 自动完成 access token 校验并取当前 User；未登录/token 失效在依赖内 401。
操作绑定 current_user.id 实现租户隔离；越权/不存在同码 404（业务在 service）。**不加 mode
守卫**（受控决策 4）：设定候选卡是作品级、guided/free 两模式均可产出并编辑。
"""

import uuid

from fastapi import APIRouter, Response

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.story import (
    ProfileCardEditRequest,
    ProfileFeedbackRequest,
    StoryProfileCardResponse,
    StyleAnchorRequest,
    StyleProfileResponse,
    StyleSampleResponse,
)
from muse.services import story_settle_agent, style_anchor_agent

router = APIRouter(prefix="/api/projects", tags=["story"])


@router.get(
    "/{project_id}/style-anchor/samples",
    response_model=list[StyleSampleResponse],
)
async def list_style_samples(
    project_id: uuid.UUID, current_user: CurrentUser
) -> list[StyleSampleResponse]:
    """列出预置文风样本库（AC1）：全局常量、非用户数据，仅需登录（CurrentUser）。

    project_id 在路径上保持 REST 层级一致（设定挂 project 下），但样本库本身与具体作品无关、
    不做租户校验（无 project 归属查询）。返回 id/name/note/excerpt 供前端渲染卡片，不含抽取
    用完整原文（库选只回传 sampleId，原文后端内部持有）。
    """
    return [
        StyleSampleResponse(
            id=s.id, name=s.name, note=s.note, excerpt=s.excerpt
        )
        for s in style_anchor_agent.STYLE_SAMPLE_LIBRARY
    ]


@router.post("/{project_id}/style-anchor", response_model=StyleProfileResponse)
async def anchor_style(
    project_id: uuid.UUID,
    payload: StyleAnchorRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> StyleProfileResponse:
    """文风锚点抽取（AC2/AC3/AC6）：真实抽取 style_profile 并 upsert 到 story_bible，返 200。

    **先预检再抽取**（同 interpret 范式的错误映射）：租户 404 / 护栏 429 在预检阶段用请求
    session 校验、抛 ErrorEnvelope 交全局 handler 转正确 HTTP 状态。预检通过后 service 用独立
    session 自管抽取（陷阱⑩）。sampleId/sampleText 互斥由 StyleAnchorRequest 的 model_validator
    校验（422 在进入本函数前完成）；project_id 非法 UUID 由 FastAPI 自动 422。

    sample 原文解析（库选取预置原文 / 粘贴原样）在 service.resolve_sample_text；未知 sampleId
    → 400 unknown_style_sample。抽取空产 → service 抛 generate_failed（502）。
    """
    # 预检：租户守卫 + 护栏（抽取前，产出正确 HTTP 状态）。
    await style_anchor_agent.preflight_style_anchor(
        session, user_id=current_user.id, project_id=project_id
    )
    # 统一解析待抽取样本原文（库选 sampleId / 粘贴 sampleText），未知 id 在此 400。
    sample_text = style_anchor_agent.resolve_sample_text(
        sample_id=payload.sample_id, sample_text=payload.sample_text
    )
    bible = await style_anchor_agent.extract_and_anchor_style(
        user_id=current_user.id,
        project_id=project_id,
        sample_text=sample_text,
    )
    return StyleProfileResponse(style_profile=bible.style_profile or "", anchored=True)


@router.get("/{project_id}/story-profile")
async def get_story_profile(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    """取待确认候选卡（Story 3.4 AC6 恢复）：有 pending 卡返 200 + 卡、无返 204。

    刷新/断线重连时前端 GET 恢复待确认卡（含 profile/revision/changedFields），不回退到探索主界面。
    无待确认卡（还没整理 / 已确认清了 pending 态）是正常空态、返 204 No Content（非 404 错误）。
    越权/不存在 project → service 抛 404（二义合一）。
    """
    bible = await story_settle_agent.get_pending_card(
        session, user_id=current_user.id, project_id=project_id
    )
    if bible is None:
        return Response(status_code=204)
    card = StoryProfileCardResponse.model_validate(bible)
    return Response(
        content=card.model_dump_json(by_alias=True),
        media_type="application/json",
    )


@router.patch("/{project_id}/story-profile", response_model=StoryProfileCardResponse)
async def edit_story_profile(
    project_id: uuid.UUID,
    payload: ProfileCardEditRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> StoryProfileCardResponse:
    """直接编辑候选卡字段（Story 3.4 AC2）：无 LLM 同步改字段值、revision 不变，返 200 + 新卡。

    只改用户实际传入（非 None）的字段（`to_fields`）；仅作用 status='pending' 行。无待确认卡
    → service 抛 404 no_pending_card。越权/不存在 project → 404。model 只暴露 12 内容字段，
    天然防越权改 status/revision。
    """
    bible = await story_settle_agent.edit_profile_card(
        session,
        user_id=current_user.id,
        project_id=project_id,
        fields=payload.to_fields(),
    )
    return StoryProfileCardResponse.model_validate(bible)


@router.post(
    "/{project_id}/story-profile/revise", response_model=StoryProfileCardResponse
)
async def revise_story_profile(
    project_id: uuid.UUID,
    payload: ProfileFeedbackRequest,
    current_user: CurrentUser,
) -> StoryProfileCardResponse:
    """反馈升版本（Story 3.4 AC3/AC4）：真实凝练 Agent 按反馈重生成、revision 递增，返 200 + 新卡。

    **同步 REST**（受控决策 2）：一次性重凝练，处理中态由 HTTP 在途表达（前端 disable 按钮 +
    「调整中…」），无需 SSE。service 独立 session 自管（陷阱⑩，含记账）——租户 404 / 无卡 404 /
    护栏 429 / 空产 502 均由 service 抛 ErrorEnvelope 交全局 handler。空反馈由 schema 422 拦。
    """
    bible = await story_settle_agent.revise_profile_card(
        user_id=current_user.id,
        project_id=project_id,
        feedback=payload.feedback,
    )
    return StoryProfileCardResponse.model_validate(bible)


@router.post(
    "/{project_id}/story-profile/confirm", response_model=StoryProfileCardResponse
)
async def confirm_story_profile(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> StoryProfileCardResponse:
    """确认设定 → 只读设定圣经 + phase 推进（Story 3.5 AC1/AC2/AC5）：返 200 + confirmed 卡。

    **无请求体**（幂等动作，作用对象由 path project_id + 会话 user_id 唯一确定）。POST（有副作用：
    翻 status='confirmed' + 推 project.phase explore→chapter，两处同一事务）。确认后 GET 恢复端点
    自然返 204（待确认态已清）；编辑/反馈端点对 confirmed 行天然返 404（只读性，AC2）。

    租户 404 / 无 pending 卡 → 404 no_pending_card 由 service 抛 ErrorEnvelope 交全局 handler；
    project_id 非法 UUID 由 FastAPI 自动 422。
    """
    bible = await story_settle_agent.confirm_profile_card(
        session, user_id=current_user.id, project_id=project_id
    )
    return StoryProfileCardResponse.model_validate(bible)


@router.post("/{project_id}/story-profile/discard", status_code=204)
async def discard_story_profile(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    """回到探索页面 → 丢弃待确认设定（Story 3.5 AC3）：删 pending 行，返 204。

    **无请求体**（对应原型二次确认「确定返回」）。POST（有副作用：删 pending 行）。**幂等**：无
    pending 卡可丢时也返 204（用户意图=回到探索，卡在不在都达成）。只删 pending 行——confirmed
    只读圣经 / draft 半成品行不受影响。越权/不存在 project → service 抛 404（二义合一）。

    二次确认弹窗 + 「取消」保留是纯前端交互（AC4）——「取消」不触后端、无对应端点；仅「确定返回」
    调本端点。
    """
    await story_settle_agent.discard_profile_card(
        session, user_id=current_user.id, project_id=project_id
    )
    return Response(status_code=204)
