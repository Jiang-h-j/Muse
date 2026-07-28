"""Story 2.5 验证：引导收尾「整理为故事设定」触发端点 + skeleton settle 任务（AC2）。

本 story 是**后端 only**切片（受控决策 A：前端接线 defer）+ **管道 skeleton**（受控决策 B：
step 2 占位凝练、真实 LLM 12 字段凝练归 3.3）+ 护栏 defer（受控决策 C：skeleton 无 LLM 成本、
不 check_quota、测试不需 @requires_deepseek）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- HTTP 触发 + 属主登记（@requires_db @requires_redis，仿 test_tasks_sse.py）：
  - 触发返 taskId（camelCase、非空 hex）+ Redis 登记属主（陷阱⑤ 依据）
  - 租户隔离 404（他人 project，越权=不存在，陷阱①）
  - project 不存在 404（随机 UUID，不泄露存在性）
  - 非法 UUID 422（FastAPI 路径解析）
  - settle 产出的 taskId 走 2.1 GET /api/tasks/{taskId}/events、非属主 404
    （坐实 taskId 复用 2.1 IDOR 守卫；属主正向消费归 2.1 event_stream 用例 + 下方 ARQ 端到端用例）
- skeleton 任务逻辑（@requires_db @requires_redis，直调 worker 函数 + _drain_pubsub）：
  - happy：progress×3 + result；answeredCount == 落的答案数（证明读到 2.4 落库的答案）
  - 空答案跑通管道：未落任何答案 → 仍 progress + result（answeredCount==0，陷阱⑨）
  - error 路径：任务内异常 → error（含 code/message）、失败后无 result（陷阱⑧）
- ARQ 真实入队→消费（@requires_db @requires_redis，burst worker）：坐实真实 ARQ 链路 +
  functions 注册（陷阱⑤），非仅直调函数。
"""

import json
import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from muse.core import sse
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.repositories import exploration_repo
from muse.tasks import worker as worker_mod
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """持久事件循环运行 TestClient（与 test_tasks_sse/test_exploration 同源治理）。"""
    with _client:
        yield


def _create_project(user: User, headers: dict[str, str], mode: str = "guided") -> str:
    """建一部作品并返回其 id（探索会话挂在 project 下，用例前置）。"""
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _settle_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/guided/settle"


def _redis() -> Redis:
    """测试用 async Redis 连接（独立于应用单例）。"""
    return Redis.from_url(get_settings().redis_url)


async def _subscribe(redis: Redis, channel: str):
    """订阅频道并读掉 subscribe 确认——强制 round-trip 保证服务端已注册订阅（照 test_tasks_sse）。"""
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=5.0)  # 读掉 subscribe 确认
    return pubsub


async def _drain_pubsub(pubsub, *, until_terminal: bool = True) -> list[tuple[str, dict]]:
    """从已订阅 pubsub 拉取所有缓冲消息，收集 (event, data)。

    命中首个终态（result/error）后**不立刻停**：再以短 timeout 宽限读一次，捕获重复/尾随的终态
    事件——如 ARQ 默认重试（max_tries=5）用同 `_job_id` 重放会二次推 result/error（defer 项所述
    风险）。宽限期内无更多消息才停，故 happy path 只多等一个短 timeout。这样调用方的 `== [...]`
    精确断言能暴露多余终态，不再被「首终态即 break」掩盖。
    """
    events: list[tuple[str, dict]] = []
    saw_terminal = False
    while True:
        # 命中终态后仅作「确认无尾随」的短宽限探测（1s），避免 happy path 恒等满 5s。
        timeout = 1.0 if saw_terminal else 5.0
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg is None:
            break
        payload = json.loads(msg["data"])
        events.append((payload["event"], payload["data"]))
        if until_terminal and payload["event"] in (sse.EVENT_RESULT, sse.EVENT_ERROR):
            saw_terminal = True
    return events


def _make_ctx(session_maker, pub_redis: Redis) -> dict:
    """构造 settle 任务 ctx（模拟 worker on_startup 备好的 session_maker + pub_redis）。"""
    return {"session_maker": session_maker, "pub_redis": pub_redis}


def _cleanup_enqueued_job(task_id: str) -> None:
    """清掉「入真队但无 worker 消费」用例遗留的孤儿 ARQ job（避免污染共享 Redis）。

    触发端点经 `enqueue_job(_job_id=task_id)` 写下 `arq:job:{task_id}` 键并把 task_id 作成员加入
    `arq:queue` 有序集（arq/constants.py）。这些端点用例只验证触发契约、不起 worker，若不清理，
    同库有 dev worker 在跑会真的消费这些 settle 任务（且孤儿 job 键长期滞留）。owner/snapshot 键
    由各用例 finally 自行清，此处专清 ARQ 侧。
    """
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== 离线：触发端点鉴权前置（无 token，不需容器）==========


