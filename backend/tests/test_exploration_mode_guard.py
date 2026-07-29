"""Story 2.6 验证：guided/free mode 边界守卫（AC7）。

2.4 code review 显式 defer 至本 story 的裁定（deferred-work.md「缺 guided-mode 守卫」）：
free-mode project 此前可静默写入 guided 答案。本 story 在 service 层加 `_require_project_mode`
后，guided 专属端点遇 free-mode project、free 专属端点遇 guided-mode project 均应返 409
mode_mismatch——本文件专注验证这一边界，不重复既有 2.3/2.4/2.5 测试文件已覆盖的正向路径。
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from muse.main import app
from muse.models.account import User
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True, scope="module")
def _client_lifespan() -> "object":
    with _client:
        yield


def _create_project(headers: dict[str, str], mode: str) -> str:
    resp = _client.post("/api/projects", json={"mode": mode}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------- free-mode project 调 guided 专属端点 → 409 ----------


@requires_db
def test_guided_answers_post_on_free_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-1@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="free")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/guided/answers",
        json={"questionIndex": 0, "question": "q", "answer": "a", "answerType": "option"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_guided_answers_get_on_free_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-2@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="free")

    resp = _client.get(
        f"/api/projects/{project_id}/explore/guided/answers", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_guided_settle_on_free_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-3@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="free")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/guided/settle", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_guided_interpret_on_free_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # interpret 预检阶段（用请求 session）就应拦下，不建流、不进 SSE。
    user = make_user("mode-guard-4@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="free")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/guided/interpret",
        json={"question": "题", "freeText": "自述"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


# ---------- guided-mode project 调 free 专属端点 → 409 ----------


@requires_db
def test_free_messages_post_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-5@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/free/messages",
        json={"content": "你好"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_messages_get_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-6@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.get(
        f"/api/projects/{project_id}/explore/free/messages", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_clues_get_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-7@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.get(
        f"/api/projects/{project_id}/explore/free/clues", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_clues_post_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-8@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/free/clues",
        json={"label": "新线索"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_clues_refresh_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-9@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.post(
        f"/api/projects/{project_id}/explore/free/clues/refresh", headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_clues_patch_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # 用一个不存在的 clue_id 亦可——mode 守卫在 get_clue_by_id 之前触发，409 优先于 404。
    user = make_user("mode-guard-10@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.patch(
        f"/api/projects/{project_id}/explore/free/clues/{uuid.uuid4()}",
        json={"value": "新值"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"


@requires_db
def test_free_clues_delete_on_guided_project_returns_409(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = make_user("mode-guard-11@example.com")
    headers = auth_headers(user)
    project_id = _create_project(headers, mode="guided")

    resp = _client.delete(
        f"/api/projects/{project_id}/explore/free/clues/{uuid.uuid4()}",
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "mode_mismatch"
