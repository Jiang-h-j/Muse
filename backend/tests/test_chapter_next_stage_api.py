"""Story 4.7 验证：下一阶段规划触发端点 POST .../plan-next-stage（AC5，FR22）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- HTTP 触发 + 属主登记（@requires_db @requires_redis，仿 test_chapter_stage_plan_api.py）：
  - 触发返 taskId（camelCase、非空 hex）+ Redis 登记属主
  - 无任何阶段规划 → 400 no_stage_plan（防未规划首阶段就触发下一阶段，且不登记属主）
  - 未确认设定 → 400 bible_not_confirmed（防御）
  - 租户隔离 404（他人 project）
- ARQ 真实入队 → 消费 plan_next_stage → 发布 progress×3 + result（含新 stageNumber）。

造 confirmed bible + 首阶段 stage_plan 用同步 Session 直接造种子。
"""

import json
import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core import sse
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.models.stage_plan import StagePlan
from muse.models.story_bible import StoryBible
from muse.tasks import worker as worker_mod
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    with _client:
        yield


def _create_project(user: User, headers: dict[str, str]) -> str:
    resp = _client.post("/api/projects", json={"mode": "guided"}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_confirmed_bible(engine: Engine, user_id: uuid.UUID, project_id: str) -> None:
    with Session(engine) as session:
        session.add(
            StoryBible(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                genre="修仙",
                core_appeal="逆袭爽感",
                protagonist="林凡",
                main_conflict="对抗宗门",
                world_rules="灵气复苏",
                overall_tone="热血",
                opening_hook="废物觉醒",
                status="confirmed",
            )
        )
        session.commit()


def _seed_stage_plan(
    engine: Engine,
    user_id: uuid.UUID,
    project_id: str,
    stage_number: int = 1,
    goal: str = "站稳外门。",
) -> None:
    with Session(engine) as session:
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                stage_number=stage_number,
                goal=goal,
                chapters=[{"title": "废物觉醒", "brief": "觉醒传承。"}],
            )
        )
        session.commit()


def _next_stage_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/chapters/plan-next-stage"


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


async def _subscribe(redis: Redis, channel: str):
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=5.0)
    return pubsub


async def _drain_pubsub(pubsub) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    saw_terminal = False
    while True:
        timeout = 1.0 if saw_terminal else 5.0
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg is None:
            break
        payload = json.loads(msg["data"])
        events.append((payload["event"], payload["data"]))
        if payload["event"] in (sse.EVENT_RESULT, sse.EVENT_ERROR):
            saw_terminal = True
    return events


def _cleanup_enqueued_job(task_id: str) -> None:
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(sse.task_owner_key(task_id))
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== 离线：鉴权前置 ==========


