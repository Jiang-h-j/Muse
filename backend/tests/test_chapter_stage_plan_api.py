"""Story 4.3 Task 3 验证：阶段规划触发端点 + GET 恢复端点 + ARQ 消费链（AC1/AC2/AC6）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- HTTP 触发 + 属主登记（@requires_db @requires_redis，仿 test_exploration_settle.py）：
  - 触发返 taskId（camelCase、非空 hex）+ Redis 登记属主（陷阱⑤ 依据）
  - 未确认设定 → 400 bible_not_confirmed（不给未确认作品排任务，防御）
  - 租户隔离 404（他人 project）/ 不存在 404 / 非法 UUID 422
- GET 恢复端点：无阶段规划 → 204；有 → 200 + camelCase 阶段规划
- ARQ 真实入队→消费（burst worker，stage_planner mock）：坐实真实链路 + functions 注册（陷阱⑤）

造 confirmed bible 用同步 Session 直接 status="confirmed"（触发前置校验依赖）。
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
    """给作品造一份 confirmed 设定圣经（触发阶段规划的前置校验依赖）。"""
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


def _plan_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/chapters/plan-stage"


def _stage_plan_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/chapters/stage-plan"


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
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== 离线：鉴权前置 ==========


def test_plan_stage_without_token_401() -> None:
    resp = _client.post(_plan_url(str(uuid.uuid4())))
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== HTTP 触发 + 属主登记 ==========


@requires_db
@requires_redis
def test_plan_stage_returns_task_id_and_registers_owner(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("plan-submit@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    _seed_confirmed_bible(db_engine, user.id, project_id)

    resp = _client.post(_plan_url(project_id), headers=headers)
    assert resp.status_code == 200
    task_id = resp.json()["taskId"]
    assert task_id

    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        owner = client.get(sse.task_owner_key(task_id))
        assert owner == str(user.id)
    finally:
        client.delete(sse.task_owner_key(task_id))
        client.close()
        _cleanup_enqueued_job(task_id)


@requires_db
@requires_redis
def test_plan_stage_not_confirmed_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无 confirmed 设定 → 400 bible_not_confirmed（不给未确认作品排任务，且从不登记属主）。"""
    user = make_user("plan-noconfirm@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)  # 未造 confirmed bible

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(_plan_url(project_id), headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "bible_not_confirmed"
    # 前置未过：从未登记属主/入队。
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_plan_stage_others_project_returns_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("plan-owner-a@example.com")
    bob = make_user("plan-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice))
    _seed_confirmed_bible(db_engine, alice.id, project_id)

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(_plan_url(project_id), headers=auth_headers(bob))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_plan_stage_nonexistent_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("plan-404@example.com")
    resp = _client.post(_plan_url(str(uuid.uuid4())), headers=auth_headers(user))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
@requires_redis
def test_plan_stage_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("plan-bad-uuid@example.com")
    resp = _client.post(
        "/api/projects/not-a-uuid/chapters/plan-stage", headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ========== GET 恢复端点 ==========


@requires_db
@requires_redis
def test_get_stage_plan_absent_returns_204(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("plan-get-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    resp = _client.get(_stage_plan_url(project_id), headers=headers)
    assert resp.status_code == 204


@requires_db
@requires_redis
def test_get_stage_plan_present_returns_200(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """有阶段规划 → 200 + camelCase 阶段规划（用同步 Session 直接造种子）。"""
    from muse.models.stage_plan import StagePlan

    user = make_user("plan-get-present@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)

    with Session(db_engine) as session:
        session.add(
            StagePlan(
                user_id=user.id,
                project_id=uuid.UUID(project_id),
                goal="站稳外门。",
                chapters=[{"title": "废物觉醒", "brief": "觉醒传承。"}],
            )
        )
        session.commit()

    resp = _client.get(_stage_plan_url(project_id), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stageNumber"] == 1
    assert body["goal"] == "站稳外门。"
    assert body["chapters"][0]["title"] == "废物觉醒"
    assert body["chapters"][0]["brief"] == "觉醒传承。"


# ========== 端到端：ARQ 真实入队 → 消费 → SSE ==========


@requires_db
@requires_redis
async def test_plan_stage_arq_enqueue_consume_publishes_events(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """真 ARQ 入队 → burst worker 消费 plan_first_stage → 发布 progress×3 + result。

    坐实真实 ARQ 链路 + WorkerSettings.functions 注册（陷阱⑤）。stage_planner mock（burst
    worker 同进程，patch 可见）——不打真实 LLM，只验 ARQ 链路。
    """
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    assert worker_mod.plan_first_stage in worker_mod.WorkerSettings.functions

    user = make_user("plan-arq@example.com")
    project_id = _create_project(user, auth_headers(user))

    fake_plan = MagicMock()
    fake_plan.goal = "站稳外门。"
    fake_plan.chapters = [{"title": "废物觉醒", "brief": "觉醒传承。"}]
    fake_plan.stage_number = 1

    task_id = uuid.uuid4().hex
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))

    pool = await create_pool(redis_settings)
    try:
        with patch.object(
            worker_mod.stage_planner,
            "plan_first_stage",
            new=AsyncMock(return_value=fake_plan),
        ):
            await pool.enqueue_job(
                "plan_first_stage",
                task_id,
                str(user.id),
                project_id,
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
    assert result_data["stagePlan"]["goal"] == "站稳外门。"
    assert result_data["stagePlan"]["chapters"][0]["title"] == "废物觉醒"
