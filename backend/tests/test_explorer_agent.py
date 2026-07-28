"""Story 2.3 验证：引导探索——真实 Explorer Agent 理解自述 + 流式 SSE 端点（AC4 全覆盖）。

- 编排单元（离线，mock get_provider_for_user + check_quota，不打真实 API，CI 必过）：
  - interpret_guided_answer happy：逐 content 块透传、reasoning 静默丢弃、StreamUsage 不外产。
  - preflight 护栏拦截（承 2.1 AC6）：check_quota 抛 429 → provider 未被构造/调用。
  - preflight 租户隔离（承 2.2 陷阱①）：get_owned_project 返 None → 404 project_not_found。
  - prompt 契约最小断言：messages 含 system prompt + user 消息携题干与自述（防未来误删约束）。
- SSE 端点（@requires_db，完整 HTTP 栈 + 真实 DB 建 user/project，provider mock）：
  鉴权 401 / happy delta→done（camelCase）/ 422 空 freeText / 护栏 429 / 租户 404。
  **不需 @requires_redis**（直连流式非 ARQ，陷阱⑤）。
- 真实契约见 test_providers.py::test_real_deepseek_stream_contract（@requires_deepseek，Task 4）。
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.providers.base import StreamChunk, StreamUsage
from muse.services import explorer_agent
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    """上下文管理器模式跑 TestClient：所有请求共享同一持久事件循环（与 test_exploration 同源）。"""
    with _client:
        yield


# ========== 离线：interpret_guided_answer 编排单元（mock provider + check_quota）==========


async def _fake_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
    """假 provider.stream：吐 reasoning + content×2 + 末尾 StreamUsage（模拟真实事件序列）。"""
    yield StreamChunk(delta="思考中", kind="reasoning")
    yield StreamChunk(delta="一个在雨夜里", kind="content")
    yield StreamChunk(delta="收到陌生人来信的人。", kind="content")
    yield StreamUsage(
        prompt_tokens=20, completion_tokens=10, total_tokens=30, model="deepseek-v4-flash"
    )


async def test_interpret_yields_content_only_drops_reasoning_and_usage() -> None:
    # AC4：逐 content 块透传；reasoning 片段静默丢弃；StreamUsage 不外产（供上层拼 done.text）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    fake_provider = MagicMock()
    fake_provider.stream = _fake_stream
    with (
        patch.object(
            explorer_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(explorer_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            explorer_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(explorer_agent, "async_session_maker", _fake_session_maker()),
    ):
        deltas = [
            d
            async for d in explorer_agent.interpret_guided_answer(
                user_id=uid,
                project_id=pid,
                question="脑中最先亮起的画面？",
                free_text="一个收到信的人",
            )
        ]
    # 只见 content 正文块，reasoning「思考中」与 StreamUsage 均不在产出里。
    assert deltas == ["一个在雨夜里", "收到陌生人来信的人。"]
    assert "".join(deltas) == "一个在雨夜里收到陌生人来信的人。"


async def test_interpret_quota_exceeded_blocks_before_provider() -> None:
    # 陷阱②：check_quota 抛 429 时 provider 未被构造/调用（护栏在生成前，别先生成再判额度）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    quota_err = ErrorEnvelope(
        code="quota_exceeded", message="额度已用完", http_status=429
    )
    with (
        patch.object(
            explorer_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(
            explorer_agent.usage_service,
            "check_quota",
            new=AsyncMock(side_effect=quota_err),
        ),
        patch.object(
            explorer_agent, "get_provider_for_user", new=AsyncMock()
        ) as get_provider,
        patch.object(explorer_agent, "async_session_maker", _fake_session_maker()),
        pytest.raises(ErrorEnvelope) as exc_info,
    ):
        async for _ in explorer_agent.interpret_guided_answer(
            user_id=uid, project_id=pid, question="题", free_text="自述"
        ):
            pass
    assert exc_info.value.code == "quota_exceeded"
    assert exc_info.value.http_status == 429
    get_provider.assert_not_awaited()  # 护栏在前：provider 根本没被构造


async def test_interpret_tenant_guard_returns_404_before_provider() -> None:
    # 陷阱③：get_owned_project 返 None → 404 project_not_found；provider 未被构造。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    with (
        patch.object(
            explorer_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            explorer_agent.usage_service, "check_quota", new=AsyncMock()
        ) as check_quota,
        patch.object(
            explorer_agent, "get_provider_for_user", new=AsyncMock()
        ) as get_provider,
        patch.object(explorer_agent, "async_session_maker", _fake_session_maker()),
        pytest.raises(ErrorEnvelope) as exc_info,
    ):
        async for _ in explorer_agent.interpret_guided_answer(
            user_id=uid, project_id=pid, question="题", free_text="自述"
        ):
            pass
    assert exc_info.value.code == "project_not_found"
    assert exc_info.value.http_status == 404
    # 租户守卫在最前：护栏与 provider 都不该被触及。
    check_quota.assert_not_awaited()
    get_provider.assert_not_awaited()


async def test_interpret_builds_messages_with_system_prompt_and_free_text() -> None:
    # 去 AI 味/单一职责契约最小断言：组装的 messages 含 system prompt + user 消息携题干与自述。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    captured: dict[str, object] = {}

    async def _capturing_stream(messages: list[dict[str, str]], **kwargs: object):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        yield StreamChunk(delta="答案。", kind="content")
        yield StreamUsage(
            prompt_tokens=1, completion_tokens=1, total_tokens=2, model="deepseek-v4-flash"
        )

    fake_provider = MagicMock()
    fake_provider.stream = _capturing_stream
    with (
        patch.object(
            explorer_agent.project_repo,
            "get_owned_project",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch.object(explorer_agent.usage_service, "check_quota", new=AsyncMock()),
        patch.object(
            explorer_agent,
            "get_provider_for_user",
            new=AsyncMock(return_value=fake_provider),
        ),
        patch.object(explorer_agent, "async_session_maker", _fake_session_maker()),
    ):
        _ = [
            d
            async for d in explorer_agent.interpret_guided_answer(
                user_id=uid,
                project_id=pid,
                question="故事里最主要的对抗来自哪里？",
                free_text="主角跟自己过不去",
            )
        ]
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    # system prompt 保留去 AI 味硬约束的关键词（防未来误删）。
    assert "作为 AI" in messages[0]["content"]
    assert "一句话" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    # user 消息同时携带题干与用户自述（Agent 才能「就这道题理解这句话」）。
    assert "故事里最主要的对抗来自哪里？" in messages[1]["content"]
    assert "主角跟自己过不去" in messages[1]["content"]
    # 快档 + 足量 max_tokens（陷阱⑥）。
    assert captured["kwargs"]["model"] == get_settings().deepseek_model_fast
    assert captured["kwargs"]["max_tokens"] >= 512


def _fake_session_maker() -> Callable[[], object]:
    """构造一个假 async_session_maker()：返回支持 async with 的假 session 上下文。

    interpret_guided_answer 用 `async with async_session_maker() as session:` 自管 session
    （陷阱⑩独立 session 定档②）——离线单元不碰真实 DB，故 patch 掉，产出可 async with 的哑 session。
    repo/service 调用均已 mock，session 本身不被真正使用。
    """

    class _FakeSessionCtx:
        async def __aenter__(self) -> object:
            return MagicMock()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    return lambda: _FakeSessionCtx()


# ========== 离线：SSE 端点鉴权前置（无 token / 过期 token 不需 DB）==========


def _interpret_url(project_id: object) -> str:
    return f"/api/projects/{project_id}/explore/guided/interpret"


def test_interpret_without_token_401() -> None:
    # 未登录 → 401 token_invalid（CurrentUser 依赖鉴权入口挡下）。
    resp = _client.post(
        _interpret_url(uuid.uuid4()), json={"question": "题", "freeText": "自述"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_interpret_expired_token_401() -> None:
    # 过期 access → 401 token_expired（对接原型 #/login?state=expired）。
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": now - 100, "exp": now - 10},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = _client.post(
        _interpret_url(uuid.uuid4()),
        json={"question": "题", "freeText": "自述"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_expired"


# ========== DB 端到端：SSE 端点（@requires_db，provider mock）==========


def _create_project(headers: dict[str, str], mode: str = "guided") -> str:
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    """解析 SSE 响应体为 [(event, data_dict)]（sse-starlette 输出 `event:`/`data:` 行块）。"""
    events: list[tuple[str, dict[str, object]]] = []
    event_name = None
    for line in text.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:") and event_name is not None:
            data = json.loads(line[len("data:") :].strip())
            events.append((event_name, data))
            event_name = None
    return events


def _patch_interpret_stream(
    deltas: list[str], captured: dict[str, object] | None = None
) -> object:
    """patch explorer_agent.interpret_guided_answer 为吐给定 content 块的假异步生成器。

    端点测试聚焦「HTTP 栈 + 预检 + SSE 编码」，故直接替换编排层产出（provider/记账另在单元覆盖）。
    传入 captured 时记录端点透传给编排层的 kwargs（锁 HTTP→编排 入参契约，防未来误接错字段）。
    """

    async def _fake(**kwargs: object) -> AsyncIterator[str]:
        if captured is not None:
            captured.update(kwargs)
        for d in deltas:
            yield d

    return patch.object(explorer_agent, "interpret_guided_answer", _fake)


def _patch_interpret_raises(deltas: list[str], exc: BaseException) -> object:
    """patch interpret_guided_answer 为「先吐 deltas 再抛 exc」的假异步生成器。

    模拟**流已开始后**才现实化的错误（provider 中途 5xx/断连、独立 session 重校验护栏触顶）——
    此时 HTTP 200 已提交、状态码不可改，错误只能走 SSE error 事件（Task 3 错误映射）。
    """

    async def _fake(**kwargs: object) -> AsyncIterator[str]:
        for d in deltas:
            yield d
        raise exc

    return patch.object(explorer_agent, "interpret_guided_answer", _fake)


@requires_db
def test_interpret_happy_delta_then_done(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 端到端 happy：建 project → mock 编排吐两块 → SSE delta×2 → done（done.text=完整答案）。
    user = make_user("interpret-happy@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    captured: dict[str, object] = {}
    with _patch_interpret_stream(["一个在雨夜里", "收到陌生人来信的人。"], captured):
        resp = _client.post(
            _interpret_url(project_id),
            json={"question": "脑中最先亮起的画面？", "freeText": "一个收到信的人"},
            headers=headers,
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert kinds == ["delta", "delta", "done"]
    # camelCase payload（此处 payload 键 text 本就无下划线，验事件形状与内容）。
    assert events[0][1] == {"text": "一个在雨夜里"}
    assert events[1][1] == {"text": "收到陌生人来信的人。"}
    # done.text 为完整凝练答案（供前端纳入该题答案）。
    assert events[2][1] == {"text": "一个在雨夜里收到陌生人来信的人。"}
    # HTTP→编排 入参透传契约：端点须把 project_id + 当前用户 + camelCase 解出的题干/自述
    # 原样传给编排层（锁死字段映射，防未来误接错字段静默降级）。
    assert captured["project_id"] == uuid.UUID(project_id)
    assert captured["user_id"] == user.id
    assert captured["question"] == "脑中最先亮起的画面？"
    assert captured["free_text"] == "一个收到信的人"


@requires_db
def test_interpret_unexpected_error_after_stream_emits_generic_error(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 流已开始后 provider 抛未预期异常（5xx/断连）→ 已推的 delta 保留 + 末尾泛化 error 事件；
    # 原始异常不外泄（对外恒 generate_failed + 通用文案，承 2.1「内部信息不外泄」）。
    user = make_user("interpret-midstream-err@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    with _patch_interpret_raises(["一个在雨夜里"], RuntimeError("上游 502 boom")):
        resp = _client.post(
            _interpret_url(project_id),
            json={"question": "题", "freeText": "自述"},
            headers=headers,
        )
    # 流建立前已提交 HTTP 200，中途异常只能走 error 事件（不改状态码，Task 3 错误映射）。
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["delta", "error"]
    assert events[0][1] == {"text": "一个在雨夜里"}
    # 泛化：对外只见 generate_failed + 通用文案，原始 "上游 502 boom" 不外泄。
    assert events[1][1] == {"code": "generate_failed", "message": "生成失败，请稍后重试。"}


@requires_db
def test_interpret_business_error_after_stream_passes_envelope(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 流已开始后现实化的结构化业务错误（如独立 session 重校验护栏触顶）→ error 事件透传其
    # 面向用户的 {code, message}（与 HTTP envelope 同源，前端可按 code 分支引导绑 key）。
    user = make_user("interpret-midstream-biz@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    quota_err = ErrorEnvelope(
        code="quota_exceeded",
        message="免费额度已用完，绑定自己的 API Key 即可继续创作。",
        http_status=429,
    )
    with _patch_interpret_raises(["半句"], quota_err):
        resp = _client.post(
            _interpret_url(project_id),
            json={"question": "题", "freeText": "自述"},
            headers=headers,
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["delta", "error"]
    # 业务错误透传 code + 面向用户文案（非泛化）——三要素本就面向用户、不含内部细节。
    assert events[1][1] == {
        "code": "quota_exceeded",
        "message": "免费额度已用完，绑定自己的 API Key 即可继续创作。",
    }


@requires_db
def test_interpret_empty_output_emits_error_not_done(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 空产兜底（陷阱⑥残留）：编排层零正文产出 → 不发 done.text=""（否则前端纳入空答案），
    # 改发 generate_failed error 让用户重试。
    user = make_user("interpret-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    with _patch_interpret_stream([]):
        resp = _client.post(
            _interpret_url(project_id),
            json={"question": "题", "freeText": "自述"},
            headers=headers,
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    # 无 delta、无 done，只有兜底 error（前端不会拿到空答案）。
    assert [e for e, _ in events] == ["error"]
    assert events[0][1] == {"code": "generate_failed", "message": "生成失败，请稍后重试。"}


@requires_db
def test_interpret_empty_free_text_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # freeText 纯空白 → 422（_NonBlankText strip 后空，仿原型 if(!answer) return）。
    user = make_user("interpret-422@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        _interpret_url(project_id),
        json={"question": "题干", "freeText": "   "},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_interpret_overlong_free_text_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # freeText 超长（>2000，review 裁定上界）→ 422 挡在建流前，不进 LLM（防塞万字挤爆 prompt）。
    user = make_user("interpret-overlong@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        _interpret_url(project_id),
        json={"question": "题干", "freeText": "字" * 2001},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


@requires_db
def test_interpret_quota_exceeded_429_before_stream(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 护栏触顶 → 流建立前走 HTTP 429（非 error 事件，Task 3 错误映射）。
    user = make_user("interpret-429@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    quota_err = ErrorEnvelope(
        code="quota_exceeded",
        message="免费额度已用完，绑定自己的 API Key 即可继续创作。",
        detail={"quotaExceeded": True},
        http_status=429,
    )
    # 预检阶段 check_quota 抛 429——用请求 session 的护栏拦在建流之前。
    with patch.object(
        explorer_agent.usage_service,
        "check_quota",
        new=AsyncMock(side_effect=quota_err),
    ):
        resp = _client.post(
            _interpret_url(project_id),
            json={"question": "题", "freeText": "自述"},
            headers=headers,
        )
    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "quota_exceeded"
    # 走 HTTP 错误 envelope（三要素），不是 SSE error 事件。
    assert set(body.keys()) == {"code", "message", "detail"}


@requires_db
def test_interpret_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 租户隔离（陷阱③）：B 对 A 的 project interpret → 404 project_not_found（越权=不存在）。
    alice = make_user("interpret-owner-a@example.com")
    bob = make_user("interpret-owner-b@example.com")
    project_id = _create_project(auth_headers(alice), mode="guided")

    resp = _client.post(
        _interpret_url(project_id),
        json={"question": "题", "freeText": "自述"},
        headers=auth_headers(bob),
    )
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"code", "message", "detail"}
    assert body["code"] == "project_not_found"


@requires_db
def test_interpret_nonexistent_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 随机 UUID（不存在）→ 与越权同码 404（不泄露存在性）。
    user = make_user("interpret-404@example.com")
    resp = _client.post(
        _interpret_url(uuid.uuid4()),
        json={"question": "题", "freeText": "自述"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"