def test_plan_next_stage_without_token_401() -> None:
    resp = _client.post(_next_stage_url(str(uuid.uuid4())), json={"direction": "x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== HTTP 触发 + 属主登记 ==========


@requires_db
@requires_redis
def test_plan_next_stage_returns_task_and_registers_owner(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """已有首阶段规划 → 触发下一阶段返 taskId + 登记属主。"""
    user = make_user("next-submit@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    _seed_confirmed_bible(db_engine, user.id, project_id)
    _seed_stage_plan(db_engine, user.id, project_id, stage_number=1)

    resp = _client.post(
        _next_stage_url(project_id),
        json={"direction": "让主角开始怀疑同伴"},
        headers=headers,
    )
    assert resp.status_code == 200
    task_id = resp.json()["taskId"]
    assert task_id

    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        assert client.get(sse.task_owner_key(task_id)) == str(user.id)
    finally:
        client.close()
        _cleanup_enqueued_job(task_id)


@requires_db
@requires_redis
def test_plan_next_stage_empty_direction_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """「直接继续」= 空 direction 仍返 taskId（AC7）。"""
    user = make_user("next-empty-dir@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    _seed_confirmed_bible(db_engine, user.id, project_id)
    _seed_stage_plan(db_engine, user.id, project_id, stage_number=1)

    resp = _client.post(_next_stage_url(project_id), json={}, headers=headers)
    assert resp.status_code == 200
    task_id = resp.json()["taskId"]
    assert task_id
    _cleanup_enqueued_job(task_id)


@requires_db
@requires_redis
def test_plan_next_stage_no_stage_plan_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无任何阶段规划 → 400 no_stage_plan（防未规划首阶段就触发下一阶段，不登记属主）。"""
    user = make_user("next-noplan@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    _seed_confirmed_bible(db_engine, user.id, project_id)
    # 不造 stage_plan。

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(
            _next_stage_url(project_id), json={"direction": "x"}, headers=headers
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "no_stage_plan"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_plan_next_stage_not_confirmed_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无 confirmed 设定 → 400 bible_not_confirmed（防御）。"""
    user = make_user("next-noconfirm@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)  # 未造 confirmed bible

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(
            _next_stage_url(project_id), json={"direction": "x"}, headers=headers
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "bible_not_confirmed"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_plan_next_stage_others_project_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("next-owner-a@example.com")
    bob = make_user("next-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice))
    _seed_confirmed_bible(db_engine, alice.id, project_id)
    _seed_stage_plan(db_engine, alice.id, project_id)

    resp = _client.post(
        _next_stage_url(project_id), json={"direction": "x"}, headers=auth_headers(bob)
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


# ========== 端到端：ARQ 真实入队 → 消费 → SSE（含新 stageNumber） ==========


@requires_db
@requires_redis
async def test_plan_next_stage_arq_enqueue_consume_publishes_events(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """真 ARQ 入队 → burst 消费 plan_next_stage → progress×3 + result（带新 stageNumber）。"""
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    assert worker_mod.plan_next_stage in worker_mod.WorkerSettings.functions

    user = make_user("next-arq@example.com")
    project_id = _create_project(user, auth_headers(user))

    fake_plan = MagicMock()
    fake_plan.goal = "进入内门争锋。"
    fake_plan.chapters = [{"title": "内门试炼", "brief": "踏入内门。"}]
    fake_plan.stage_number = 2

    task_id = uuid.uuid4().hex
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))

    pool = await create_pool(redis_settings)
    try:
        with patch.object(
            worker_mod.stage_planner,
            "plan_next_stage",
            new=AsyncMock(return_value=fake_plan),
        ):
            await pool.enqueue_job(
                "plan_next_stage",
                task_id,
                str(user.id),
                project_id,
                "让主角怀疑同伴",
                _job_id=task_id,
            )
            wk = Worker(
                functions=worker_mod.WorkerSettings.functions,
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
    result_data = [d for e, d in events if e == "result"][0]
    assert result_data["status"] == "stage_plan_ready"
    assert result_data["stagePlan"]["stageNumber"] == 2
    assert result_data["stagePlan"]["goal"] == "进入内门争锋。"


# ========== F4a review patch：同 project 重复入队去重 ==========


@requires_db
@requires_redis
def test_plan_next_stage_uses_stable_job_id_for_dedup(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """同 project 触发 plan-next-stage 时 _job_id 稳定（F4a）——ARQ 同 job_id 第二次入队返 None。

    双 tab / 重复点击并发触发 plan-next-stage 时，两个 worker 都读 latest、都算 next=prev+1、
    都 INSERT 撞唯一键、last-write-wins 覆盖——用户看到不同章骨架。修复：`_job_id =
    f"{project_id}:plan_next_stage"` 让 ARQ 同 project 重复入队直接返回 None（不重复执行）。

    本测试断言 service 层 enqueue 的 job_id 形态正确——真实 ARQ 去重由 ARQ 自身
    `_job_id` 参数保证（arq.connections.ArqRedis.enqueue_job 在 _job_id 冲突时返 None）。
    """
    user = make_user("next-jobid@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    _seed_confirmed_bible(db_engine, user.id, project_id)
    _seed_stage_plan(db_engine, user.id, project_id, stage_number=1)

    captured_kwargs: dict = {}

    class _SpyPool:
        async def enqueue_job(self, name, *args, _job_id=None, **kwargs):
            captured_kwargs["name"] = name
            captured_kwargs["args"] = args
            captured_kwargs["_job_id"] = _job_id
            captured_kwargs.update(kwargs)
            return MagicMock(job_id=_job_id)

        async def aclose(self):
            return None

    with (
        patch("muse.services.chapter_service.create_pool", new=AsyncMock(return_value=_SpyPool())),
        patch("muse.services.chapter_service.sse.register_task_owner", new=AsyncMock()),
    ):
        resp = _client.post(
            _next_stage_url(project_id), json={"direction": "x"}, headers=headers
        )
    assert resp.status_code == 200
    assert captured_kwargs["name"] == "plan_next_stage"
    # F4a 核心：_job_id 是 f"{project_id}:plan_next_stage"（不含 task_id），
    # 同 project 重复触发复用 job → ARQ 第二次入队返 None。
    assert captured_kwargs["_job_id"] == f"{project_id}:plan_next_stage"
