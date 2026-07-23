"""Muse 后端 FastAPI 应用入口。"""

from fastapi import FastAPI

from muse.core.errors import register_exception_handlers
from muse.core.settings import get_settings
from muse.routers import health


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    register_exception_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
