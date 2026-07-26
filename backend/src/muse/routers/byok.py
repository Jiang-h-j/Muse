"""BYOK 路由（Story 1.7，AR2：router 仅校验入参 + 分发，业务在 byok_service）。

PUT/GET/DELETE /api/byok 均依赖 CurrentUser——鉴权入口（core/deps）自动完成 access token
校验并取当前 User；未登录/失效在依赖内 401。BYOK 是账户级单例资源：当前用户即资源主体，
用 current_user.id 定位，路径不带 key_id/project_id（消除 IDOR 面，契合账户级唯一约束）。
"""

from fastapi import APIRouter, status

from muse.core.deps import CurrentUser, SessionDep
from muse.schemas.account import ByokBindRequest, ByokStatusResponse
from muse.services import byok_service

router = APIRouter(prefix="/api/byok", tags=["byok"])


@router.put("", response_model=ByokStatusResponse)
async def bind_byok(
    payload: ByokBindRequest, current_user: CurrentUser, session: SessionDep
) -> ByokStatusResponse:
    # PUT = 幂等 upsert 语义，天然覆盖绑定（AC1）+ 替换（AC3）；同账户至多一条、重复提交结果一致。
    # 入参已由 Pydantic 校验（provider 枚举 / apiKey 非空）；加密落库 + 掩码在 service。
    byok = await byok_service.bind_or_replace_key(
        session,
        user_id=current_user.id,
        provider=payload.provider,
        plaintext_key=payload.api_key,
    )
    return ByokStatusResponse.model_validate(byok_service.status_payload(byok))


@router.get("", response_model=ByokStatusResponse)
async def get_byok(
    current_user: CurrentUser, session: SessionDep
) -> ByokStatusResponse:
    # 查询本人绑定状态（AC4）：已绑定回掩码、未绑定回空态；绝不回显明文。租户隔离在 repo 层保证。
    payload = await byok_service.get_binding_status(session, user_id=current_user.id)
    return ByokStatusResponse.model_validate(payload)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_byok(current_user: CurrentUser, session: SessionDep) -> None:
    # 204 No Content 不带响应体（参照 delete_project）：解绑（AC3），幂等——未绑定时也成功。
    await byok_service.unbind_key(session, user_id=current_user.id)
