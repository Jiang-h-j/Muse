"""认证路由（AR2：router 仅校验入参 + 分发，业务在 auth_service）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import get_session
from muse.core.deps import CurrentUser
from muse.schemas.account import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from muse.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep) -> RegisterResponse:
    # 入参已由 Pydantic 独立校验（AC4）；业务编排在 service，错误经全局 handler 转 envelope。
    # 本 story 不签发 token（登录/会话是 Story 1.3），成功仅返回新用户安全视图。
    user = await auth_service.register(
        session,
        invite_code=payload.invite_code,
        email=payload.email,
        password=payload.password,
    )
    return RegisterResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    # 校验 + 分发；限流/等时防枚举/双 token 签发全在 service（AC1/AC3/AC4）。
    bundle = await auth_service.login(session, email=payload.email, password=payload.password)
    return TokenResponse(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        expires_in=bundle.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenResponse:
    # refresh 有效性校验 + 轮转在 service（AC2）；失效由全局 handler 转 401 token_invalid envelope。
    bundle = await auth_service.refresh(session, refresh_token=payload.refresh_token)
    return TokenResponse(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        expires_in=bundle.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, session: SessionDep) -> None:
    # 幂等作废 refresh 会话（AC5）；无返回体，204。
    await auth_service.logout(session, refresh_token=payload.refresh_token)


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    # 最小受保护端点：CurrentUser 依赖已完成 access token 校验（AC5）；失败在依赖内 401。
    return MeResponse.model_validate(current_user)
