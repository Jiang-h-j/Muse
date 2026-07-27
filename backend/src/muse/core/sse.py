"""SSE 事件封装：progress / result / error 三事件 + Redis Pub/Sub 回传（Story 2.1，AC3/AC4）。

长时生成（NFR2/AR13）：POST → taskId，GET /api/tasks/{id}/events SSE 推送进度，禁前端轮询。
worker 经 Redis Pub/Sub 推事件，SSE 端点订阅转发（spike P2 已端到端验证含 error 路径）。

**AC4 时序缺口定档（快照补发 + 增量订阅）**：Redis Pub/Sub 不留历史——客户端订阅晚于首个
progress、或刷新/断线重连会丢早期进度（spike P2 明确留的缺口）。本模块定档方案：
`publish_event` 每次同时 SET 快照键（最新态）+ PUBLISH 增量；`event_stream` **先 subscribe、
再读快照补发一次、再听增量**。

**subscribe 必须在读快照之前**（陷阱⑥关键）：若先读快照再 subscribe，两步之间发布的终态事件
（PUBLISH 无订阅者即丢）会永久丢失，导致 SSE 永久挂起。subscribe-first 保证补发窗口后的所有
事件都被 Redis 缓冲、经 listen() 送达；代价仅是「既在快照又在缓冲」的事件重复一次（progress
幂等重复无害，终态在快照分支已 return、不重复）。
"""

import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis

# 三事件名（architecture.md:335，固定契约）：进度 / 成功结果 / 失败。
EVENT_PROGRESS = "progress"
EVENT_RESULT = "result"
EVENT_ERROR = "error"
# 终态事件：收到即结束 SSE 流（后续不再有事件）。
_TERMINAL_EVENTS = frozenset({EVENT_RESULT, EVENT_ERROR})

# Redis 频道 / 快照键命名（按 taskId 隔离，spike P2 频道格式 + 本 story 新增快照键，AC4）。
_CHANNEL_TEMPLATE = "task:{task_id}:events"
_SNAPSHOT_TEMPLATE = "task:{task_id}:snapshot"
# 任务归属键（陷阱⑤ IDOR 防护）：存该 task 属主 user_id，SSE 端点据此校验订阅者本人。
_OWNER_TEMPLATE = "task:{task_id}:owner"
# 快照键 TTL（秒）：任务终结后快照仍可供短时间内重连拿终态，1 小时后自动回收避免键堆积。
_SNAPSHOT_TTL_SECONDS = 3600
# 归属键 TTL：**必须实质长于快照 TTL**。owner 键仅在提交任务时写一次、之后不续期，而 snapshot
# 每次 publish 都续期——若两者相等，owner 会先于 snapshot 过期，导致「任务终结近 1 小时后重连、
# 快照仍在但 owner 已过期」时 SSE 端点鉴权得 None 误返 404，合法属主拿不到本该可读的终态。
# 取 2 倍快照 TTL 保证 owner 覆盖整个快照可读窗口。
_OWNER_TTL_SECONDS = _SNAPSHOT_TTL_SECONDS * 2
# 读 subscribe 确认的超时（秒）：强制 round-trip 保证订阅注册（见 event_stream ①）。给足余量，
# 正常本地/同机 Redis 亚毫秒返回；超时视为拿不到确认，仍继续（listen 会自然阻塞等消息）。
_SUBSCRIBE_CONFIRM_TIMEOUT = 5.0


def task_channel(task_id: str) -> str:
    """该 task 的 Redis Pub/Sub 频道名。"""
    return _CHANNEL_TEMPLATE.format(task_id=task_id)


def task_snapshot_key(task_id: str) -> str:
    """该 task 的 Redis 快照键名（存最新态，供晚订阅/重连补发，AC4）。"""
    return _SNAPSHOT_TEMPLATE.format(task_id=task_id)


def task_owner_key(task_id: str) -> str:
    """该 task 的归属键名（存属主 user_id，供 SSE 端点校验订阅者，陷阱⑤）。"""
    return _OWNER_TEMPLATE.format(task_id=task_id)


async def register_task_owner(redis: Redis, task_id: str, user_id: str) -> None:
    """登记任务属主（提交任务时调用，陷阱⑤）：SSE 端点据此拒绝越权订阅他人任务。"""
    await redis.set(task_owner_key(task_id), user_id, ex=_OWNER_TTL_SECONDS)


