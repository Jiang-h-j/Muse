"""Story 2.8 验证（2026-08-03 合并重构后）：自由探索——设定导航端点集成
（HTTP 栈 + 租户/mode 守卫 + camelCase 边界）。

3 个端点：`GET .../free/guidance`（恢复）、`POST .../free/guidance/start`（零对话四入口）、
`POST .../free/guidance/skip`（跳过）。**`/guidance/suggestions` 端点已移除**——候选回复
现在随聊天回复/开场问题/跳过下一问同一次 LLM 调用生成，写入 `currentSuggestions`，前端
本地展开/收起即可，不再需要单独请求。

- 离线（不需容器）：3 端点鉴权缺失 401。
- `GET .../free/guidance`：零对话时返回全 `missing` 初始态 + camelCase 字段名（`fields`/
  `currentField`/`currentSuggestions`/`readyToSettle`，**无 `currentQuestion`**）；guided
  项目该端点仍受 mode 守卫。
- `start`：mock provider，四入口各自映射到正确的主干字段并生成开场问题 + 候选回复，
  开场问题落库为真实 agent 聊天消息；已有对话时幂等返回当前态、不调 provider。
- `skip`：无 `current_field` → 400 `no_current_question`；有则按 mock 产出正常工作，
  谨慎归纳与用户编辑保护同 2.6 既有约束。
- 门禁替换回归（AC8 核心，与 `test_exploration_free_settle.py` 呼应）：mock 让 7 项全
  `filled`/`skipped` 后，`POST .../free/settle` 才放行。
- mode 守卫 409 / 租户隔离 404 / 非法 UUID 422：新端点对称覆盖。

`guidance_agent.py`/`free_explorer_agent.py` 的解析/合并/护栏取舍纯逻辑单元见
`test_guidance_agent.py`，本文件不重复覆盖，只验证端点契约（HTTP 状态码、camelCase
序列化、鉴权/守卫链路）。
"""

import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from muse.core.db import async_session_maker
from muse.main import app
from muse.models.account import User
from muse.providers.base import ChatResult
from muse.repositories import exploration_repo
from muse.services import exploration_service, guidance_agent, story_settle_agent
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


def _guidance_url(project_id: str) -> str:
    return f"/api/projects/{project_id}/explore/free/guidance"


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


def _mock_provider(content: str) -> AsyncMock:
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(content))
    return provider


async def _set_current_field_only_missing(
    user: User, project_id: str, *, field: str
) -> None:
    """把导航状态改成「只剩 `field` 一项 missing、其余 6 项 filled、current_field=field」。

    `skip` 端点契约测试只关心「跳过这一动作本身」，不是判定逻辑（那归
    `test_guidance_agent.py`）——只留 1 项待跳过可以让跳过后直接进入 `ready_to_settle`
    收束态，避免触发「立即推进下一问」分支（会额外消费一次 mock provider 调用），
    使断言聚焦在归纳落库这一件事上。
    """
    async with async_session_maker() as session:
        exploration_session = await exploration_service.enter_exploration(
            session, user.id, uuid.UUID(project_id)
        )
        fields = {
            key: ("missing" if key == field else "filled")
            for key, _ in story_settle_agent._BACKBONE_FIELDS
        }
        state = {
            "fields": fields,
            "current_field": field,
            "current_suggestions": [],
            "ready_to_settle": False,
        }
        await exploration_repo.update_guidance_state(
            session,
            user_id=user.id,
            project_id=uuid.UUID(project_id),
            session_id=exploration_session.id,
            guidance_state=state,
        )
        await session.commit()


# ========== 离线：3 端点鉴权前置（无 token，不需容器） ==========


def test_get_guidance_without_token_401() -> None:
    resp = _client.get(_guidance_url(str(uuid.uuid4())))
    assert resp.status_code == 401


def test_start_guidance_without_token_401() -> None:
    resp = _client.post(
        f"{_guidance_url(str(uuid.uuid4()))}/start", json={"entry": "story_idea"}
    )
    assert resp.status_code == 401


def test_skip_field_without_token_401() -> None:
    resp = _client.post(f"{_guidance_url(str(uuid.uuid4()))}/skip")
    assert resp.status_code == 401


# ========== GET /free/guidance：恢复（AC1/AC10） ==========


