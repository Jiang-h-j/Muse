"""Muse 后端 FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from muse.core.db import engine
from muse.core.errors import register_exception_handlers
from muse.core.settings import get_settings
from muse.routers import auth, byok, exploration, health, projects, story, tasks, usage


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # 应用关闭/热重载时释放 async 连接池，避免连接泄漏耗尽 DB slot。
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    # CORS（Story 7.1 AC6，联调前置）：原型静态站与后端跨域，须放开前端 origin，否则浏览器
    # 预检/响应阶段拦截所有跨域请求（连 401 都收不到），Epic 7 前端接线地基无从验证。
    # 来源按环境配置（settings.cors_allow_origins_list），不无脑 `*`；allow_credentials 与
    # 通配 `*` 互斥，此处走显式 origin 列表故可安全开启。中间件包裹全应用，错误响应也带 CORS 头。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(exploration.router)
    app.include_router(story.router)
    app.include_router(byok.router)
    app.include_router(usage.router)
    app.include_router(tasks.router)
    return app


app = create_app()
