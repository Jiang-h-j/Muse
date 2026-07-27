"""Story 2.1 验证：SSE 三事件 + ARQ 示范任务 + 任务提交/订阅端点（AC3/AC4）。

- 离线（不需容器）：任务端点鉴权缺失 401（CurrentUser 前置）。
- SSE 层（@requires_redis，真 Redis 无需 worker，确定性无 sleep）：
  - publish_event 同时写快照 + 发布
  - event_stream 补发快照（晚订阅不丢早期进度，AC4）——**先发布落快照、再连接**，确定性
  - event_stream 补发后继续听增量（subscribe 在 backfill yield 之前完成，故收到首个补发事件即证明
    已订阅，后续发布必被 listen 捕获——无需 sleep 协调，规避测试竞态）
  - 终态任务重连立即拿 result/error（AC4）
- 端到端（@requires_redis + @requires_db）：
  - demo_generate happy：progress×3 + result；串起 check_quota → provider → record_usage（兑现 1.8）
  - demo_generate error：fail 分支 → progress×1 + error（含 code/message）
  - ARQ 真实入队→消费→SSE（burst worker，照 spike 结构）
  - HTTP POST /api/tasks/demo → taskId + 登记属主；SSE 端点归属校验（他人任务 404，陷阱⑤）
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from muse.core import sse
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import UsageLedger, User
from muse.tasks import worker as worker_mod
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """持久事件循环运行 TestClient（与 test_byok/test_usage 同源）。"""
    with _client:
        yield


def _redis() -> Redis:
    """测试用 async Redis 连接（独立于应用单例）。"""
    return Redis.from_url(get_settings().redis_url)


async def _subscribe(redis: Redis, channel: str):
    """订阅频道并读掉 subscribe 确认——强制 round-trip 保证服务端已注册订阅。

    redis-py 的 subscribe() 只写命令不等确认；若不强制 round-trip 就 publish（另一连接），
    PUBLISH 可能先于 SUBSCRIBE 被处理、消息丢失（与 core/sse.event_stream ① 同源治理）。
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=5.0)  # 读掉 subscribe 确认
    return pubsub


async def _drain_pubsub(pubsub, *, until_terminal: bool = True) -> list[tuple[str, dict]]:
    """从已订阅的 pubsub 拉取所有缓冲消息，收集 (event, data)；收到终态即停。

    用 get_message(timeout) 而非 listen()——可确定性地在无更多消息时返回，不挂起（无 sleep）。
    """
    events: list[tuple[str, dict]] = []
    while True:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
        if msg is None:
            break
        payload = json.loads(msg["data"])
        events.append((payload["event"], payload["data"]))
        if until_terminal and payload["event"] in (sse.EVENT_RESULT, sse.EVENT_ERROR):
            break
    return events


# ========== 离线：任务端点鉴权前置（无 token，不需容器）==========


def test_submit_demo_without_token_401() -> None:
    # 未登录提交示范任务 → 401（CurrentUser 依赖先于业务挡下）。
    resp = _client.post("/api/tasks/demo")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_task_events_without_token_401() -> None:
    # 未登录订阅事件 → 401（SSE 端点也须鉴权，陷阱⑤）。
    resp = _client.get(f"/api/tasks/{uuid.uuid4().hex}/events")
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== SSE 层：publish_event 写快照 + 发布（AC3/AC4）==========


@requires_redis
async def test_publish_event_writes_snapshot_and_publishes() -> None:
    # publish_event 同时 SET 快照键（供补发）+ PUBLISH（供实时）。
    redis = _redis()
    task_id = uuid.uuid4().hex
    try:
        await sse.publish_event(redis, task_id, sse.EVENT_PROGRESS, {"step": 1, "percent": 33})
        snapshot_raw = await redis.get(sse.task_snapshot_key(task_id))
        assert snapshot_raw is not None
        snapshot = json.loads(snapshot_raw)
        assert snapshot["event"] == "progress"
        assert snapshot["data"] == {"step": 1, "percent": 33}
    finally:
        await redis.delete(sse.task_snapshot_key(task_id))
        await redis.aclose()


@requires_redis
async def test_event_stream_backfills_snapshot_for_late_subscriber() -> None:
    # AC4：先发布几个 progress 落快照，**再**连接 SSE → 首个事件是补发的最新快照（晚订阅不丢进度）。
    # 之后继续听增量（subscribe 在 backfill yield 前完成，收到补发即证明已订阅，后续发布必被捕获）。
    redis = _redis()
    task_id = uuid.uuid4().hex
    try:
        # 连接前先发布两个 progress——纯 Pub/Sub 会丢，快照保留最新（step 2）。
        await sse.publish_event(redis, task_id, sse.EVENT_PROGRESS, {"step": 1, "percent": 33})
        await sse.publish_event(redis, task_id, sse.EVENT_PROGRESS, {"step": 2, "percent": 66})

        gen: AsyncIterator[dict[str, str]] = sse.event_stream(
            get_settings().redis_url, task_id
        )
        # 首个 yield = 补发的最新快照（step 2），证明晚订阅补回了早期进度。
        first = await gen.__anext__()
        assert first["event"] == "progress"
        assert json.loads(first["data"]) == {"step": 2, "percent": 66}

        # 此刻 generator 已 subscribe（在 backfill yield 之前），现发布 result 必被 listen 捕获。
        await sse.publish_event(
            redis, task_id, sse.EVENT_RESULT, {"taskId": task_id, "chapterText": "done"}
        )
        second = await gen.__anext__()
        assert second["event"] == "result"
        assert json.loads(second["data"])["chapterText"] == "done"
        # 收到终态后 generator 结束。
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await redis.delete(sse.task_snapshot_key(task_id))
        await redis.aclose()


