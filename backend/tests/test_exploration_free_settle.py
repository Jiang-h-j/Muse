"""Story 2.7 验证：自由探索——「整理为故事设定」开放门禁（AC3/AC4）。

本 story 是**后端 only**切片（受控决策 A：前端接线 defer）+ 复用 2.5 的 settle skeleton
任务（真实凝练归 3.3——Story 3.3 已把该任务接入真实 LLM 凝练并改名 `settle_exploration`）+
护栏 defer（C：skeleton 无成本）。
本 story 相对 2.5 的**净新增**是 AC4 后端门禁硬校验（≥1 条 free 用户消息才放行）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- 门禁 400（AC4，本 story 核心，2.5 无对应）：free-mode project 未发任何消息 → 400
  exploration_not_ready；断言从未登记属主（越权在门禁前短路则不到此，门禁本身也不登记/不入队）。
- 门禁通过 → 正常触发（AC3）：先落 1 条 free 用户消息，再 POST /free/settle → 200 + taskId +
  Redis 登记属主；收尾清孤儿 ARQ job。
- mode 守卫 409（AC4/2.6 AC7）：guided-mode project 调 free/settle → 409 mode_mismatch。
- 租户隔离 404（他人 project）/ 不存在 404（随机 UUID）/ 非法 UUID 422。
- worker 端到端：复用 `settle_exploration` 真实入队消费链路（3.3 已接真实凝练），本文件只验证
  free settle 触发入口正确，不重测 worker 内部（同一任务体，链路等价；凝练本体断言归
  test_story_settle）。
"""

import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from muse.core import sse
from muse.core.db import async_session_maker
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.providers.base import ChatResult
from muse.repositories import exploration_repo
from muse.services import exploration_service, free_explorer_agent, guidance_agent
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """持久事件循环运行 TestClient（与 test_exploration_settle/test_exploration_free 同源治理）。"""
    with _client:
        yield


def _create_project(user: User, headers: dict[str, str], mode: str = "free") -> str:
    """建一部作品并返回其 id（探索会话挂在 project 下，用例前置）。默认 free（本 story 主场景）。"""
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _settle_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/free/settle"


