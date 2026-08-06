"""Story 4.7 验证：定稿本章端点 POST .../finalize（AC1/AC2/AC9）。

- 离线（不需容器）：定稿端点鉴权缺失 401（CurrentUser 前置）。
- HTTP（@requires_db，同步 REST 不需 Redis）：
  - 定稿返 ChapterTextResponse status=finalized、text/revision 保留
  - 幂等：已 finalized 再调 200、仍 finalized
  - 本章未生成（无 chapter 行）→ 400 chapter_not_generated
  - 未确认设定（无 confirmed bible）→ 400 bible_not_confirmed
  - 租户隔离 404（他人 project）
  - 章号 <1 → 400 chapter_out_of_range（防御 API 直打）

造 confirmed bible / chapter 用同步 Session 直接造种子（仿 test_chapter_revise_api.py）。
"""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.main import app
from muse.models.account import User
from muse.models.chapter import Chapter
from muse.models.story_bible import StoryBible
from tests.conftest import requires_db

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
    status: str = "draft",
) -> None:
    with Session(engine) as session:
        session.add(
            Chapter(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                chapter_number=chapter_number,
                text=text,
                revision=revision,
                status=status,
            )
        )
        session.commit()


def _read_chapter(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_number: int
) -> Chapter | None:
    with Session(engine) as session:
        return session.execute(
            select(Chapter).where(
                Chapter.user_id == user_id,
                Chapter.project_id == uuid.UUID(project_id),
                Chapter.chapter_number == chapter_number,
            )
        ).scalar_one_or_none()


def _finalize_url(project_id: str, n: int) -> str:
    return f"/api/projects/{project_id}/chapters/{n}/finalize"


# ========== 离线：鉴权前置 ==========


def test_finalize_without_token_401() -> None:
    resp = _client.post(_finalize_url(str(uuid.uuid4()), 1))
    assert resp.status_code == 401
    assert resp.json()["code"] == "token_invalid"


# ========== HTTP 定稿（同步 REST，只需 DB） ==========


@requires_db
def test_finalize_sets_status_and_keeps_text_revision(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """定稿返 status=finalized，text/revision 保留不变。"""
    with _client:
        user = make_user("fin-ok@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "第一章正文", revision=3)

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "finalized"
        assert body["chapterText"] == "第一章正文"
        assert body["revision"] == 3
        assert body["chapterNumber"] == 1

        # 落库确认。
        row = _read_chapter(db_engine, user.id, project_id, 1)
        assert row is not None
        assert row.status == "finalized"
        assert row.text == "第一章正文"
        assert row.revision == 3


@requires_db
def test_finalize_idempotent(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """幂等：已 finalized 再调 200、仍 finalized（防御 API 直打重复定稿）。"""
    with _client:
        user = make_user("fin-idem@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(
            db_engine, user.id, project_id, 1, "已定稿正文", status="finalized"
        )

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"


@requires_db
def test_finalize_chapter_not_generated_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """本章无正文（无 chapter 行）→ 400 chapter_not_generated。"""
    with _client:
        user = make_user("fin-nogen@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "chapter_not_generated"


@requires_db
def test_finalize_bible_not_confirmed_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """无 confirmed 设定 → 400 bible_not_confirmed（防御前置）。"""
    with _client:
        user = make_user("fin-nobible@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        # 不造 bible，直接造 chapter（防御路径：先校验 confirmed 再校验正文）。
        _seed_chapter(db_engine, user.id, project_id, 1, "正文")

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "bible_not_confirmed"


@requires_db
def test_finalize_tenant_guard_404(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """他人 project → 404（二义合一，租户隔离）。"""
    with _client:
        owner = make_user("fin-owner@example.com")
        owner_headers = auth_headers(owner)
        project_id = _create_project(owner, owner_headers)
        _seed_confirmed_bible(db_engine, owner.id, project_id)
        _seed_chapter(db_engine, owner.id, project_id, 1, "正文")

        other = make_user("fin-other@example.com")
        other_headers = auth_headers(other)
        resp = _client.post(_finalize_url(project_id, 1), headers=other_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "project_not_found"


@requires_db
def test_finalize_chapter_number_below_one_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """章号 0（<1）→ 400 chapter_out_of_range（防御 API 直打）。"""
    with _client:
        user = make_user("fin-badnum@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)

        resp = _client.post(_finalize_url(project_id, 0), headers=headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "chapter_out_of_range"


# ========== F1甲 review patch：定稿后拒改进/重生（chapter_already_finalized） ==========


def _seed_stage_plan_for_revise(
    engine: Engine, user_id: uuid.UUID, project_id: str
) -> None:
    """revise 路径要 stage_plan 章数上界校验，造单行 stage 1（1 章骨架）。"""
    from muse.models.stage_plan import StagePlan

    with Session(engine) as session:
        session.add(
            StagePlan(
                user_id=user_id,
                project_id=uuid.UUID(project_id),
                stage_number=1,
                goal="外门立足。",
                chapters=[{"title": "废物觉醒", "brief": "觉醒传承。"}],
            )
        )
        session.commit()


@requires_db
def test_revise_after_finalize_rejected_400(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """已 finalized 章节再调 revise → 400 chapter_already_finalized（Story 4.7 review F1甲）。

    FR21：定稿版本是后续创作的正式上下文；改进/重生会写 draft 覆盖 finalized，list_recent_chapters
    下一轮就漏取这章。前端 4.5 已在 chapterFinalized=true 时隐藏按钮，本测试守的是「API 直打 /
    多 tab / 前端守卫失效」的穿透路径。覆盖 action=improve 与 action=regenerate 两个分支。
    """
    with _client:
        user = make_user("fin-revise@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_stage_plan_for_revise(db_engine, user.id, project_id)
        _seed_chapter(
            db_engine,
            user.id,
            project_id,
            1,
            "已定稿正文",
            revision=2,
            status="finalized",
        )

        # action=regenerate
        resp_regen = _client.post(
            f"/api/projects/{project_id}/chapters/1/revise",
            json={"action": "regenerate"},
            headers=headers,
        )
        assert resp_regen.status_code == 400
        assert resp_regen.json()["code"] == "chapter_already_finalized"

        # action=improve（带 feedback 通过 AC1 守卫后才到 finalized 守卫）
        resp_improve = _client.post(
            f"/api/projects/{project_id}/chapters/1/revise",
            json={"action": "improve", "feedback": "放慢节奏"},
            headers=headers,
        )
        assert resp_improve.status_code == 400
        assert resp_improve.json()["code"] == "chapter_already_finalized"

        # 落库确认 status 未被改动（防止守卫只是抛错但 upsert 仍然发生）。
        row = _read_chapter(db_engine, user.id, project_id, 1)
        assert row is not None
        assert row.status == "finalized"
        assert row.revision == 2
