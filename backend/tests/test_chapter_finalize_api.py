"""Story 4.7 验证：定稿本章端点 POST .../finalize（AC1/AC2/AC9 + Story 5.2 写后投影）。

- 离线（不需容器）：定稿端点鉴权缺失 401（CurrentUser 前置）。
- HTTP（@requires_db，同步 REST 不需 Redis）：
  - 定稿返 ChapterTextResponse status=finalized、text/revision 保留
  - 幂等：已 finalized 再调 200、仍 finalized
  - 本章未生成（无 chapter 行）→ 400 chapter_not_generated
  - 未确认设定（无 confirmed bible）→ 400 bible_not_confirmed
  - 租户隔离 404（他人 project）
  - 章号 <1 → 400 chapter_out_of_range（防御 API 直打）

**Story 5.2 扩展**：
- 定稿触发 data-agent 投影——chapter_card / story_state / story_thread 三表落库
- 幂等：已 finalized + chapter_card 已存在 → 不重复投影
- 投影失败不卡 status——mock pipeline 抛异常 → status 仍 finalized、chapter_card 缺失
- 断点续跑：已 finalized + chapter_card 缺失 → 再调 finalize 触发投影补齐

**LLM mock 策略**（关键）：5.2 finalize 会跑 data-agent LLM 调用（DeepSeek 真实 API 慢
+ 需真实 key）。本测试 **autouse fixture** mock `chapter_service.pipeline.run_chapter_pipeline`
不打真实 LLM，改为在 `chapter_generation_run.steps` 直接种 data_agent 段产物——
`chapter_projection_service.chapter_commit` 从 run 表读产物做**真实投影**（非 mock），
保证端到端验证「定稿 → 三表落库」的完整链路。

造 confirmed bible / chapter 用同步 Session 直接造种子（仿 test_chapter_revise_api.py）。
"""

import uuid
from collections.abc import Callable
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.main import app
from muse.models.account import User
from muse.models.chapter import Chapter
from muse.models.chapter_card import ChapterCard
from muse.models.chapter_generation import ChapterGenerationRun
from muse.models.embedding import Embedding
from muse.models.story_bible import StoryBible
from muse.models.story_state import StoryState
from muse.models.story_thread import StoryThread
from muse.services import embedding_projection_service
from tests.conftest import requires_db

_client = TestClient(app, raise_server_exceptions=False)


def _default_extracted(chapter_number: int = 1) -> dict:
    """默认 data-agent 产出（一章定稿的标准提取 schema，供 run 表种产物用）。"""
    return {
        "what_happened": f"第 {chapter_number} 章发生了什么（mock data-agent）",
        "character_changes": "人物变化（mock）",
        "new_facts_clues": "新增事实（mock）",
        "unresolved_hooks": "未解决悬念（mock）",
        "end_state": "章末状态（mock）",
        "protagonist_state": "主角状态（mock）",
        "world_rules_state": "世界规则（mock）",
        "current_stage": "当前阶段（mock）",
        "new_threads": [
            {
                "content": f"第 {chapter_number} 章埋伏笔",
                "introduced_chapter_number": chapter_number,
            }
        ],
        "resolved_threads": [],
        "touched_threads": [],
    }


