"""Muse 后端 FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from muse.core.db import engine
from muse.core.errors import register_exception_handlers
from muse.core.settings import get_settings
from muse.routers import auth, health


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # 应用关闭/热重载时释放 async 连接池，避免连接泄漏耗尽 DB slot。
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
