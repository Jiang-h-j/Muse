"""Story 2.6 验证：自由探索——对话 + 线索区 + Agent 整理线索（AC1-AC3/AC5/AC6 全覆盖）。

- 离线用例：新端点鉴权缺失 401（不需 DB）。
- 自由对话 SSE（@requires_db，mock stream_free_chat 编排产出，同 2.3 interpret 测试范式）：
  happy delta→done + 两条消息真实落库（user/agent 各一行，kind="free"）；GET messages 恢复
  顺序正确（严格递增 created_at，验证「分两次 commit 避免同值」确实生效）；空产兜底 error；
  租户隔离 404。
- 线索 CRUD（@requires_db）：进入自由探索播种 7 preset（display_order 0-6、user_edited=false，
  2.8 扩容自 4 preset，key 与 story_settle_agent._BACKBONE_FIELDS 一致）；PATCH 编辑后
  user_edited=true；新增/删除自定义线索；删除 preset 返 400 clue_not_deletable
  （非 404）；越权访问他人线索 404。
- Agent 整理（@requires_db，mock provider.chat）：全部未编辑时更新全部槙位；已编辑槙位跳过；
  全部已编辑时不调用 provider（省成本）；LLM 输出格式异常时全部槙位保持原值、端点仍 200。
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from muse.main import app
from muse.models.account import User
from muse.providers.base import ChatResult
from muse.services import free_explorer_agent
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    with _client:
        yield


def _create_project(headers: dict[str, str], mode: str = "free") -> str:
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


def _messages_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/free/messages"


def _clues_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/free/clues"


def _parse_sse(text_body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event_name = None
    for line in text_body.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:") and event_name is not None:
            data = json.loads(line[len("data:") :].strip())
            events.append((event_name, data))
            event_name = None
    return events


def _patch_stream_free_chat(deltas: list[str]) -> object:
    """patch free_explorer_agent.stream_free_chat 为吐给定 content 块的假异步生成器。

    端点测试聚焦「HTTP 栈 + 预检 + SSE 编码」，故直接替换编排层产出（同 2.3 interpret 测试范式）。
    """

    async def _fake(**kwargs: object) -> AsyncIterator[str]:
        for d in deltas:
            yield d

    return patch.object(free_explorer_agent, "stream_free_chat", _fake)


# ---------- 离线：鉴权前置（无 token，不需 DB） ----------


def test_send_free_message_without_token_401() -> None:
    resp = _client.post(
        _messages_url(str(uuid.uuid4())), json={"content": "你好"}
    )
    assert resp.status_code == 401


def test_list_free_messages_without_token_401() -> None:
    resp = _client.get(_messages_url(str(uuid.uuid4())))
    assert resp.status_code == 401


def test_list_clues_without_token_401() -> None:
    resp = _client.get(_clues_url(str(uuid.uuid4())))
    assert resp.status_code == 401


def test_refresh_clues_without_token_401() -> None:
    resp = _client.post(
        f"/api/projects/{uuid.uuid4()}/explore/free/clues/refresh"
    )
    assert resp.status_code == 401


# ---------- DB 端到端：自由对话 SSE（AC2/AC6） ----------


@requires_db
def test_send_free_message_happy_delta_then_done(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    user = make_user("free-chat-happy@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    with _patch_stream_free_chat(["这个想法", "很有意思。"]):
        resp = _client.post(
            _messages_url(project_id),
            json={"content": "我想写一个修仙世界的故事"},
            headers=headers,
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert kinds == ["delta", "delta", "done"]
    assert events[2][1] == {"text": "这个想法很有意思。"}

    # 本端点测试 stream_free_chat 被 mock 替换（聚焦 HTTP 栈 + SSE 编码），不验证落库。
    # 真实落库 + created_at 严格递增见 test_free_chat_persists_two_messages_...
    # （直调 free_explorer_agent.stream_free_chat 真实编排，仅 mock provider）。


@requires_db
def test_send_free_message_empty_output_emits_error_not_done(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("free-chat-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    with _patch_stream_free_chat([]):
        resp = _client.post(
            _messages_url(project_id),
            json={"content": "你好"},
            headers=headers,
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["error"]
    assert events[0][1]["code"] == "generate_failed"


@requires_db
def test_send_free_message_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("free-chat-owner-a@example.com")
    bob = make_user("free-chat-owner-b@example.com")
    project_id = _create_project(auth_headers(alice))

    resp = _client.post(
        _messages_url(project_id),
        json={"content": "你好"},
        headers=auth_headers(bob),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@requires_db
async def test_free_chat_persists_two_messages_with_strictly_increasing_created_at(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # 直调真实编排（只 mock provider.stream），验证「分两次 commit」确实避免同 created_at，
    # 且两条消息（user/agent）均落 kind="free"。
    user = make_user("free-chat-persist@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    async def _fake_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
        from muse.providers.base import StreamChunk

        yield StreamChunk(delta="这个想法", kind="content")
        yield StreamChunk(delta="很有意思。", kind="content")

    fake_provider = AsyncMock()
    fake_provider.stream = _fake_stream

    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        deltas = [
            d
            async for d in free_explorer_agent.stream_free_chat(
                user_id=user.id,
                project_id=uuid.UUID(project_id),
                user_message="我想写一个修仙世界的故事",
            )
        ]
    assert "".join(deltas) == "这个想法很有意思。"

    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT role, content, created_at FROM exploration_message "
                "WHERE project_id = :pid AND kind = 'free' ORDER BY created_at ASC"
            ),
            {"pid": project_id},
        ).all()
    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[0].content == "我想写一个修仙世界的故事"
    assert rows[1].role == "agent"
    assert rows[1].content == "这个想法很有意思。"
    # 关键断言：两行 created_at 严格递增（分两次独立 commit 生效），非相等。
    assert rows[1].created_at > rows[0].created_at


@requires_db
async def test_free_chat_empty_output_persists_nothing(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # P1 回归：Agent 空产时用户消息与 Agent 回复都不落库（避免孤儿用户消息）。直调真实编排、
    # provider.stream 产出零 content 块。
    user = make_user("free-chat-empty-persist@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    async def _empty_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
        return
        yield  # pragma: no cover — 使其成为 async generator

    fake_provider = AsyncMock()
    fake_provider.stream = _empty_stream

    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        deltas = [
            d
            async for d in free_explorer_agent.stream_free_chat(
                user_id=user.id,
                project_id=uuid.UUID(project_id),
                user_message="你好",
            )
        ]
    assert deltas == []

    with db_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM exploration_message "
                "WHERE project_id = :pid AND kind = 'free'"
            ),
            {"pid": project_id},
        ).scalar_one()
    # 关键断言：空产 → 零落库（含用户消息），不留孤儿。
    assert count == 0


@requires_db
async def test_free_chat_error_midstream_persists_nothing(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # P1 回归：provider.stream 中途抛异常时，用户消息也不落库（异常前尚未 commit）。
    user = make_user("free-chat-error-persist@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    async def _boom_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
        from muse.providers.base import StreamChunk

        yield StreamChunk(delta="开头", kind="content")
        raise RuntimeError("provider 中途炸了")

    fake_provider = AsyncMock()
    fake_provider.stream = _boom_stream

    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        with pytest.raises(RuntimeError):
            _ = [
                d
                async for d in free_explorer_agent.stream_free_chat(
                    user_id=user.id,
                    project_id=uuid.UUID(project_id),
                    user_message="你好",
                )
            ]

    with db_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM exploration_message "
                "WHERE project_id = :pid AND kind = 'free'"
            ),
            {"pid": project_id},
        ).scalar_one()
    # 关键断言：中途异常 → 零落库（用户消息在异常前尚未 commit），不留孤儿。
    assert count == 0


@requires_db
def test_list_free_messages_empty_returns_empty_list(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("free-messages-empty@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    resp = _client.get(_messages_url(project_id), headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ---------- DB 端到端：线索 CRUD（AC3/AC6） ----------


@requires_db
def test_enter_free_exploration_seeds_seven_preset_clues(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-seed@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    # 进入探索触发播种。
    resp = _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    assert resp.status_code == 200

    resp = _client.get(_clues_url(project_id), headers=headers)
    assert resp.status_code == 200
    clues = resp.json()
    assert len(clues) == 7
    assert [c["displayOrder"] for c in clues] == [0, 1, 2, 3, 4, 5, 6]
    assert [c["clueKey"] for c in clues] == [
        "genre",
        "core_appeal",
        "protagonist",
        "main_conflict",
        "world_rules",
        "overall_tone",
        "opening_hook",
    ]
    assert [c["label"] for c in clues] == [
        "题材",
        "核心吸引力",
        "主角",
        "主要冲突",
        "关键世界规则",
        "整体气质",
        "开篇钩子",
    ]
    for c in clues:
        assert c["kind"] == "preset"
        assert c["userEdited"] is False
        assert c["value"] == ""


@requires_db
def test_enter_free_exploration_idempotent_does_not_reseed(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-reseed@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    resp = _client.get(_clues_url(project_id), headers=headers)
    assert len(resp.json()) == 7


@requires_db
def test_enter_free_exploration_heals_stale_null_guidance_state(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
    db_engine: Engine,
) -> None:
    # code review 修复回归：模拟本 story 上线前已创建的存量 free 会话（guidance_state 被
    # 迁移回填为 NULL）。再次进入探索（enter_exploration 命中「已存在」分支）应就地初始化
    # guidance_state，而不是让它永久停留在 None（否则 settle 门禁永久无法满足）。
    user = make_user("guidance-heal-stale@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE exploration_session SET guidance_state = NULL "
                "WHERE project_id = :pid"
            ),
            {"pid": project_id},
        )
    with db_engine.begin() as conn:
        row = conn.execute(
            text("SELECT guidance_state FROM exploration_session WHERE project_id = :pid"),
            {"pid": project_id},
        ).one()
    assert row.guidance_state is None  # 模拟成功：确认已回退成存量态

    resp = _client.post(f"/api/projects/{project_id}/explore", headers=headers)
    assert resp.status_code == 200

    resp2 = _client.get(
        f"/api/projects/{project_id}/explore/free/guidance", headers=headers
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["readyToSettle"] is False
    assert all(v == "missing" for v in body["fields"].values())

    with db_engine.begin() as conn:
        row_after = conn.execute(
            text("SELECT guidance_state FROM exploration_session WHERE project_id = :pid"),
            {"pid": project_id},
        ).one()
    assert row_after.guidance_state is not None  # 已就地初始化并落库，不再是 NULL


@requires_db
def test_edit_clue_sets_user_edited_true(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-edit@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    opening_clue = next(c for c in clues if c["clueKey"] == "genre")

    resp = _client.patch(
        f"{_clues_url(project_id)}/{opening_clue['id']}",
        json={"value": "一个雨夜收到陌生来信的人"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"] == "一个雨夜收到陌生来信的人"
    assert body["userEdited"] is True


@requires_db
def test_create_and_delete_custom_clue(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-custom@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    resp = _client.post(
        _clues_url(project_id),
        json={"label": "神秘组织", "value": "暗中操控一切"},
        headers=headers,
    )
    assert resp.status_code == 201
    custom_clue = resp.json()
    assert custom_clue["kind"] == "custom"
    assert custom_clue["clueKey"] is None
    assert custom_clue["displayOrder"] == 7  # 7 个 preset 之后追加

    del_resp = _client.delete(
        f"{_clues_url(project_id)}/{custom_clue['id']}", headers=headers
    )
    assert del_resp.status_code == 204

    remaining = _client.get(_clues_url(project_id), headers=headers).json()
    assert len(remaining) == 7  # 只剩 7 个 preset


@requires_db
def test_delete_preset_clue_returns_400_not_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-delete-preset@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    preset_clue = clues[0]

    resp = _client.delete(
        f"{_clues_url(project_id)}/{preset_clue['id']}", headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "clue_not_deletable"


@requires_db
def test_edit_others_clue_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("clue-owner-a@example.com")
    bob = make_user("clue-owner-b@example.com")
    alice_headers = auth_headers(alice)
    project_id = _create_project(alice_headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=alice_headers)
    clues = _client.get(_clues_url(project_id), headers=alice_headers).json()

    resp = _client.patch(
        f"{_clues_url(project_id)}/{clues[0]['id']}",
        json={"value": "越权改写"},
        headers=auth_headers(bob),
    )
    assert resp.status_code == 404


# ---------- DB 端到端：Agent 整理线索（AC5，核心） ----------


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


@requires_db
def test_refresh_clues_updates_all_unedited_presets(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-refresh-all@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(
        return_value=_fake_chat_result(
            "题材：悬疑\n"
            "核心吸引力：谎言与真相的拉扯\n"
            "主角：一个孤独的侦探\n"
            "主要冲突：真相与谎言的对抗\n"
            "关键世界规则：阴郁的近未来都市\n"
            "整体气质：压抑克制\n"
            "开篇钩子：一个雨夜的来信"
        )
    )
    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        resp = _client.post(
            f"/api/projects/{project_id}/explore/free/clues/refresh", headers=headers
        )
    assert resp.status_code == 200
    clues = {c["clueKey"]: c for c in resp.json()}
    assert clues["genre"]["value"] == "悬疑"
    assert clues["core_appeal"]["value"] == "谎言与真相的拉扯"
    assert clues["protagonist"]["value"] == "一个孤独的侦探"
    assert clues["main_conflict"]["value"] == "真相与谎言的对抗"
    assert clues["world_rules"]["value"] == "阴郁的近未来都市"
    assert clues["overall_tone"]["value"] == "压抑克制"
    assert clues["opening_hook"]["value"] == "一个雨夜的来信"
    # Agent 整理不改 user_edited（仍 false，可被后续整理继续覆盖）。
    for c in clues.values():
        assert c["userEdited"] is False


@requires_db
def test_refresh_clues_skips_user_edited_preset(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-refresh-skip@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    opening_clue = next(c for c in clues if c["clueKey"] == "genre")
    _client.patch(
        f"{_clues_url(project_id)}/{opening_clue['id']}",
        json={"value": "用户手动写的开头"},
        headers=headers,
    )

    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(
        return_value=_fake_chat_result(
            "核心吸引力：谎言与真相的拉扯\n"
            "主角：一个孤独的侦探\n"
            "主要冲突：真相与谎言的对抗\n"
            "关键世界规则：阴郁的近未来都市\n"
            "整体气质：压抑克制\n"
            "开篇钩子：一个雨夜的来信"
        )
    )
    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        resp = _client.post(
            f"/api/projects/{project_id}/explore/free/clues/refresh", headers=headers
        )
    assert resp.status_code == 200
    result_clues = {c["clueKey"]: c for c in resp.json()}
    # genre 已被用户编辑，值不变、user_edited 仍 true。
    assert result_clues["genre"]["value"] == "用户手动写的开头"
    assert result_clues["genre"]["userEdited"] is True
    # 其余槙位正常被整理更新。
    assert result_clues["protagonist"]["value"] == "一个孤独的侦探"


@requires_db
def test_refresh_clues_all_edited_skips_provider_call(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-refresh-noop@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    for c in clues:
        _client.patch(
            f"{_clues_url(project_id)}/{c['id']}",
            json={"value": f"手动填的{c['label']}"},
            headers=headers,
        )

    get_provider = AsyncMock()
    with patch.object(free_explorer_agent, "get_provider_for_user", get_provider):
        resp = _client.post(
            f"/api/projects/{project_id}/explore/free/clues/refresh", headers=headers
        )
    assert resp.status_code == 200
    # 全部槙位已编辑 → 不调用 provider（省成本，验证「空转不调用」分支真生效）。
    get_provider.assert_not_awaited()


@requires_db
def test_refresh_clues_malformed_llm_output_keeps_original_values(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("clue-refresh-malformed@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(
        return_value=_fake_chat_result("这是一段完全不符合格式的自由文本，没有任何冒号分隔。")
    )
    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        resp = _client.post(
            f"/api/projects/{project_id}/explore/free/clues/refresh", headers=headers
        )
    # 零行匹配 → 防御性解析不崩溃，端点仍 200，全部槙位保持原值（空串）不变。
    assert resp.status_code == 200
    for c in resp.json():
        assert c["value"] == ""
        assert c["userEdited"] is False


@requires_db
async def test_extract_clues_race_does_not_overwrite_user_edit(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # P3 回归：extract_clues 读 pending 快照后、写回前，用户手动 PATCH 了某槙位（置
    # user_edited=true）——条件 UPDATE (WHERE user_edited=false) 应命中 0 行、跳过覆盖，
    # 用户编辑的值保留。用 provider.chat 里注入"抢编辑"模拟读-算-写之间的时序。
    user = make_user("clue-race@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    opening_clue = next(c for c in clues if c["clueKey"] == "genre")

    async def _chat_then_user_edits(*args: object, **kwargs: object) -> ChatResult:
        # 模拟 LLM 调用耗时窗口内用户抢先手动编辑 genre 槙位（置 user_edited=true）。
        _client.patch(
            f"{_clues_url(project_id)}/{opening_clue['id']}",
            json={"value": "用户在整理期间抢先写的开头"},
            headers=headers,
        )
        return _fake_chat_result(
            "题材：Agent 想覆盖的题材\n"
            "主角：一个孤独的侦探\n"
            "主要冲突：真相与谎言\n"
            "关键世界规则：阴郁都市"
        )

    fake_provider = AsyncMock()
    fake_provider.chat = _chat_then_user_edits
    with patch.object(
        free_explorer_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=fake_provider),
    ):
        await free_explorer_agent.extract_clues(
            user_id=user.id, project_id=uuid.UUID(project_id)
        )

    result = {
        c["clueKey"]: c
        for c in _client.get(_clues_url(project_id), headers=headers).json()
    }
    # 关键断言：genre 保留用户抢写的值、user_edited 仍 true（未被 Agent 覆盖）。
    assert result["genre"]["value"] == "用户在整理期间抢先写的开头"
    assert result["genre"]["userEdited"] is True
    # 其余未被用户碰的槙位仍正常被整理更新。
    assert result["protagonist"]["value"] == "一个孤独的侦探"


@requires_db
def test_edit_preset_clue_label_returns_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # P7 回归：preset 线索的 label 不可改（会导致 UI 与整理端点匹配键语义分裂），返 400。
    user = make_user("clue-preset-label@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    clues = _client.get(_clues_url(project_id), headers=headers).json()
    preset_clue = next(c for c in clues if c["clueKey"] == "genre")

    resp = _client.patch(
        f"{_clues_url(project_id)}/{preset_clue['id']}",
        json={"value": "改内容可以", "label": "改名不行"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "preset_label_immutable"

    # 只改 value 不带 label 仍应成功（不误伤正常编辑路径）。
    resp2 = _client.patch(
        f"{_clues_url(project_id)}/{preset_clue['id']}",
        json={"value": "只改内容"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["value"] == "只改内容"


@requires_db
def test_edit_custom_clue_label_succeeds(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # P7 边界：custom 线索的 label 可自由改（无匹配键约束），不被 preset 限制误伤。
    user = make_user("clue-custom-label@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    _client.post(f"/api/projects/{project_id}/explore", headers=headers)

    created = _client.post(
        _clues_url(project_id),
        json={"label": "旧名", "value": "内容"},
        headers=headers,
    ).json()

    resp = _client.patch(
        f"{_clues_url(project_id)}/{created['id']}",
        json={"value": "内容", "label": "新名"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "新名"