@pytest.fixture(autouse=True)
def _mock_pipeline_run_chapter_pipeline(db_engine: Engine, request):
    """autouse：mock chapter_service.pipeline.run_chapter_pipeline 不打真实 LLM。

    改为在 chapter_generation_run.steps 种 data_agent 段产物（含四段 succeeded 占位），
    chapter_projection_service 从 run 表读产物做真实投影——端到端验证「定稿 → 三表落库」。

    **E6 patch 例外**：标记 `@pytest.mark.real_pipeline` 的测试跳过 mock，真实跑通
    pipeline（只 mock provider 不打真实 LLM）——用于验证「finalize 后 chapter.status/
    revision 不被 pipeline 末段 upsert_chapter 覆盖」（E1+E2 致命 bug 回归防线）。
    """
    # 标记 real_pipeline 的测试跳过 mock，让真实 pipeline 跑起来。
    if request.node.get_closest_marker("real_pipeline"):
        yield
        return

    async def _fake_run_chapter_pipeline(
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        chapter_number: int,
        chapter_idea=None,
        on_progress=None,
        revision_input=None,
        target_revision: int = 1,
        run_data_agent_step: bool = False,
    ) -> str:
        """mock：种 run 表 steps（含 data_agent 段产物），返回 mock 正文。"""
        final_text = f"第 {chapter_number} 章定稿正文（mock pipeline）"
        with Session(db_engine) as s:
            run = (
                s.execute(
                    select(ChapterGenerationRun).where(
                        ChapterGenerationRun.user_id == user_id,
                        ChapterGenerationRun.project_id == project_id,
                        ChapterGenerationRun.chapter_number == chapter_number,
                    )
                )
            ).scalar_one_or_none()
            if run is None:
                run = ChapterGenerationRun(
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_idea=chapter_idea,
                    status="succeeded",
                    steps={},
                )
                s.add(run)
            # 四段 succeeded 占位（finalize 路径只跑 data_agent，四段产物复用 mock 值）。
            run.steps = {
                "context": {"status": "succeeded", "output": "mock 任务书"},
                "drafter": {"status": "succeeded", "output": "mock 初稿"},
                "reviewer": {"status": "succeeded", "output": "mock 审查意见"},
                "polisher": {"status": "succeeded", "output": final_text},
            }
            if run_data_agent_step:
                run.steps["data_agent"] = {
                    "status": "succeeded",
                    "output": _default_extracted(chapter_number),
                }
            run.status = "succeeded"
            s.commit()
        return final_text

    with patch(
        "muse.services.chapter_service.pipeline.run_chapter_pipeline",
        side_effect=_fake_run_chapter_pipeline,
    ):
        yield


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


# ========== Story 5.2 写后投影：定稿触发 data-agent → 三表落库 ==========


def _read_chapter_card(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_number: int
) -> ChapterCard | None:
    with Session(engine) as session:
        return session.execute(
            select(ChapterCard).where(
                ChapterCard.user_id == user_id,
                ChapterCard.project_id == uuid.UUID(project_id),
                ChapterCard.chapter_number == chapter_number,
            )
        ).scalar_one_or_none()


def _read_story_state(
    engine: Engine, user_id: uuid.UUID, project_id: str
) -> StoryState | None:
    with Session(engine) as session:
        return session.execute(
            select(StoryState).where(
                StoryState.user_id == user_id,
                StoryState.project_id == uuid.UUID(project_id),
            )
        ).scalar_one_or_none()


def _read_open_threads(
    engine: Engine, user_id: uuid.UUID, project_id: str
) -> list[StoryThread]:
    with Session(engine) as session:
        return list(
            session.execute(
                select(StoryThread).where(
                    StoryThread.user_id == user_id,
                    StoryThread.project_id == uuid.UUID(project_id),
                    StoryThread.status == "open",
                )
            )
            .scalars()
            .all()
        )