def test_settle_without_token_401() -> None:
    # 未登录触发整理 → 401（CurrentUser 依赖先于业务挡下）。
    resp = _client.post(_settle_url(str(uuid.uuid4())))
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "token_invalid"


# ========== HTTP 触发 + 属主登记（IDOR 陷阱⑤ / 租户守卫陷阱①）==========


@requires_db
@requires_redis
def test_settle_returns_task_id_and_registers_owner(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC2：POST .../settle → 200 taskId（camelCase）；并登记属主到 Redis（供 2.1 SSE 端点鉴权）。
    user = make_user("settle-submit@example.com")
    project_id = _create_project(user, auth_headers(user))

    resp = _client.post(_settle_url(project_id), headers=auth_headers(user))
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
        _cleanup_enqueued_job(task_id)  # 清入队遗留的孤儿 ARQ job（无 worker 消费）


@requires_db
@requires_redis
def test_settle_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 陷阱①：B 对 A 的 project 触发整理 → 404 project_not_found（越权=不存在，不 403、不泄露）。
    alice = make_user("settle-owner-a@example.com")
    bob = make_user("settle-owner-b@example.com")
    project_id = _create_project(alice, auth_headers(alice))

    # spy register_task_owner：越权应在租户守卫处短路，绝不走到登记属主/入队。断言「从未登记属主」
    # 才是真正的安全属性——旧断言 `"taskId" not in body` 对 404 封套 {code,message,detail} 恒真、
    # 给假安全感（并未证明未入队/未登记）。
    with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
        resp = _client.post(_settle_url(project_id), headers=auth_headers(bob))
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}  # AR5 envelope 三要素
    assert body["code"] == "project_not_found"
    # 越权在守卫处短路：从未登记属主（若有人把租户守卫挪到 register 之后，此断言即失败）。
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_settle_nonexistent_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 随机 UUID（压根不存在）→ 与「越权」完全相同的 404 project_not_found（不泄露存在性）。
    user = make_user("settle-404@example.com")
    resp = _client.post(_settle_url(str(uuid.uuid4())), headers=auth_headers(user))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
