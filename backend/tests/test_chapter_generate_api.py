"""Story 4.4 Task 4/5 验证：章节生成触发端点 + GET 正文恢复端点（AC1/AC5/AC6/AC7）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- HTTP 触发 + 属主登记（@requires_db @requires_redis，仿 test_chapter_stage_plan_api.py）：
  - 触发返 taskId（camelCase、非空 hex）+ Redis 登记属主（陷阱⑤）
  - 本章想法 chapterIdea 透传（body）
  - 未确认设定 → 400 bible_not_confirmed（不给未确认作品排任务，防御）
  - 租户隔离 404（他人 project）/ 不存在 404 / 非法 UUID 422
- GET 恢复端点：无正文 → 204；有 → 200 + camelCase 正文
- 路由不冲突：GET .../chapters/stage-plan 与 GET .../chapters/{n} 各自命中

造 confirmed bible / chapter 用同步 Session 直接造种子。
"""

import uuid
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core import sse
from muse.core.settings import get_settings
from muse.main import app
from muse.models.account import User
from muse.models.chapter import Chapter
from muse.models.story_bible import StoryBible
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


def _client_lifespan_ctx() -> TestClient:
    return _client


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


def _seed_chapter(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_number: int, text: str
) -> None:
    with Session(engine) as session:
        session.add(
            Chapter(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                chapter_number=chapter_number,
                text=text,
            )
        )
        session.commit()


def _seed_stage_plan(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_count: int = 3
) -> None:
    """造一份首阶段规划（chapter_count 章），供生成端点的章号范围校验通过。"""
    from muse.models.stage_plan import StagePlan

    with Session(engine) as session:
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                goal="站稳外门。",
                chapters=[
                    {"title": f"第 {i} 章", "brief": "略"}
                    for i in range(1, chapter_count + 1)
                ],
            )
        )
        session.commit()


def _gen_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}/generate"


def _chapter_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}"


def _cleanup_enqueued_job(task_id: str) -> None:
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== 离线：鉴权前置 ==========


def test_generate_without_token_401() -> None:
    resp = _client.post(_gen_url(str(uuid.uuid4()), 1), json={})
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


def test_get_chapter_without_token_401() -> None:
    resp = _client.get(_chapter_url(str(uuid.uuid4()), 1))
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== HTTP 触发 + 属主登记 ==========


@requires_db
@requires_redis
def test_generate_returns_task_id_and_registers_owner(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        user = make_user("gen-submit@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)

        resp = _client.post(
            _gen_url(project_id, 1), json={"chapterIdea": "多写点雨"}, headers=headers
        )
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
def test_generate_empty_idea_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """本章想法可留空（跳过并生成）——body 不带 chapterIdea 也返 taskId。"""
    with _client:
        user = make_user("gen-empty-idea@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)

        resp = _client.post(_gen_url(project_id, 1), json={}, headers=headers)
        assert resp.status_code == 200
        task_id = resp.json()["taskId"]
        assert task_id
    _cleanup_enqueued_job(task_id)
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(sse.task_owner_key(task_id))
    finally:
        client.close()


@requires_db
@requires_redis
def test_generate_not_confirmed_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无 confirmed 设定 → 400 bible_not_confirmed（不给未确认作品排任务，从不登记属主）。"""
    with _client:
        user = make_user("gen-noconfirm@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)  # 未造 confirmed bible

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(_gen_url(project_id, 1), json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "bible_not_confirmed"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_generate_out_of_range_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """章号超出阶段规划范围 / 无阶段规划 → 400 chapter_out_of_range，从不登记属主。"""
    with _client:
        user = make_user("gen-out-of-range@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id, chapter_count=3)

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            # 第 4 章不在 3 章的规划范围内。
            resp = _client.post(_gen_url(project_id, 4), json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_out_of_range"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_generate_no_stage_plan_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无阶段规划（尚未生成）→ 400 chapter_out_of_range（不给无规划作品排生成）。"""
    with _client:
        user = make_user("gen-no-plan@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)  # 无 stage_plan

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(_gen_url(project_id, 1), json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_out_of_range"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_generate_others_project_returns_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        alice = make_user("gen-owner-a@example.com")
        bob = make_user("gen-owner-b@example.com")
        project_id = _create_project(alice, auth_headers(alice))
        _seed_confirmed_bible(db_engine, alice.id, project_id)

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(
                _gen_url(project_id, 1), json={}, headers=auth_headers(bob)
            )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_generate_invalid_uuid_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        user = make_user("gen-bad-uuid@example.com")
        resp = _client.post(
            "/api/projects/not-a-uuid/chapters/1/generate",
            json={},
            headers=auth_headers(user),
        )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


# ========== GET 正文恢复端点 ==========


@requires_db
@requires_redis
def test_get_chapter_absent_returns_204(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        user = make_user("chapter-get-empty@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        resp = _client.get(_chapter_url(project_id, 1), headers=headers)
        assert resp.status_code == 204


@requires_db
@requires_redis
def test_get_chapter_present_returns_200(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """有正文 → 200 + camelCase（chapterNumber/chapterText/revision/status）。"""
    with _client:
        user = make_user("chapter-get-present@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_chapter(db_engine, user.id, project_id, 1, "雨落下来了。")

        resp = _client.get(_chapter_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["chapterNumber"] == 1
        assert body["chapterText"] == "雨落下来了。"
        assert body["revision"] == 1
        assert body["status"] == "draft"


@requires_db
@requires_redis
def test_get_chapter_others_project_returns_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        alice = make_user("chapter-get-a@example.com")
        bob = make_user("chapter-get-b@example.com")
        project_id = _create_project(alice, auth_headers(alice))
        _seed_chapter(db_engine, alice.id, project_id, 1, "正文。")

        resp = _client.get(_chapter_url(project_id, 1), headers=auth_headers(bob))
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


# ========== 路由不冲突：stage-plan 静态段 vs {chapter_number} ==========


@requires_db
@requires_redis
def test_stage_plan_route_not_shadowed_by_chapter_number(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """GET .../chapters/stage-plan 命中阶段规划端点（返 204 未生成），不被 {chapter_number} 吞。

    若被动态路由吞，chapter_number="stage-plan" 会 422（int 转换失败）；这里应为 204。
    """
    with _client:
        user = make_user("route-no-shadow@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        resp = _client.get(
            f"/api/projects/{project_id}/chapters/stage-plan", headers=headers
        )
        assert resp.status_code == 204