@requires_db
def test_get_guidance_zero_dialog_returns_initial_missing_state(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-get-initial@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200

    resp = _client.get(_guidance_url(project_id), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["readyToSettle"] is False
    assert body["currentField"] is None
    assert body["currentSuggestions"] == []
    assert "currentQuestion" not in body
    # camelCase 边界：fields dict 内部 key 也须转换（core_appeal → coreAppeal）。
    assert body["fields"]["coreAppeal"] == "missing"
    assert body["fields"]["mainConflict"] == "missing"
    assert set(body["fields"].keys()) == {
        "genre",
        "coreAppeal",
        "protagonist",
        "mainConflict",
        "worldRules",
        "overallTone",
        "openingHook",
    }


@requires_db
def test_get_guidance_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-get-guided@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.get(_guidance_url(project_id), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_get_guidance_others_project_returns_404(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    alice = make_user("guidance-owner-a@example.com")
    bob = make_user("guidance-owner-b@example.com")
    project_id = _create_project(auth_headers(alice))

    resp = _client.get(_guidance_url(project_id), headers=auth_headers(bob))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


def test_get_guidance_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-get-baduuid@example.com")
    resp = _client.get(
        "/api/projects/not-a-uuid/explore/free/guidance", headers=auth_headers(user)
    )
    assert resp.status_code == 422


# ========== POST /free/guidance/start：零对话四入口（AC3） ==========


@requires_db
def test_start_guidance_maps_entry_to_field_and_generates_question(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-start-happy@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200

    with patch.object(
        guidance_agent,
        "get_provider_for_user",
        new=AsyncMock(
            return_value=_mock_provider(
                "这故事最抓人的地方是什么？\n###SUGGESTIONS###\n候选：主角想复仇\n候选：主角想救赎"
            )
        ),
    ):
        resp = _client.post(
            f"{_guidance_url(project_id)}/start",
            json={"entry": "story_idea"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["currentField"] == "coreAppeal"  # story_idea → core_appeal 映射
    assert body["currentSuggestions"] == ["主角想复仇", "主角想救赎"]

    # 开场问题落库为真实 agent 聊天消息（2026-08-03 合并重构新增）。
    messages = _client.get(
        f"/api/projects/{project_id}/explore/free/messages", headers=headers
    ).json()
    assert len(messages) == 1
    assert messages[0]["role"] == "agent"
    assert messages[0]["content"] == "这故事最抓人的地方是什么？"


@requires_db
def test_start_guidance_invalid_entry_returns_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-start-badentry@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)

    resp = _client.post(
        f"{_guidance_url(project_id)}/start",
        json={"entry": "not_a_real_entry"},
        headers=headers,
    )
    assert resp.status_code == 422


@requires_db
def test_start_guidance_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-start-guided@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        f"{_guidance_url(project_id)}/start",
        json={"entry": "world"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


# ========== POST /free/guidance/skip：跳过 + 谨慎归纳（AC6） ==========


@requires_db
def test_skip_field_no_current_field_returns_400(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-skip-nofield@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200

    resp = _client.post(f"{_guidance_url(project_id)}/skip", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "no_current_question"


@requires_db
async def test_skip_field_marks_skipped_and_summarizes_into_clue(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-skip-happy@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200
    await _set_current_field_only_missing(user, project_id, field="genre")

    with patch.object(
        guidance_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=_mock_provider("结论：都市悬疑")),
    ):
        resp = _client.post(f"{_guidance_url(project_id)}/skip", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["fields"]["genre"] == "skipped"
    assert body["readyToSettle"] is True  # genre 是唯一 missing 项，跳过后收束

    # 谨慎归纳落库：对应 preset 槙位（clueKey=genre）被写入。
    clues = _client.get(
        f"/api/projects/{project_id}/explore/free/clues", headers=headers
    ).json()
    genre_clue = next(c for c in clues if c["clueKey"] == "genre")
    assert genre_clue["value"] == "都市悬疑"
    assert genre_clue["userEdited"] is False  # 归纳不算用户编辑


@requires_db
async def test_skip_field_does_not_overwrite_user_edited_clue(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # AC6/AC10 硬约束：已被用户手动编辑（user_edited=true）的槙位不被跳过归纳覆盖。
    user = make_user("guidance-skip-useredited@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200
    await _set_current_field_only_missing(user, project_id, field="genre")

    clues = _client.get(
        f"/api/projects/{project_id}/explore/free/clues", headers=headers
    ).json()
    genre_clue = next(c for c in clues if c["clueKey"] == "genre")
    _client.patch(
        f"/api/projects/{project_id}/explore/free/clues/{genre_clue['id']}",
        json={"value": "用户手动写的题材"},
        headers=headers,
    )

    with patch.object(
        guidance_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=_mock_provider("结论：Agent 想覆盖的题材")),
    ):
        resp = _client.post(f"{_guidance_url(project_id)}/skip", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fields"]["genre"] == "skipped"  # 状态转移仍生效

    clues_after = _client.get(
        f"/api/projects/{project_id}/explore/free/clues", headers=headers
    ).json()
    genre_clue_after = next(c for c in clues_after if c["clueKey"] == "genre")
    assert genre_clue_after["value"] == "用户手动写的题材"  # 未被覆盖
    assert genre_clue_after["userEdited"] is True


@requires_db
async def test_skip_field_blank_conclusion_leaves_clue_untouched(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-skip-noinfo@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers)
    assert _client.post(f"/api/projects/{project_id}/explore", headers=headers).status_code == 200
    await _set_current_field_only_missing(user, project_id, field="genre")

    with patch.object(
        guidance_agent,
        "get_provider_for_user",
        new=AsyncMock(return_value=_mock_provider("结论：")),
    ):
        resp = _client.post(f"{_guidance_url(project_id)}/skip", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["fields"]["genre"] == "skipped"

    clues = _client.get(
        f"/api/projects/{project_id}/explore/free/clues", headers=headers
    ).json()
    genre_clue = next(c for c in clues if c["clueKey"] == "genre")
    assert genre_clue["value"] == ""  # 无材料可归纳，槙位保持空值不报错


@requires_db
def test_skip_field_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("guidance-skip-guided@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(f"{_guidance_url(project_id)}/skip", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"