async def get_task_owner(redis: Redis, task_id: str) -> str | None:
    """读任务属主 user_id（SSE 端点鉴权用）；不存在（过期/无此任务）返 None。"""
    value = await redis.get(task_owner_key(task_id))
    if value is None:
        return None
    # from_url 默认返 bytes；统一 decode 为 str 供与 current_user.id 字符串比对。
    return value.decode() if isinstance(value, bytes) else str(value)


def format_sse_event(event: str, data: dict[str, object]) -> dict[str, str]:
    """把事件名 + payload 编码为 sse-starlette 的 {event, data} 结构（data 为 JSON 串）。

    payload 须已是 camelCase（如 {step, percent}，Communication Patterns architecture.md:336）——
    调用方保证；本函数只做 JSON 编码，不改字段名。ensure_ascii=False 保留中文可读。
    """
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def publish_event(
    redis: Redis, task_id: str, event: str, data: dict[str, object]
) -> None:
    """发布一个 SSE 事件：SET 快照（覆盖最新态）+ PUBLISH 增量（AC3/AC4）。

    快照与增量载荷一致（{event, data}）——progress 覆盖为最新进度、result/error 置终态，
    保证晚订阅/重连从快照即可拿到当前态；PUBLISH 供已连接的 SSE 实时收增量。
    """
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    channel = task_channel(task_id)
    snapshot_key = task_snapshot_key(task_id)
    # 先写快照再发布：保证「已发布的增量」对应的快照一定已落地——晚订阅者补发不会拿到比
    # 增量更旧的快照（终态尤其重要，重连必须能从快照读到 result/error）。
    await redis.set(snapshot_key, payload, ex=_SNAPSHOT_TTL_SECONDS)
    await redis.publish(channel, payload)


async def event_stream(
    redis_url: str, task_id: str
) -> AsyncIterator[dict[str, str]]:
    """SSE 事件生成器（AC3/AC4）：先订阅、再补发快照、再听增量，收终态即结束。

    用独立 Redis 连接（订阅是长连接、与 worker 的发布连接分离）。ordering 见模块 docstring：
    subscribe-first 消除「读快照与订阅之间丢终态」的竞态。收到 result/error 立即结束流。
    """
    sub = Redis.from_url(redis_url)
    pubsub = sub.pubsub()
    channel = task_channel(task_id)
    try:
        # ① 先订阅，并**读掉 subscribe 确认**强制一次 round-trip——保证订阅已在服务端注册。
        # redis-py 的 subscribe() 只把命令写进 socket，不等服务端确认；若不强制 round-trip 就去
        # 发布/读快照，PUBLISH（另一条连接）可能先于 SUBSCRIBE 被服务端处理，增量丢失。读一次确认
        # 消息即可保证：此刻起服务端已注册订阅，之后所有 PUBLISH 都会被缓冲经 listen() 送达。
        # subscribe/get_message 置于 try 内：Redis 抖动使订阅抛错时，finally 仍关闭连接不泄漏。
        await pubsub.subscribe(channel)
        await pubsub.get_message(timeout=_SUBSCRIBE_CONFIRM_TIMEOUT)
        # ② 再读快照补发一次：捕获订阅注册之前已发布的早期进度 / 已终结任务的终态（AC4）。
        # 订阅已注册（①），故快照读之后新发布的事件必被 listen 捕获——补发与增量之间无丢失窗口。
        snapshot_raw = await sub.get(task_snapshot_key(task_id))
        if snapshot_raw is not None:
            snapshot = json.loads(snapshot_raw)
            yield format_sse_event(snapshot["event"], snapshot["data"])
            # 快照已是终态 → 任务早已结束，直接收尾（重连立即拿终态，不必再听增量）。
            if snapshot["event"] in _TERMINAL_EVENTS:
                return
        # ③ 听增量：送达补发窗口后的所有事件（含可能与快照重复的一次 progress，幂等无害）。
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue  # 跳过 subscribe 确认等非数据消息。
            payload = json.loads(msg["data"])
            yield format_sse_event(payload["event"], payload["data"])
            if payload["event"] in _TERMINAL_EVENTS:
                break
    finally:
        # unsubscribe 可能因连接已断而抛错；嵌套 try 保证 aclose 一定执行、连接不泄漏。
        try:
            await pubsub.unsubscribe(channel)
        finally:
            await pubsub.aclose()
            await sub.aclose()
