"""任务路由（Story 2.1，AR2：router 仅校验入参 + 分发，编排在 worker/service）。

- POST /api/tasks/demo：提交**示范**长时任务（底座验证、非真实生成），入队 ARQ 返 taskId。
  真实生成端点（POST /api/projects/{id}/chapters/{n}/generate 等）在 Epic 2/4。
- GET /api/tasks/{task_id}/events：SSE 推送 progress/result/error（AC3），先补发快照再听增量
  （AC4）。

均依赖 CurrentUser 鉴权。SSE 端点额外做**任务归属校验**（陷阱⑤ IDOR）：taskId 是不可枚举的
uuid4 hex，且提交时登记属主 user_id 到 Redis，SSE 端点比对当前用户——防枚举 taskId 偷看他人
生成进度/内容。ARQ 连接池每次 create_pool + aclose（spike 范式，简单；应用级复用池待需要时再优化）。
"""

import uuid

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from muse.core import sse
from muse.core.deps import CurrentUser
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.schemas.task import TaskSubmitResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/demo", response_model=TaskSubmitResponse)
async def submit_demo_task(current_user: CurrentUser) -> TaskSubmitResponse:
    """提交示范长时任务（AC3）：生成 stable taskId、登记属主、入队 ARQ demo_generate。

    taskId = uuid4 hex（不可枚举，陷阱⑤）；作为 ARQ _job_id + Pub/Sub 频道键。登记属主须在入队
    **之前**——否则 worker 可能在属主键写入前就发首个事件、SSE 端点鉴权读不到属主而误拒。
    """
    settings = get_settings()
    task_id = uuid.uuid4().hex
    user_id = str(current_user.id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主。
        await sse.register_task_owner(pool, task_id, user_id)
        # _job_id=task_id：stable id 作 pubsub 频道键（spike 范式）；user_id 传给 worker 供
        # 记账/护栏。
        await pool.enqueue_job("demo_generate", task_id, user_id, _job_id=task_id)
    finally:
        await pool.aclose()
    return TaskSubmitResponse(task_id=task_id)


@router.get("/{task_id}/events")
async def task_events(task_id: str, current_user: CurrentUser) -> EventSourceResponse:
    """SSE 订阅任务事件（AC3/AC4）：鉴权 + 归属校验后转发 progress/result/error。

    归属校验（陷阱⑤）：读 Redis 属主键，非本人（或任务不存在/已过期）一律 404——用 not_found
    而非 403，不泄露「该 taskId 是否存在」（与 byok/usage 账户级资源的 IDOR 处置一脉相承）。
    """
    settings = get_settings()
    # 用独立短连接做归属校验（event_stream 内部另开长连接订阅）。
    owner_redis = Redis.from_url(settings.redis_url)
    try:
        owner = await sse.get_task_owner(owner_redis, task_id)
    finally:
        await owner_redis.aclose()
    if owner != str(current_user.id):
        # 不存在 / 越权都回 404：不区分「无此任务」与「非你的任务」，避免枚举探测（IDOR）。
        raise ErrorEnvelope(
            code="task_not_found",
            message="任务不存在或无权访问。",
            http_status=404,
        )
    return EventSourceResponse(sse.event_stream(settings.redis_url, task_id))