@requires_redis
async def test_event_stream_terminal_snapshot_reconnect_gets_terminal_immediately() -> None:
    # AC4：已终结（result）任务重连 → 立即从快照拿终态，流随即结束（不必再听增量）。
    redis = _redis()
    task_id = uuid.uuid4().hex
    try:
        await sse.publish_event(
            redis, task_id, sse.EVENT_RESULT, {"taskId": task_id, "chapterText": "final"}
        )
        gen = sse.event_stream(get_settings().redis_url, task_id)
        first = await gen.__anext__()
        assert first["event"] == "result"
        assert json.loads(first["data"])["chapterText"] == "final"
        # 终态快照 → 补发后立即结束。
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await redis.delete(sse.task_snapshot_key(task_id))
        await redis.aclose()


@requires_redis
async def test_event_stream_error_snapshot_reconnect() -> None:
    # AC4：已终结（error）任务重连 → 立即拿 error 终态（含 code/message）。
    redis = _redis()
    task_id = uuid.uuid4().hex
    try:
        await sse.publish_event(
            redis, task_id, sse.EVENT_ERROR, {"code": "generate_failed", "message": "boom"}
        )
        gen = sse.event_stream(get_settings().redis_url, task_id)
        first = await gen.__anext__()
        assert first["event"] == "error"
        assert json.loads(first["data"]) == {"code": "generate_failed", "message": "boom"}
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
    finally:
        await redis.delete(sse.task_snapshot_key(task_id))
        await redis.aclose()


# ========== 端到端：demo_generate 任务逻辑（真 Redis + 真 DB，AC3/AC5/AC6）==========


def _make_ctx(session_maker, pub_redis: Redis) -> dict:
    """构造 demo_generate 的 ctx（模拟 worker on_startup 备好的 session_maker + pub_redis）。"""
    return {"session_maker": session_maker, "pub_redis": pub_redis}


@requires_db
@requires_redis
async def test_demo_generate_happy_path_publishes_and_records_usage(
    make_user: Callable[..., User],
) -> None:
    # AC3/AC5/AC6：happy path 推 progress×3 + result；串起 check_quota → provider(mock)
    # → record_usage。patch AsyncOpenAI 避免真实网络：真实 MeteredProvider.chat →
    # record_usage 写真实 usage_ledger 行。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("task-happy@example.com")
    task_id = uuid.uuid4().hex
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))

    # mock openai chat 响应：让托管 DeepSeekProvider.chat 返回带 usage 的结果 → record_usage 落库。
    fake_msg = MagicMock()
    fake_msg.content = "（生成的开场）"
    del fake_msg.reasoning_content
    fake_usage = MagicMock(prompt_tokens=30, completion_tokens=20, total_tokens=50)
    fake_resp = MagicMock(choices=[MagicMock(message=fake_msg)], usage=fake_usage)
    try:
        # patch.object 强制 deepseek_api_key 非空：demo_generate 用 `if settings.deepseek_api_key:`
        # 作真实生成门槛，若依赖本机 .env（干净 CI 为空）则跳过记账分支、断言失败——本 story「兑现
        # 1.8 记账闭合」的旗舰验证必须确定性走到记账，故显式注入而非依赖环境。AsyncOpenAI 已 mock，
        # 此 key 不发真实网络。
        with (
            patch.object(get_settings(), "deepseek_api_key", "test-key"),
            patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls,
        ):
            mock_cls.return_value.chat.completions.create = AsyncMock(return_value=fake_resp)
            await worker_mod.demo_generate(
                _make_ctx(session_maker, pub), task_id, str(user.id), fail=False
            )
        events = await _drain_pubsub(pubsub)
    finally:
        await pubsub.unsubscribe(sse.task_channel(task_id))
        await pubsub.aclose()
        await sub.aclose()
        await pub.delete(sse.task_snapshot_key(task_id))
        await pub.aclose()
        await engine.dispose()

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "progress", "result"]
    # progress payload camelCase {step, percent}。
    progress_data = [d for e, d in events if e == "progress"]
    assert all("step" in d and "percent" in d for d in progress_data)
    result_data = [d for e, d in events if e == "result"][0]
    assert result_data["taskId"] == task_id

    # 记账串联（兑现 1.8）：usage_ledger 落了一行 hosted、total_tokens = API usage 的 50。
    from tests.conftest import _sync_engine

    with Session(_sync_engine()) as session:
        row = session.scalar(select(UsageLedger).where(UsageLedger.user_id == user.id))
        assert row is not None
        assert row.billing_path == "hosted"
        assert row.total_tokens == 50  # API usage，非本地估算


