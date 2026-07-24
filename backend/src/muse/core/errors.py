"""统一错误处理：error envelope {code, message, detail}（AR5）。

所有异常出口收敛为同一结构，HTTP 状态码语义化。时间字段一律 ISO 8601 UTC。
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("muse")


class ErrorEnvelope(Exception):
    """业务可主动抛出的错误，携带 envelope 三要素与 HTTP 状态码。"""

    def __init__(
        self,
        code: str,
        message: str,
        detail: object = None,
        http_status: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = http_status
        super().__init__(message)


def _envelope(code: str, message: str, detail: object = None) -> dict[str, object]:
    # jsonable_encoder 兜底：detail 可能是 Pydantic 错误、异常对象等非原生可序列化类型，
    # 否则 JSONResponse 渲染时抛 TypeError 逃逸出 handler，反退化成裸 500。
    return {"code": code, "message": message, "detail": jsonable_encoder(detail)}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErrorEnvelope)
    async def _handle_envelope(_: Request, exc: ErrorEnvelope) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail), None),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 剔除每条错误里的 input（用户提交的原始值），避免密码/token 等敏感字段反射进响应体。
        # 注：FastAPI 的 RequestValidationError.errors() 不支持 pydantic 的 include_input 参数，
        # 故手动过滤。
        safe_errors = [
            {k: v for k, v in err.items() if k != "input"} for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", "请求参数校验失败。", safe_errors),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 记录完整 traceback + 请求上下文，避免生产 500 成为无线索的可观测性黑洞。
        logger.exception("未处理异常：%s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "服务器内部错误。", None),
        )
