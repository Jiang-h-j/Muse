"""故事设定路由（AR2：router 仅校验入参 + 分发，业务在 services/style_anchor_agent）。

设定挂在 project 层级下（prefix /api/projects）：
- GET  /{project_id}/style-anchor/samples：列出预置文风样本库（Story 3.2 AC1）——后端做样本库
  单一事实源，避免前后端样本漂移。无需鉴权外的租户校验（样本库是全局常量、非用户数据）。
- POST /{project_id}/style-anchor：文风锚点抽取（Story 3.2 AC2/AC3）——库选 sampleId 或粘贴
  sampleText，真实抽取 style_profile 并 upsert 到 story_bible，返 200 + StyleProfileResponse。

**非流式**（受控决策 3）：文风抽取是一次性结构化小提炼、非长时生成，同步端点即可（同
free/clues/refresh，exploration.py:32-35），不引入 Redis/worker/SSE。

依赖 CurrentUser 自动完成 access token 校验并取当前 User；未登录/token 失效在依赖内 401。
抽取绑定 current_user.id 实现租户隔离；越权/不存在同码 404（业务在 service）。**不加 mode
守卫**（受控决策 4）：文风锚点作品级、guided/free 两模式均可锚定。
"""

import uuid

from fastapi import APIRouter

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.story import (
    StyleAnchorRequest,
    StyleProfileResponse,
    StyleSampleResponse,
)
from muse.services import style_anchor_agent

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