async def _seed_free_user_message(user: User, project_id: str) -> None:
    """通过真实编排落 1 条 free 用户消息（供门禁通过用例前置）。

    直调 `stream_free_chat`（只 mock provider.stream，同 test_exploration_free 持久化用例范式）：
    get-or-create 会话 + 落 user/agent 两条 kind="free" 消息，其中 user 行即门禁校验的对象。
    """

    async def _fake_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
        from muse.providers.base import StreamChunk

        yield StreamChunk(delta="这个方向", kind="content")
        yield StreamChunk(delta="值得展开。", kind="content")

    fake_provider = AsyncMock()
    fake_provider.stream = _fake_stream
    with (
        patch.object(
            free_explorer_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        # 2.8：stream_free_chat 成功落库后追加调用 guidance_agent.refresh_guidance，它是
        # 独立 import 的同名函数引用，需单独 mock（否则真的会打外部 LLM）。空产出即可，
        # refresh_guidance 内部对解析失败保留上一轮 guidance_state 不变。
        patch.object(
            guidance_agent,
            "get_provider_for_user",
            new=AsyncMock(
                return_value=AsyncMock(
                    chat=AsyncMock(
                        return_value=ChatResult(
                            content="",
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                            model="deepseek-v4-flash",
                        )
                    )
                )
            ),
        ),
    ):
        async for _ in free_explorer_agent.stream_free_chat(
            user_id=user.id,
            project_id=uuid.UUID(project_id),
            user_message="我想写一个修仙世界的故事",
        ):
            pass


def _cleanup_enqueued_job(task_id: str) -> None:
    """清「入真队但无 worker 消费」用例遗留的孤儿 ARQ job（避免污染共享 Redis，同 2.5 范式）。"""
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


async def _force_ready_to_settle(user: User, project_id: str) -> None:
    """直接把本会话的 `guidance_state.ready_to_settle` 置真（2.8 门禁前置）。

    本文件聚焦触发端点契约（AC3/AC8），不是 `guidance_agent` 判定逻辑本身的测试场地
    （那归 `test_guidance_agent.py`/`test_exploration_guidance.py`）——故绕过真实 LLM
    判定链路，直调 repo 原语把 7 项主干强制推到 `filled`/`skipped`，只验证「就绪后能
    正常触发」这一件事。
    """
    async with async_session_maker() as session:
        exploration_session = await exploration_service.enter_exploration(
            session, user.id, uuid.UUID(project_id)
        )
        ready_state = {
            "fields": {
                "genre": "filled",
                "core_appeal": "filled",
                "protagonist": "filled",
                "main_conflict": "filled",
                "world_rules": "filled",
                "overall_tone": "filled",
                "opening_hook": "filled",
            },
            "current_field": None,
            "current_question": None,
            "ready_to_settle": True,
        }
        await exploration_repo.update_guidance_state(
            session,
            user_id=user.id,
            project_id=uuid.UUID(project_id),
            session_id=exploration_session.id,
            guidance_state=ready_state,
        )
        await session.commit()


# ========== 离线：触发端点鉴权前置（无 token，不需容器）==========


def test_free_settle_without_token_401() -> None:
    # 未登录触发整理 → 401（CurrentUser 依赖先于业务挡下）。
    resp = _client.post(_settle_url(str(uuid.uuid4())))
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


# ========== 门禁 400（AC4，本 story 核心新增，2.5 无对应）==========


@requires_db
@requires_redis
def test_free_settle_without_message_blocked_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC4：free-mode project 未发任何消息（开场白是前端静态文案、不落库）→ 400 not_ready。
    # spy register_task_owner + create_pool：门禁未通过时绝不登记属主、绝不建池入队
    # （断言未登记 + 未建池 = 未入队，才是完整的「不入队」安全属性，对齐 Task 4）。
    user = make_user("free-settle-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    # 先进入自由探索建会话（但不发任何消息）——证明「有会话但无用户消息」也被门禁挡下。
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200

    with (
        patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register,
        patch.object(exploration_service, "create_pool", new=AsyncMock()) as spy_pool,
    ):
        resp = _client.post(_settle_url(project_id), headers=headers)
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "exploration_not_ready"
    spy_register.assert_not_awaited()
    spy_pool.assert_not_awaited()  # 未建 Redis 池 → 必然未 enqueue_job（门禁 raise 早于建池）


@requires_db
@requires_redis
def test_free_settle_no_session_blocked_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC4 边界：连探索会话都还没建（没 POST /explore）→ 无会话视为无消息 → 400，不 500。
    user = make_user("free-settle-nosession@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)

    with patch.object(exploration_service, "create_pool", new=AsyncMock()) as spy_pool:
        resp = _client.post(_settle_url(project_id), headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "exploration_not_ready"
    spy_pool.assert_not_awaited()  # 未建 Redis 池 → 必然未入队（门禁 raise 早于建池）


@requires_db
@requires_redis
async def test_free_settle_with_message_but_not_ready_still_blocked_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 2.8 AC8 核心回归：2.7 旧判据「≥1 条消息」被本 story **替换**而非「或」关系——即便远
    # 超 1 条消息，7 项主干未全部 filled/skipped 时（guidance_state 恒 missing 初始态，
    # 本用例不驱动 refresh_guidance）仍应 400，不因消息存在而放行。
    user = make_user("free-settle-notready@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    await _seed_free_user_message(user, project_id)

    with patch.object(exploration_service, "create_pool", new=AsyncMock()) as spy_pool:
        resp = _client.post(_settle_url(project_id), headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "exploration_not_ready"
    spy_pool.assert_not_awaited()


# ========== 门禁通过 → 正常触发（AC3）==========


@requires_db
@requires_redis
async def test_free_settle_with_message_returns_task_id_and_registers_owner(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC3/AC8（2.8 门禁替换）：7 项主干全 filled/skipped 后 → POST /free/settle → 200
    # taskId（camelCase）+ Redis 登记属主。落 1 条消息不再足够（2.8 替换 2.7 近似判据），
    # 故本用例额外强制 ready_to_settle=True（判定逻辑本身归 test_guidance_agent.py）。
    user = make_user("free-settle-ready@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    await _seed_free_user_message(user, project_id)
    await _force_ready_to_settle(user, project_id)

    resp = _client.post(_settle_url(project_id), headers=headers)
    assert resp.status_code == 200
    task_id = resp.json()["taskId"]
    assert task_id  # 非空 hex

    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        owner = client.get(sse.task_owner_key(task_id))
        assert owner == str(user.id)
    finally:
        client.delete(sse.task_owner_key(task_id))
        client.close()
        _cleanup_enqueued_job(task_id)  # 清入队遗留的孤儿 ARQ job（无 worker 消费）


# ========== mode 守卫 409（AC4 / 2.6 AC7）==========


@requires_db
@requires_redis
def test_free_settle_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 2.6 AC7 对称补位：guided-mode project 调 free/settle → 409 mode_mismatch（先于门禁）。
    user = make_user("free-settle-guided@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers, mode="guided")

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(_settle_url(project_id), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"
    spy_register.assert_not_awaited()


# ========== 租户守卫 / 存在性 / 参数校验（陷阱①）==========


@requires_db
@requires_redis
def test_free_settle_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 陷阱①：B 对 A 的 free project 触发整理 → 404 project_not_found（越权=不存在，先于门禁）。
    alice = make_user("free-settle-owner-a@example.com")
    bob = make_user("free-settle-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice))

    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(_settle_url(project_id), headers=auth_headers(bob))
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "project_not_found"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_free_settle_nonexistent_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 随机 UUID（压根不存在）→ 与「越权」完全相同的 404 project_not_found（不泄露存在性）。
    user = make_user("free-settle-404@example.com")
    resp = _client.post(_settle_url(str(uuid.uuid4())), headers=auth_headers(user))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
@requires_redis
def test_free_settle_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）。需真实身份：鉴权先于参数校验。
    user = make_user("free-settle-bad-uuid@example.com")
    resp = _client.post(
        "/api/projects/not-a-uuid/explore/free/settle", headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
