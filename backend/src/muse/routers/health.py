"""健康检查路由（AR2：router 仅校验入参 + 分发，业务在 service）。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.db import get_session
from muse.core.errors import ErrorEnvelope
from muse.schemas.health import HealthResponse
from muse.services.health_service import check_db_connected

router = APIRouter(tags=["health"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDep) -> HealthResponse:
    db_ok = await check_db_connected(session)
    return HealthResponse(status="ok", db_connected=db_ok)


@router.get("/health/error-probe")
async def error_probe() -> None:
    """临时探针：主动抛错以验证统一 error envelope（本 story 用，后续可删）。"""
    raise ErrorEnvelope(
        code="probe_error",
        message="这是用于验证 error envelope 的探针错误。",
        detail={"hint": "本端点仅供 Story 1.1 验证，后续可移除。"},
    )
