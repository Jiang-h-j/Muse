"""Story 4.6 验证：改进本章 / 重新生成整章触发端点（AC1/AC2/AC3/AC4）。

- 离线（不需容器）：触发端点鉴权缺失 401（CurrentUser 前置）。
- HTTP 触发 + 属主登记（@requires_db @requires_redis，仿 test_chapter_generate_api.py）：
  - 改进返 taskId + Redis 登记属主 + reset_run 生效（旧 succeeded run 被清）
  - 改进无反馈（无点评无批注）→ 400 improve_feedback_required，不登记属主
  - 重生允许空反馈 → 返 taskId
  - 本章未生成（无 chapter 行）→ 400 chapter_not_generated
  - 租户隔离 404（他人 project）/ 非法 action 422

造 confirmed bible / chapter / stage_plan / run 用同步 Session 直接造种子。
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
from muse.models.chapter_generation import ChapterGenerationRun
from muse.models.stage_plan import StagePlan
from muse.models.story_bible import StoryBible
from tests.conftest import requires_db, requires_redis

_client = TestClient(app, raise_server_exceptions=False)


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
    engine: Engine,
    user_id: uuid.UUID,
    project_id: str,
    chapter_number: int,
    text: str,
    revision: int = 1,
) -> None:
    with Session(engine) as session:
        session.add(
            Chapter(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                chapter_number=chapter_number,
                text=text,
                revision=revision,
            )
        )
        session.commit()


def _seed_stage_plan(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_count: int = 3
) -> None:
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


def _seed_succeeded_run(
    engine: Engine,
    user_id: uuid.UUID,
    project_id: str,
    chapter_number: int,
    chapter_idea: str | None = None,
) -> None:
    """造一条已 succeeded 的运行记录（含四段产物），验证 reset_run 会作废它。"""
    with Session(engine) as session:
        session.add(
            ChapterGenerationRun(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                chapter_number=chapter_number,
                status="succeeded",
                steps={"polisher": {"status": "succeeded", "output": "旧终稿"}},
                chapter_idea=chapter_idea,
            )
        )
        session.commit()


def _read_run(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_number: int
) -> ChapterGenerationRun | None:
    from sqlalchemy import select

    with Session(engine) as session:
        return session.execute(
            select(ChapterGenerationRun).where(
                ChapterGenerationRun.user_id == user_id,
                ChapterGenerationRun.project_id == uuid.UUID(project_id),
                ChapterGenerationRun.chapter_number == chapter_number,
            )
        ).scalar_one_or_none()


def _revise_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}/revise"


def _cleanup(task_id: str) -> None:
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(sse.task_owner_key(task_id))
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== 离线：鉴权前置 ==========


def test_revise_without_token_401() -> None:
    resp = _client.post(
        _revise_url(str(uuid.uuid4()), 1), json={"action": "improve", "feedback": "x"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== HTTP 触发 ==========


@requires_db
@requires_redis
def test_improve_returns_task_and_resets_run(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """改进返 taskId + 登记属主；旧 succeeded run 被 reset（steps 清空、status→running）。"""
    with _client:
        user = make_user("rev-improve@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "旧正文", revision=1)
        _seed_succeeded_run(db_engine, user.id, project_id, 1)

        resp = _client.post(
            _revise_url(project_id, 1),
            json={"action": "improve", "feedback": "开头太慢"},
            headers=headers,
        )
        assert resp.status_code == 200
        task_id = resp.json()["taskId"]
        assert task_id

    # reset_run 生效：旧 succeeded run 被清（steps=None、status=running）。
    run = _read_run(db_engine, user.id, project_id, 1)
    assert run is not None
    assert run.status == "running"
    assert run.steps is None
    _cleanup(task_id)


@requires_db
@requires_redis
def test_improve_without_feedback_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """改进无点评且无批注 → 400 improve_feedback_required，不登记属主。"""
    with _client:
        user = make_user("rev-improve-nofb@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "旧正文")

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy:
            resp = _client.post(
                _revise_url(project_id, 1),
                json={"action": "improve", "annotations": []},
                headers=headers,
            )
    assert resp.status_code == 400
    assert resp.json()["code"] == "improve_feedback_required"
    spy.assert_not_awaited()


@requires_db
@requires_redis
def test_improve_with_annotations_only_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """改进只有段落批注（无整体点评）也放行（批注也是具体反馈）。"""
    with _client:
        user = make_user("rev-improve-anno@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "旧正文")

        resp = _client.post(
            _revise_url(project_id, 1),
            json={
                "action": "improve",
                "annotations": [{"paragraph": "那段", "comment": "改一下"}],
            },
            headers=headers,
        )
        assert resp.status_code == 200
        task_id = resp.json()["taskId"]
    _cleanup(task_id)


@requires_db
@requires_redis
def test_regenerate_empty_feedback_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """重生允许空反馈 → 返 taskId。"""
    with _client:
        user = make_user("rev-regen-empty@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "旧正文")

        resp = _client.post(
            _revise_url(project_id, 1),
            json={"action": "regenerate"},
            headers=headers,
        )
        assert resp.status_code == 200
        task_id = resp.json()["taskId"]
    _cleanup(task_id)


@requires_db
@requires_redis
def test_regenerate_does_not_overwrite_chapter_idea(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """code review 回归：重生带反馈时 reset_run **不覆盖** run.chapter_idea（防 feedback 双注入）。

    修复前：service 把 feedback 写进 run.chapter_idea → pipeline effective_idea=feedback →
    context-agent 的 idea_block 与 revision_block 双重渲染同段 feedback。修复后：chapter_idea
    保持首次生成的原值不变，重生方向只经 revision_input 注入。
    """
    with _client:
        user = make_user("rev-no-idea-overwrite@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "旧正文")
        _seed_succeeded_run(
            db_engine, user.id, project_id, 1, chapter_idea="首次生成的本章想法"
        )

        resp = _client.post(
            _revise_url(project_id, 1),
            json={"action": "regenerate", "feedback": "换个冷开场"},
            headers=headers,
        )
        assert resp.status_code == 200
        task_id = resp.json()["taskId"]

    # reset_run 后 chapter_idea 仍是首次的原值，**未被 feedback「换个冷开场」覆盖**。
    run = _read_run(db_engine, user.id, project_id, 1)
    assert run is not None
    assert run.chapter_idea == "首次生成的本章想法"
    assert run.status == "running"
    assert run.steps is None
    _cleanup(task_id)


@requires_db
@requires_redis
def test_revise_not_generated_returns_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """本章尚无正文（无 chapter 行）→ 400 chapter_not_generated，不登记属主。"""
    with _client:
        user = make_user("rev-notgen@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan(db_engine, user.id, project_id)  # 无 chapter 行

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy:
            resp = _client.post(
                _revise_url(project_id, 1),
                json={"action": "regenerate"},
                headers=headers,
            )
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_not_generated"
    spy.assert_not_awaited()


@requires_db
@requires_redis
def test_revise_others_project_returns_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    with _client:
        alice = make_user("rev-owner-a@example.com")
        bob = make_user("rev-owner-b@example.com")
        project_id = _create_project(alice, auth_headers(alice))
        _seed_confirmed_bible(db_engine, alice.id, project_id)

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy:
            resp = _client.post(
                _revise_url(project_id, 1),
                json={"action": "regenerate"},
                headers=auth_headers(bob),
            )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"
    spy.assert_not_awaited()


@requires_db
@requires_redis
def test_revise_invalid_action_422(
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """非法 action（非 improve/regenerate）→ FastAPI 自动 422。"""
    with _client:
        user = make_user("rev-bad-action@example.com")
        resp = _client.post(
            _revise_url(str(uuid.uuid4()), 1),
            json={"action": "delete"},
            headers=auth_headers(user),
        )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