@requires_db
def test_finalize_triggers_projection_three_tables(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.2 AC1/AC2/AC3：定稿触发 data-agent 投影 → chapter_card + story_state +
    story_thread 三表全部落库（单事务原子性）。"""
    with _client:
        user = make_user("fin-proj@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "第一章定稿正文")

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    # chapter_card 五要素落库（mock data-agent 产出）。
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is not None
    assert card.what_happened == "第 1 章发生了什么（mock data-agent）"
    assert card.unresolved_hooks == "未解决悬念（mock）"

    # story_state 三列快照落库。
    state = _read_story_state(db_engine, user.id, project_id)
    assert state is not None
    assert state.protagonist_state == "主角状态（mock）"
    assert state.current_stage == "当前阶段（mock）"

    # story_thread.new_threads 落库（1 条 open thread）。
    threads = _read_open_threads(db_engine, user.id, project_id)
    assert len(threads) == 1
    assert threads[0].content == "第 1 章埋伏笔"
    assert threads[0].status == "open"
    assert threads[0].introduced_chapter_number == 1
    assert threads[0].last_touched_chapter_number == 1


@requires_db
def test_finalize_idempotent_skips_projection_when_card_exists(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.2 幂等：已 finalized + chapter_card 已存在 → 不重复投影（防御 API 直打
    重复定稿 / data-agent 断点续跑不重复付费 NFR5）。"""
    with _client:
        user = make_user("fin-idem@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(
            db_engine, user.id, project_id, 1, "已定稿正文", status="finalized"
        )
        # 手工种 chapter_card（模拟「上次已投影完成」）。
        with Session(db_engine) as session:
            session.add(
                ChapterCard(
                    user_id=user.id,
                    project_id=uuid.UUID(project_id),
                    chapter_number=1,
                    what_happened="已有卡片（上次投影）",
                    character_changes="",
                    new_facts_clues="",
                    unresolved_hooks="",
                    end_state="",
                )
            )
            session.commit()

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    # chapter_card 仍是手工种的值（未被 mock data-agent 覆盖——幂等跳过投影）。
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is not None
    assert card.what_happened == "已有卡片（上次投影）"


@requires_db
def test_finalize_projection_failure_keeps_status_finalized(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.2 AC5 + 受控决策 2：投影失败不卡 status——status 仍 finalized、
    chapter_card 缺失（下次断点续跑补齐）。"""
    with _client:
        user = make_user("fin-fail@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "第一章定稿正文")

        # mock chapter_commit 抛异常（模拟投影 LLM 抖动 / DB 写异常）。
        with patch(
            "muse.services.chapter_projection_service.chapter_card_repo.upsert_chapter_card",
            side_effect=RuntimeError("DB 连接抖动"),
        ):
            resp = _client.post(_finalize_url(project_id, 1), headers=headers)
            assert resp.status_code == 200  # 定稿成功（投影失败不向上抛）
            assert resp.json()["status"] == "finalized"

    # status 仍 finalized（保留），chapter_card 缺失（投影失败）。
    row = _read_chapter(db_engine, user.id, project_id, 1)
    assert row is not None
    assert row.status == "finalized"
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is None

    # B4 patch：三表全空（story_state / story_thread 也未落库——单事务原子性防线）。
    state = _read_story_state(db_engine, user.id, project_id)
    assert state is None
    threads = _read_open_threads(db_engine, user.id, project_id)
    assert threads == []


@requires_db
def test_finalize_resume_projection_when_card_missing(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.2 断点续跑：已 finalized + chapter_card 缺失（上次投影失败）→ 再调
    finalize 触发投影补齐（data-agent 复用 run 表 polisher 段产物，不重新调 drafter）。"""
    with _client:
        user = make_user("fin-resume@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(
            db_engine, user.id, project_id, 1, "已定稿正文", status="finalized"
        )
        # chapter_card 缺失（模拟「上次投影失败」状态）。

        resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    # 投影补齐：chapter_card / story_state / story_thread 三表全部落库。
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is not None
    assert card.what_happened == "第 1 章发生了什么（mock data-agent）"

    state = _read_story_state(db_engine, user.id, project_id)
    assert state is not None

    threads = _read_open_threads(db_engine, user.id, project_id)
    assert len(threads) == 1


# ========== Story 5.2 review E6 patch：真实跑通 pipeline 验证 status/revision 不被改 ==========


@requires_db
@pytest.mark.real_pipeline
def test_finalize_real_pipeline_preserves_status_and_revision(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.2 review E6 patch：真实跑通 pipeline（不 mock run_chapter_pipeline、只
    mock provider），验证「finalize 后 chapter.status/revision 不被 pipeline 末段
    upsert_chapter 覆盖」（E1+E2 致命 bug 的回归防线）。

    场景：revision=3 的 draft 章调 finalize → chapter_service 把 status 置 finalized +
    保留 revision=3 → 真实跑 pipeline（四段 cached 复用 mock 产物 + data_agent 段跑
    mock provider）→ 断言 DB 中 chapter.status 仍 finalized、revision 仍 3（未被
    pipeline 末段 upsert_chapter 覆盖回 draft/1）。
    """
    with _client:
        user = make_user("fin-real@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        # 种 revision=3 的 draft 章（模拟「改进过 2 次」）。
        _seed_chapter(
            db_engine,
            user.id,
            project_id,
            1,
            "第一章定稿正文（第 3 版）",
            revision=3,
            status="draft",
        )

        # 不 mock run_chapter_pipeline（让它真实跑）；只 mock provider 不打真实 LLM。
        # 造一个 mock provider：run_data_agent 返回合法 JSON。
        from unittest.mock import AsyncMock, MagicMock

        from muse.orchestration import steps
        from muse.providers.base import ChatResult

        def _fake_chat_result(content: str) -> ChatResult:
            return ChatResult(
                content=content,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                model="deepseek-v4-flash",
            )

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(
            return_value=_fake_chat_result(
                '{"what_happened": "真实 pipeline 提取", "character_changes": "人物变化", '
                '"new_facts_clues": "新增事实", "unresolved_hooks": "未解决悬念", '
                '"end_state": "章末状态", "protagonist_state": "主角状态", '
                '"world_rules_state": "世界规则", "current_stage": "当前阶段", '
                '"new_threads": [], "resolved_threads": [], "touched_threads": []}'
            )
        )

        # patch get_provider_for_user 返回 mock provider（不打真实 DeepSeek）。
        with patch.object(
            steps, "get_provider_for_user", AsyncMock(return_value=mock_provider)
        ):
            resp = _client.post(_finalize_url(project_id, 1), headers=headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "finalized"
            assert resp.json()["revision"] == 3  # API 响应保留 revision=3

    # 断言 DB 中 chapter.status 仍 finalized、revision 仍 3（未被 pipeline 末段
    # upsert_chapter 覆盖回 draft/1——E1+E2 致命 bug 的回归防线）。
    row = _read_chapter(db_engine, user.id, project_id, 1)
    assert row is not None
    assert row.status == "finalized"
    assert row.revision == 3

    # chapter_card 落库（真实 pipeline 跑的 data_agent 提取）。
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is not None
    assert card.what_happened == "真实 pipeline 提取"


# ========== Story 5.5：定稿后 embedding 落库 + embedding 失败不影响定稿 ==========


class _FakeEmbeddingProvider:
    """返每个 chunk 一个 1024 维定值向量的 fake（数量与输入对齐）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    @property
    def dimensions(self) -> int:
        return 1024


class _RaisingEmbeddingProvider:
    """embed 抛异常，模拟阿里 API 抖动（验证 embedding 失败不阻断定稿）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("模拟 embedding API 失败")

    @property
    def dimensions(self) -> int:
        return 1024


def _read_embedding_chunks(
    engine: Engine, user_id: uuid.UUID, project_id: str, chapter_number: int
) -> list[Embedding]:
    with Session(engine) as session:
        return list(
            session.execute(
                select(Embedding)
                .where(
                    Embedding.user_id == user_id,
                    Embedding.project_id == uuid.UUID(project_id),
                    Embedding.chapter_number == chapter_number,
                )
                .order_by(Embedding.chunk_index.asc())
            )
            .scalars()
            .all()
        )


@requires_db
def test_finalize_writes_embedding_chunks(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.5 AC3：定稿后 embedding 表落本章 chunk 行（mock provider 返固定向量）。"""
    with _client:
        user = make_user("fin-emb@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "第一章定稿正文，用于向量化。")

        with patch.object(
            embedding_projection_service,
            "get_embedding_provider",
            return_value=_FakeEmbeddingProvider(),
        ):
            resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    rows = _read_embedding_chunks(db_engine, user.id, project_id, 1)
    assert len(rows) >= 1
    assert all(len(r.embedding) == 1024 for r in rows)
    assert rows[0].model_name == "text-embedding-v3"


@requires_db
def test_finalize_embedding_failure_does_not_block(
    db_engine: Engine,
    make_user: Callable[..., User],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    """Story 5.5 AC3：embedding 失败不影响定稿成功 + 三表仍落库（provider 抛异常）。"""
    with _client:
        user = make_user("fin-emb-fail@example.com")
        headers = auth_headers(user)
        project_id = _create_project(user, headers)
        _seed_confirmed_bible(db_engine, user.id, project_id)
        _seed_chapter(db_engine, user.id, project_id, 1, "第一章定稿正文")

        with patch.object(
            embedding_projection_service,
            "get_embedding_provider",
            return_value=_RaisingEmbeddingProvider(),
        ):
            resp = _client.post(_finalize_url(project_id, 1), headers=headers)
        # 定稿仍 200、status 仍 finalized（embedding 失败被 finalize 层吞、不阻断）。
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    # 三表仍落库（chapter_card 在），embedding 表本章无行（失败降级）。
    card = _read_chapter_card(db_engine, user.id, project_id, 1)
    assert card is not None
    rows = _read_embedding_chunks(db_engine, user.id, project_id, 1)
    assert rows == []