@requires_redis
def test_settle_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 非法 UUID 路径参数 → 422（FastAPI 类型解析）。需真实身份：鉴权先于参数校验。
    user = make_user("settle-bad-uuid@example.com")
    resp = _client.post(
        "/api/projects/not-a-uuid/explore/guided/settle", headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
@requires_redis
def test_settle_task_id_events_rejects_non_owner_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 坐实 settle 产出的 taskId 复用 2.1 IDOR 守卫：走 GET /api/tasks/{taskId}/events，非属主订阅
    # → 404（陷阱⑤/⑪，不区分不存在/越权，防枚举探测他人整理进度）。
    # 范围说明：**属主正向消费**（alice 经 GET /events 拿到 progress/result 流）不在此测——
    # ① GET /events 是 2.1 未改的通用端点，其 event_stream 正向补发/增量消费已由
    #   test_tasks_sse.py 的 event_stream generator 层用例坐实；
    # ② 无 worker 时任务永不到终态，属主 GET /events 会阻塞挂起（SSE 长流），TestClient 不宜直测；
    # ③ settle→任务真实跑→事件流全链路由 test_settle_arq_enqueue_consume_publishes_events
    #   （burst worker）端到端坐实。
    # 故此处只验「settle taskId 经 2.1 守卫拒非属主」，属主端到端消费归前端集成切片。
    alice = make_user("settle-events-a@example.com")
    bob = make_user("settle-events-b@example.com")
    project_id = _create_project(alice, auth_headers(alice))
    task_id = _client.post(
        _settle_url(project_id), headers=auth_headers(alice)
    ).json()["taskId"]
    try:
        # B 尝试订阅 A 的 settle 任务 → 404。
        resp = _client.get(
            f"/api/tasks/{task_id}/events", headers=auth_headers(bob)
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "task_not_found"
    finally:
        import redis as sync_redis

        client = sync_redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True
        )
        client.delete(sse.task_owner_key(task_id))
        client.close()
        _cleanup_enqueued_job(task_id)  # 清入队遗留的孤儿 ARQ job（无 worker 消费）


# ========== skeleton 任务逻辑（直调 worker 函数 + _drain_pubsub）==========


async def _post_answer(
    project_id: str, headers: dict[str, str], *, index: int, answer: str
) -> None:
    """经真实 HTTP 落一条引导答案（用 2.4 端点，验证 settle 任务能读到 2.4 落的答案）。"""
    resp = _client.post(
        f"/api/projects/{project_id}/explore/guided/answers",
        json={
            "questionIndex": index,
            "question": f"问题{index}",
            "answer": answer,
            "answerType": "option",
        },
        headers=headers,
    )
    assert resp.status_code == 200


@requires_db
@requires_redis
async def test_settle_task_happy_reads_answers_and_publishes(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # happy：直调 settle_guided_exploration → progress×3 + result；answeredCount == 落的答案数
    # （证明整理任务能读到 2.4 落库的答案，是 3.3 真实凝练的前提）。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("settle-happy@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    # 经 HTTP 落 3 条答案（真实 2.4 路径）。
    await _post_answer(project_id, headers, index=0, answer="答案0")
    await _post_answer(project_id, headers, index=1, answer="答案1")
    await _post_answer(project_id, headers, index=2, answer="答案2")

    task_id = uuid.uuid4().hex
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        await worker_mod.settle_guided_exploration(
            _make_ctx(session_maker, pub), task_id, str(user.id), project_id
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
    # result 占位 payload camelCase；answeredCount == 落的 3 条（证明读到 2.4 答案）。
    result_data = [d for e, d in events if e == "result"][0]
    assert result_data["taskId"] == task_id
    assert result_data["status"] == "settle_pending"
    assert result_data["answeredCount"] == 3


@requires_db
@requires_redis
async def test_settle_task_empty_answers_still_runs(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 陷阱⑨：未落任何答案（连探索会话都没建）→ 任务仍推 progress + result（answeredCount==0），
    # skeleton 不因空答案失败（前端契约保证只在收尾态触发，但任务本身不脆弱）。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("settle-empty@example.com")
    project_id = _create_project(user, auth_headers(user))

    task_id = uuid.uuid4().hex
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        await worker_mod.settle_guided_exploration(
            _make_ctx(session_maker, pub), task_id, str(user.id), project_id
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
    result_data = [d for e, d in events if e == "result"][0]
    assert result_data["answeredCount"] == 0


@requires_db
@requires_redis
async def test_settle_task_error_path_publishes_error(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 陷阱⑧：任务内异常（mock repo 抛错）→ 推 error（含 code/message、泛化文案）、失败后无 result。
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    user = make_user("settle-error@example.com")
    project_id = _create_project(user, auth_headers(user))

    task_id = uuid.uuid4().hex
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        # 让读会话步骤抛错，验证 error 事件经同一链路推达（step 1 之后）。
        with patch.object(
            exploration_repo,
            "get_session_by_project",
            side_effect=RuntimeError("模拟读答案失败"),
        ):
            with pytest.raises(RuntimeError):
                await worker_mod.settle_guided_exploration(
                    _make_ctx(session_maker, pub), task_id, str(user.id), project_id
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
    # step 1 progress 已推，读答案抛错 → error；无 result。
    assert kinds == ["progress", "error"]
    error_data = [d for e, d in events if e == "error"][0]
    assert error_data["code"] == "settle_failed"
    assert "message" in error_data
    # 泛化文案，不外泄原始异常细节（陷阱⑧）。
    assert "模拟读答案失败" not in error_data["message"]


# ========== 端到端：ARQ 真实入队 → 消费 → SSE（burst worker，陷阱⑤ functions 注册）==========


@requires_db
@requires_redis
async def test_settle_arq_enqueue_consume_publishes_events(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 真 ARQ 入队 → burst worker 消费 settle_guided_exploration → 发布 progress×3 + result。
    # 坐实真实 ARQ 链路 + WorkerSettings.functions 注册（陷阱⑤：漏注册则无 handler 静默失败）。
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    # 前置断言：settle 任务确在 WorkerSettings.functions（生产注册表）内——否则本用例
    # 无从坐实注册（若手搭 functions=[settle_...] 则即便生产漏注册也照样绿，见陷阱⑤）。
    assert worker_mod.settle_guided_exploration in worker_mod.WorkerSettings.functions

    user = make_user("settle-arq@example.com")
    headers = auth_headers(user)
    project_id = _create_project(user, headers)
    await _post_answer(project_id, headers, index=0, answer="arq答案")

    task_id = uuid.uuid4().hex
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))

    pool = await create_pool(redis_settings)
    try:
        await pool.enqueue_job(
            "settle_guided_exploration",
            task_id,
            str(user.id),
            project_id,
            _job_id=task_id,
        )
        # burst=True：消费完队列即退出；handle_signals=False：不装信号处理器（避免与 pytest 冲突）。
        # functions 直接取自生产 WorkerSettings.functions——若有人从注册表移除 settle 任务，
        # 此处 handler 缺失、任务静默不执行、SSE 收不到事件、下方断言失败（真正回归陷阱⑤）。
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
    assert result_data["answeredCount"] == 1
