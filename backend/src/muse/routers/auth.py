"""认证路由（AR2：router 仅校验入参 + 分发，业务在 auth_service）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import get_session
from muse.schemas.account import RegisterRequest, RegisterResponse
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
