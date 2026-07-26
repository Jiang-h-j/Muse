"""用量路由（Story 1.8，AR2：router 仅校验入参 + 分发，业务在 usage_service）。

GET /api/usage 依赖 CurrentUser——鉴权入口（core/deps）自动完成 access token 校验并取当前 User；
未登录/失效在依赖内 401。用量是账户级资源：当前用户即主体，用 current_user.id 定位，路径不带
user_id/project_id（消除 IDOR 面，与 byok router 账户级同款）。
"""

from fastapi import APIRouter

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.account import UsageViewResponse
from muse.services import usage_service

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=UsageViewResponse)
async def get_usage(
    current_user: CurrentUser, session: SessionDep
) -> UsageViewResponse:
    # 查询本人用量与剩余免费额度（AC3）：托管用户回具体用量、BYOK 用户回豁免语义态。
    # 只读、永不因触顶而失败（护栏与展示分离在 service 层保证）。租户隔离在 repo 层。
    payload = await usage_service.get_usage_view(session, current_user.id)
    return UsageViewResponse.model_validate(payload)
