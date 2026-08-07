"""Story 4.8 跨阶段章节生成定位修复：跨阶段场景端到端回归（AC3/AC4）。

夹具：两阶段 stage_plan（stage_number=1 带 2 章骨架 + stage_number=2 带 3 章骨架，全局共 5 章）。
断言：
- 全局第 3、4、5 章调 generate 不再 400（返 200 + taskId + register_task_owner 被调用）。
- 全局第 6 章（超出第 2 阶段末章）仍 400 chapter_out_of_range；chapter_number=0 仍 400。
- 全局第 3 章种子 chapter 行（status=draft）调 revise 不 400（200 + taskId）。
- 全局第 4 章（无 chapter 种子）调 revise → 400 chapter_not_generated（前置语义不变）。
- 全局第 6 章调 revise → 400 chapter_out_of_range。
- 已 finalized 章调 revise → 400 chapter_already_finalized（4.7 review patch F1甲不回归）。
- 每次 400 时 register_task_owner 不被调用（沿用既有 spy 范式）。

造 confirmed bible / stage_plan / chapter 用同步 Session 直接造种子。
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


def _seed_two_stage_plans(
    engine: Engine,
    user_id: uuid.UUID,
    project_id: str,
    stage1_count: int = 2,
    stage2_count: int = 3,
) -> None:
    """造两行 StagePlan：stage_number=1 带 stage1_count 章骨架 + stage_number=2 带 stage2_count
    章骨架（全局累计 stage1_count + stage2_count 章）。供跨阶段定位回归。"""
    with Session(engine) as session:
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                stage_number=1,
                goal="首阶段：站稳外门。",
                chapters=[
                    {"title": f"第 {i} 章", "brief": "略"}
                    for i in range(1, stage1_count + 1)
                ],
            )
        )
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                stage_number=2,
                goal="次阶段：入内门。",
                chapters=[
                    {"title": f"第 {stage1_count + i} 章", "brief": "略"}
                    for i in range(1, stage2_count + 1)
                ],
            )
        )
        session.commit()


def _seed_chapter(
    engine: Engine,
    user_id: uuid.UUID,
    project_id: str,
    chapter_number: int,
    text: str,
    status: str = "draft",
) -> None:
    with Session(engine) as session:
        session.add(
            Chapter(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                chapter_number=chapter_number,
                text=text,
                status=status,
            )
        )
        session.commit()


def _gen_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}/generate"


def _revise_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}/revise"


def _cleanup_enqueued_job(task_id: str) -> None:
    """清 ARQ 入队 + SSE 属主键（沿用 test_chapter_generate_api.py 范式）。"""
    import redis as sync_redis

    client = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.delete(sse.task_owner_key(task_id))
        client.delete(f"arq:job:{task_id}")
        client.zrem("arq:queue", task_id)
    finally:
        client.close()


# ========== AC3：跨阶段生成（第 1 阶段 2 章 + 第 2 阶段 3 章 = 全局 5 章） ==========


@requires_db
@requires_redis
def test_generate_cross_stage_chapter_3_4_5_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 3、4、5 章（跨阶段落在第 2 阶段内）调 generate 不再 400。"""
    with _client:
        user = make_user("gen-cross-345@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)  # 2 + 3 = 5 章

        task_ids: list[str] = []
        try:
            for chapter_number in (3, 4, 5):
                with patch.object(
                    sse, "register_task_owner", new=AsyncMock()
                ) as spy_register:
                    resp = _client.post(
                        _gen_url(project_id, chapter_number), json={}, headers=headers
                    )
                assert resp.status_code == 200, (
                    f"chapter {chapter_number} 应 200，实际 {resp.status_code} body={resp.text}"
                )
                body = resp.json()
                assert body.get("taskId")
                task_ids.append(body["taskId"])
                spy_register.assert_awaited_once()
        finally:
            for tid in task_ids:
                _cleanup_enqueued_job(tid)


@requires_db
@requires_redis
def test_generate_cross_stage_chapter_6_out_of_range(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 6 章（超出两阶段累计 5 章）仍 400 chapter_out_of_range，不登记属主。"""
    with _client:
        user = make_user("gen-cross-6@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)  # 累计 5 章

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(_gen_url(project_id, 6), json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_out_of_range"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_generate_chapter_number_zero_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """chapter_number=0 → 400 chapter_out_of_range（下界防御）。"""
    with _client:
        user = make_user("gen-zero@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(_gen_url(project_id, 0), json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_out_of_range"
    spy_register.assert_not_awaited()


# ========== AC4：跨阶段修订 ==========


@requires_db
@requires_redis
def test_revise_cross_stage_chapter_3_ok(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 3 章（落在第 2 阶段）种子 status=draft chapter → revise 不 400（200 + taskId）。"""
    with _client:
        user = make_user("rev-cross-3@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 3, "旧正文", status="draft")

        task_id: str | None = None
        try:
            resp = _client.post(
                _revise_url(project_id, 3),
                json={"action": "improve", "feedback": "加强氛围"},
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"revise chapter 3 应 200，实际 {resp.status_code} body={resp.text}"
            )
            body = resp.json()
            assert body.get("taskId")
            task_id = body["taskId"]
        finally:
            if task_id:
                _cleanup_enqueued_job(task_id)


@requires_db
@requires_redis
def test_revise_cross_stage_chapter_4_not_generated(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 4 章（在第 2 阶段范围内）但无 chapter 种子 → 400 chapter_not_generated。"""
    with _client:
        user = make_user("rev-cross-4@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)
        # 不 seed chapter 4

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(
                _revise_url(project_id, 4),
                json={"action": "improve", "feedback": "x"},
                headers=headers,
            )
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_not_generated"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_revise_cross_stage_chapter_6_out_of_range(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 6 章（越界）调 revise → 400 chapter_out_of_range。"""
    with _client:
        user = make_user("rev-cross-6@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(
                _revise_url(project_id, 6),
                json={"action": "improve", "feedback": "x"},
                headers=headers,
            )
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_out_of_range"
    spy_register.assert_not_awaited()


@requires_db
@requires_redis
def test_revise_finalized_cross_stage_chapter_rejected(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """全局第 3 章种子 status=finalized → revise 仍 400 chapter_already_finalized
    （4.7 review patch F1甲硬约束在跨阶段场景不破）。"""
    with _client:
        user = make_user("rev-cross-final@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_two_stage_plans(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 3, "已定稿正文", status="finalized")

        with patch.object(sse, "register_task_owner", new=AsyncMock()) as spy_register:
            resp = _client.post(
                _revise_url(project_id, 3),
                json={"action": "improve", "feedback": "想再改"},
                headers=headers,
            )
    assert resp.status_code == 400
    assert resp.json()["code"] == "chapter_already_finalized"
    spy_register.assert_not_awaited()
