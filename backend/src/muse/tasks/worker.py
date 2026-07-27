"""ARQ worker + 最小示范任务（Story 2.1，AC3）。

**demo_generate 是底座验证任务、非真实生成**——真实五段流水线（context→drafter→reviewer→
polisher→data-agent）在 Epic 4（AR11）。本任务只验证端到端：ARQ 消费 → 分 step 推 progress →
（真实）串起 check_quota → provider → record_usage → 推 result；异常推 error（复用错误 envelope）。

**兑现 1.8 跨 epic 依赖**：本任务是 check_quota/record_usage 的首个真实运行时消费方——证明护栏
与记账接口可用（AC5/AC6）。

陷阱⑦（session/连接生命周期）：worker 是独立进程/事件循环，on_startup 建自己的 async engine +
session_maker + 独立发布用 Redis 连接，on_shutdown 释放；绝不复用 web 请求的 get_session。
"""

import logging
import uuid

from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from muse.core import sse
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.providers.factory import get_provider_for_user
from muse.services import usage_service

logger = logging.getLogger("muse")

# 示范任务步数：模拟「多步长时生成」，每步一个 progress 事件。
_TOTAL_STEPS = 3
# 示范真实 provider 调用的 prompt（有 key 时才真打）：短 prompt 限成本/延迟。
_DEMO_PROMPT = "用一句话描述一个修仙世界的开场。"
_DEMO_MAX_TOKENS = 100


def _progress(step: int) -> dict[str, object]:
    """构造 progress payload（camelCase，至少 {step, percent}，architecture.md:336）。"""
    return {"step": step, "percent": round(step / _TOTAL_STEPS * 100)}


async def demo_generate(
    ctx: dict, task_id: str, user_id: str, *, fail: bool = False
) -> dict[str, object]:
    """示范长时任务：分 step 推 progress、串真实 check_quota+provider+record_usage、末推 result。

    fail=True 在第 2 步故意抛异常，验证 error 事件经同一链路推达（长时任务最关键路径）。
    check_quota 触顶（托管超额）会抛 ErrorEnvelope(429)，同样转 error 事件——证明护栏真的拦得住。
    """
    pub: Redis = ctx["pub_redis"]
    session_maker: async_sessionmaker = ctx["session_maker"]
    uid = uuid.UUID(user_id)
    settings = get_settings()
    try:
        # ---- step 1：生成前护栏（AC6）——check_quota 触顶抛 429，串起 1.8 护栏 ----
        await sse.publish_event(pub, task_id, sse.EVENT_PROGRESS, _progress(1))
        async with session_maker() as session:
            # 托管触顶抛 429、BYOK 短路放行（1.8 check_quota，须在 Provider 调用之前）。
            await usage_service.check_quota(session, uid)

        if fail:
            # 模拟某步生成失败（真实五段流水线每 step 失败都走此 error 路径，Epic 4）。
            raise RuntimeError("模拟第 2 步生成失败")

        # ---- step 2：（有 key 时）真实 provider 调用 + 记账（AC5）——串起 1.8 记账 ----
        await sse.publish_event(pub, task_id, sse.EVENT_PROGRESS, _progress(2))
        chapter_text = "（未配置 DEEPSEEK_API_KEY，跳过真实生成）"
        if settings.deepseek_api_key:
            # MeteredProvider.chat 内部调用完 LLM 即 record_usage（记账埋点在 Provider 层）。
            async with session_maker() as session:
                provider = await get_provider_for_user(session, uid)
                result = await provider.chat(
                    [{"role": "user", "content": _DEMO_PROMPT}],
                    model=settings.deepseek_model_fast,
                    max_tokens=_DEMO_MAX_TOKENS,
                )
                chapter_text = result.content

        # ---- step 3：完成 ----
        await sse.publish_event(pub, task_id, sse.EVENT_PROGRESS, _progress(3))
        payload: dict[str, object] = {
            "taskId": task_id,
            "chapterText": chapter_text,
            "steps": _TOTAL_STEPS,
        }
        await sse.publish_event(pub, task_id, sse.EVENT_RESULT, payload)
        return payload
    except ErrorEnvelope as exc:
        # 护栏/业务错误（如 quota_exceeded 429、provider_not_supported）复用 envelope 的
        # code/message。
        await sse.publish_event(
            pub, task_id, sse.EVENT_ERROR, {"code": exc.code, "message": exc.message}
        )
        raise
    except Exception as exc:  # noqa: BLE001  worker 内任何异常都要推 error 事件（AC3）
        # 原始异常仅落日志（可能含 DB 连接串片段、驱动错误、内部路径等敏感信息）；推给前端的
        # error 事件只用固定泛化文案，避免内部实现细节经 SSE 外泄。受控的 ErrorEnvelope 分支
        # （上方）已是安全的 code/message，照常透传。
        logger.exception("demo_generate 任务失败：task_id=%s", task_id, exc_info=exc)
        await sse.publish_event(
            pub,
            task_id,
            sse.EVENT_ERROR,
            {"code": "generate_failed", "message": "生成失败，请稍后重试。"},
        )
        raise


async def on_startup(ctx: dict) -> None:
    """worker 启动：建独立 async engine + session_maker + 发布用 Redis 连接（陷阱⑦）。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["db_engine"] = engine
    ctx["session_maker"] = async_sessionmaker(engine, expire_on_commit=False)
    # 发布用独立 Redis 连接（不复用 ARQ broker 连接，spike P2 范式）。
    ctx["pub_redis"] = Redis.from_url(settings.redis_url)


async def on_shutdown(ctx: dict) -> None:
    """worker 关闭：释放 Redis 连接与 DB 引擎，避免连接泄漏（陷阱⑦）。"""
    pub = ctx.get("pub_redis")
    if pub is not None:
        await pub.aclose()
    engine = ctx.get("db_engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    """ARQ WorkerSettings：`uv run arq muse.tasks.worker.WorkerSettings` 启动。

    redis_settings 从 settings.redis_url 派生（与应用共用 broker）；on_startup/on_shutdown 管理
    worker 独立的 DB/Redis 连接生命周期（陷阱⑦）。
    """

    functions = [demo_generate]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
