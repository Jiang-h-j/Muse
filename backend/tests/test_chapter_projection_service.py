"""Story 5.2 Task 6 验证：chapter_projection_service.chapter_commit 单事务编排（@requires_db）。

覆盖：
- 三表齐写成功：chapter_card + story_state + story_thread 三类操作（new/resolved/touched）
  在同一 session 内全部落库。
- 幂等重跑：同 extracted 重跑 → chapter_card / story_state 覆盖同行不产生副本、
  story_thread 同内容 open thread 防重不新建行（defer 台账 B2 防线）。
- **单事务回滚**：mock 某 repo 抛异常 → 三表全 rollback（断言无任何一表落库，AC2
  原子性 NFR4 防半更新穿帮）。

repo 真实调（非 mock）——只 mock 「让某步抛异常」触发 rollback 路径；user/project
用同步 Session 造种子。
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.project import Project
from muse.models.story_state import StoryState
from muse.models.story_thread import StoryThread
from muse.services import chapter_projection_service
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"cpc-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="投影 service 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _extracted_minimal() -> dict:
    """最小可用 data-agent 产出（一章定稿的标准提取 schema）。"""
    return {
        "what_happened": "程野进入地下档案库，发现本不存在的走廊。",
        "character_changes": "程野决定用行动对抗周围人的否认。",
        "new_facts_clues": "未来日期的邮戳、第七码头邮局。",
        "unresolved_hooks": "是谁寄出了信？",
        "end_state": "程野打开标有未来日期的档案抽屉。",
        "protagonist_state": "程野心智动摇但行动果决。",
        "world_rules_state": "灵气复苏、时间裂缝法则失效。",
        "current_stage": "第七码头地下档案库。",
        "new_threads": [
            {"content": "邮戳伏笔", "introduced_chapter_number": 1},
            {"content": "信纸伏笔", "introduced_chapter_number": 1},
        ],
        "resolved_threads": [],
        "touched_threads": [],
    }


@requires_db
@pytest.mark.asyncio
async def test_chapter_commit_full_projection(db_engine: Engine) -> None:
    """三表齐写成功：chapter_card + story_state + story_thread.new_threads 全部落库。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            extracted=_extracted_minimal(),
        )
        await session.commit()

    # chapter_card 五要素落库。
    async with async_session_maker() as session:
        card = (
            await session.execute(
                select(ChapterCard).where(
                    ChapterCard.user_id == user_id,
                    ChapterCard.project_id == project_id,
                    ChapterCard.chapter_number == 1,
                )
            )
        ).scalar_one_or_none()
        assert card is not None
        assert card.what_happened.startswith("程野进入地下档案库")
        assert card.unresolved_hooks == "是谁寄出了信？"

    # story_state 三列快照落库。
    async with async_session_maker() as session:
        state = (
            await session.execute(
                select(StoryState).where(
                    StoryState.user_id == user_id,
                    StoryState.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        assert state is not None
        assert state.protagonist_state == "程野心智动摇但行动果决。"
        assert state.current_stage == "第七码头地下档案库。"

    # story_thread.new_threads 两条 open thread 落库。
    async with async_session_maker() as session:
        threads = (
            (
                await session.execute(
                    select(StoryThread).where(
                        StoryThread.user_id == user_id,
                        StoryThread.project_id == project_id,
                        StoryThread.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(threads) == 2
        contents = {t.content for t in threads}
        assert contents == {"邮戳伏笔", "信纸伏笔"}
        # introduced = last_touched = chapter_number = 1
        for t in threads:
            assert t.introduced_chapter_number == 1
            assert t.last_touched_chapter_number == 1


@requires_db
@pytest.mark.asyncio
async def test_chapter_commit_persists_initial_stage_number(db_engine: Engine) -> None:
    """首次投影固定 stage_number，后续归档不必再由可变计划反推。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=3,
            stage_number=2,
            extracted=_extracted_minimal(),
        )
        await session.commit()

    async with async_session_maker() as session:
        card = (
            await session.execute(
                select(ChapterCard).where(
                    ChapterCard.user_id == user_id,
                    ChapterCard.project_id == project_id,
                    ChapterCard.chapter_number == 3,
                )
            )
        ).scalar_one()
    assert card.stage_number == 2


@requires_db
@pytest.mark.asyncio
async def test_chapter_commit_idempotent_rerun(db_engine: Engine) -> None:
    """幂等重跑：同 extracted 重跑 → chapter_card / story_state 覆盖同行不产生副本、
    story_thread 同内容 open thread 防重不新建行（defer 台账 B2 防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    # 第一遍投影。
    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            extracted=_extracted_minimal(),
        )
        await session.commit()

    # 第二遍重跑（data-agent 断点续跑复用产物 / ARQ 重试）。
    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            extracted=_extracted_minimal(),
        )
        await session.commit()

    # 三表行数仍与原一致（未新增副本）。
    async with async_session_maker() as session:
        cards = (
            (
                await session.execute(
                    select(ChapterCard).where(
                        ChapterCard.user_id == user_id,
                        ChapterCard.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(cards) == 1

        states = (
            (
                await session.execute(
                    select(StoryState).where(
                        StoryState.user_id == user_id,
                        StoryState.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(states) == 1

        threads = (
            (
                await session.execute(
                    select(StoryThread).where(
                        StoryThread.user_id == user_id,
                        StoryThread.project_id == project_id,
                        StoryThread.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(threads) == 2  # 防重，仍 2 条未变 4 条


@requires_db
@pytest.mark.asyncio
async def test_chapter_commit_resolved_and_touched_threads(db_engine: Engine) -> None:
    """三类 thread 操作齐备：new（埋点）+ resolved（回收）+ touched（再提）。

    场景：第 1 章埋两条伏笔（邮戳/信纸）→ 第 3 章定稿时 data-agent 产「回收邮戳伏笔
    （resolved=3）+ 再提信纸伏笔（touched=3）」→ 邮戳变 resolved、信纸 last_touched=3。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    # 第 1 章：埋两条伏笔。
    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            extracted=_extracted_minimal(),
        )
        await session.commit()

    # 第 3 章：回收邮戳 + 再提信纸。
    extracted_ch3 = {
        "what_happened": "程野找到邮戳寄信人。",
        "character_changes": "程野释然。",
        "new_facts_clues": "寄信人是未来的程岚。",
        "unresolved_hooks": "未来的程岚如何知道现在？",
        "end_state": "程野离开邮局。",
        "protagonist_state": "程野释然但仍有疑惑。",
        "world_rules_state": "灵气复苏、时间裂缝、邮戳可跨时间。",
        "current_stage": "第七码头邮局。",
        "new_threads": [],
        "resolved_threads": [
            {"content": "邮戳伏笔", "resolved_chapter_number": 3},
        ],
        "touched_threads": [
            {"content": "信纸伏笔", "last_touched_chapter_number": 3},
        ],
    }
    async with async_session_maker() as session:
        await chapter_projection_service.chapter_commit(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=3,
            extracted=extracted_ch3,
        )
        await session.commit()

    # 邮戳伏笔 → resolved=3，list_open_by_project 不再返回。
    # 信纸伏笔 → 仍 open，last_touched=3。
    async with async_session_maker() as session:
        all_threads = (
            (
                await session.execute(
                    select(StoryThread).where(
                        StoryThread.user_id == user_id,
                        StoryThread.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(all_threads) == 2
        stamp = next(t for t in all_threads if t.content == "邮戳伏笔")
        letter = next(t for t in all_threads if t.content == "信纸伏笔")
        assert stamp.status == "resolved"
        assert stamp.resolved_chapter_number == 3
        assert stamp.last_touched_chapter_number == 3
        assert letter.status == "open"
        assert letter.last_touched_chapter_number == 3


@requires_db
@pytest.mark.asyncio
async def test_chapter_commit_rollback_on_failure(db_engine: Engine) -> None:
    """单事务回滚：mock 某 repo 抛异常 → 三表全 rollback（AC2 原子性 NFR4 防半更新穿帮）。

    场景：mock `story_state_repo.upsert_story_state` 抛 RuntimeError → chapter_commit
    抛异常 → 调用方 session.rollback() → 断言 chapter_card / story_state / story_thread
    三表全未落库（任何一表都不该有行）。
    """
    user_id, project_id = _seed_user_and_project(db_engine)

    # mock 第二个写操作（story_state）抛异常——模拟「chapter_card 已写入、story_state
    # 写入失败」的临界场景。
    with patch(
        "muse.services.chapter_projection_service.story_state_repo.upsert_story_state",
        side_effect=RuntimeError("DB 连接抖动"),
    ):
        async with async_session_maker() as session:
            with pytest.raises(RuntimeError, match="DB 连接抖动"):
                await chapter_projection_service.chapter_commit(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=1,
                    extracted=_extracted_minimal(),
                )
            # 调用方负责 rollback（chapter_commit 不 commit 也不 rollback）。
            await session.rollback()

    # 三表全未落库（chapter_card 在异常前已 upsert，但 rollback 抹掉）。
    async with async_session_maker() as session:
        cards = (
            (
                await session.execute(
                    select(ChapterCard).where(
                        ChapterCard.user_id == user_id,
                        ChapterCard.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert cards == []

        states = (
            (
                await session.execute(
                    select(StoryState).where(
                        StoryState.user_id == user_id,
                        StoryState.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert states == []

        threads = (
            (
                await session.execute(
                    select(StoryThread).where(
                        StoryThread.user_id == user_id,
                        StoryThread.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert threads == []