@requires_db
@requires_redis
async def test_demo_generate_error_path_publishes_error(
    make_user: Callable[..., User],
) -> None:
    # AC3：fail 分支 → progress×1 + error（含 code/message）；失败后无 result。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("task-error@example.com")
    task_id = uuid.uuid4().hex
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        with pytest.raises(RuntimeError):
            await worker_mod.demo_generate(
                _make_ctx(session_maker, pub), task_id, str(user.id), fail=True
            )
        events = await _drain_pubsub(pubsub)
    finally:
        await pubsub.unsubscribe(sse.task_channel(task_id))
        await pubsub.aclose()
        await sub.aclose()
        await pub.delete(sse.task_snapshot_key(task_id))
        await pub.aclose()
        await engine.dispose()

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "error"]  # 第 2 步失败：仅第 1 步 progress，无 result
    error_data = [d for e, d in events if e == "error"][0]
    assert error_data["code"] == "generate_failed"
    assert "message" in error_data


# ========== 端到端：ARQ 真实入队 → 消费 → SSE（burst worker，照 spike 结构）==========


@requires_db
@requires_redis
async def test_arq_enqueue_consume_publishes_events(
    make_user: Callable[..., User],
) -> None:
    # AC3：真 ARQ 入队 → burst worker 消费 → Redis 发布 progress×3 + result（端到端，照 spike）。
    # 先订阅（确定性）再运行 worker，故所有事件被缓冲捕获。patch openai 避免真实网络。
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    user = make_user("task-arq@example.com")
    task_id = uuid.uuid4().hex
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))

    fake_msg = MagicMock()
    fake_msg.content = "arq 生成"
    del fake_msg.reasoning_content
    fake_usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    fake_resp = MagicMock(choices=[MagicMock(message=fake_msg)], usage=fake_usage)

    pool = await create_pool(redis_settings)
    try:
        await pool.enqueue_job("demo_generate", task_id, str(user.id), _job_id=task_id)
        # burst=True：消费完队列即退出；handle_signals=False：不装信号处理器（避免与 pytest 冲突）。
        with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(return_value=fake_resp)
            wk = Worker(
                functions=[worker_mod.demo_generate],
                redis_settings=redis_settings,
                on_startup=worker_mod.on_startup,
                on_shutdown=worker_mod.on_shutdown,
                burst=True,
                handle_signals=False,
                poll_delay=0.1,
            )
            await wk.async_run()
        events = await _drain_pubsub(pubsub)
    finally:
        await pubsub.unsubscribe(sse.task_channel(task_id))
        await pubsub.aclose()
        await sub.aclose()
        await pool.aclose()
        cleanup = _redis()
        await cleanup.delete(sse.task_snapshot_key(task_id))
        await cleanup.aclose()

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "progress", "result"]


# ========== 端到端：HTTP 提交 + SSE 归属校验（IDOR，陷阱⑤）==========


@requires_db
@requires_redis
def test_submit_demo_returns_task_id_and_registers_owner(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC3：POST /api/tasks/demo → 200 taskId（camelCase）；并登记属主到 Redis（供 SSE 鉴权）。
    user = make_user("task-submit@example.com")
    resp = _client.post("/api/tasks/demo", headers=auth_headers(user))
    assert resp.status_code == 200
    task_id = resp.json()["taskId"]
    assert task_id  # 非空 hex

    # 属主已登记为该用户（陷阱⑤ 依据）。
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        owner = client.get(sse.task_owner_key(task_id))
        assert owner == str(user.id)
    finally:
        client.delete(sse.task_owner_key(task_id))
        client.close()


@requires_db
@requires_redis
def test_task_events_rejects_non_owner_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 陷阱⑤ IDOR：B 订阅 A 的任务 → 404（不区分不存在/越权，防枚举探测他人进度）。
    alice = make_user("task-owner-a@example.com")
    bob = make_user("task-owner-b@example.com")
    # A 提交任务。
    task_id = _client.post("/api/tasks/demo", headers=auth_headers(alice)).json()["taskId"]
    try:
        # B 尝试订阅 A 的任务 → 404。
        resp = _client.get(f"/api/tasks/{task_id}/events", headers=auth_headers(bob))
        assert resp.status_code == 404
        assert resp.json()["code"] == "task_not_found"
        # 不存在的 taskId 同样 404（同一处置，不泄露存在性）。
        resp2 = _client.get(
            f"/api/tasks/{uuid.uuid4().hex}/events", headers=auth_headers(alice)
        )
        assert resp2.status_code == 404
    finally:
        import redis as sync_redis

        client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        client.delete(sse.task_owner_key(task_id))
        client.close()
