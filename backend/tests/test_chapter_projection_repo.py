"""Story 5.2 Task 6 验证：chapter_projection 三表写路径 repo（@requires_db）。

覆盖：
- chapter_card_repo.upsert_chapter_card：get-or-create 幂等（同键重跑覆盖同值、不产生第二行）。
- story_state_repo.upsert_story_state：get-or-create 幂等（同键重跑覆盖三列快照）。
- story_thread_repo.upsert_new_thread：新建 + 同内容已存在 open thread 防重（defer 台账 B2）；
  last_touched 取 max（E6 单调）。
- story_thread_repo.resolve_thread_by_content：按内容匹配 → UPDATE resolved；
  resolved < introduced 跳过+warning（defer 台账 E5）。
- story_thread_repo.touch_thread_by_content：last_touched 单调不减（defer 台账 E6），
  倒退跳过+warning。

repo 方法全 async，用应用 async_session_maker 跑；user/project 用同步 Session 造种子
（照 test_chapter_card_repo.py / test_story_thread_repo.py 范式）。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.project import Project
from muse.models.story_state import StoryState
from muse.models.story_thread import StoryThread
from muse.repositories import (
    chapter_card_repo,
    story_state_repo,
    story_thread_repo,
)
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"cps-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="投影 repo 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


# ---------- chapter_card_repo.upsert_chapter_card ----------


@requires_db
@pytest.mark.asyncio
async def test_upsert_chapter_card_create_then_overwrite(db_engine: Engine) -> None:
    """upsert 幂等：同键重跑覆盖五要素、不产生第二行（defer 台账 B2 防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await chapter_card_repo.upsert_chapter_card(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            what_happened="第一章发生了什么（第一版）",
            character_changes="人物变化（第一版）",
            new_facts_clues="新增事实（第一版）",
            unresolved_hooks="未解决悬念（第一版）",
            end_state="章末状态（第一版）",
        )
        await session.commit()

    # 重跑（data-agent 断点续跑复用产物 / ARQ 重试）→ 覆盖同行。
    async with async_session_maker() as session:
        await chapter_card_repo.upsert_chapter_card(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            what_happened="第一章发生了什么（重跑覆盖）",
            character_changes="人物变化（重跑覆盖）",
            new_facts_clues="新增事实（重跑覆盖）",
            unresolved_hooks="未解决悬念（重跑覆盖）",
            end_state="章末状态（重跑覆盖）",
        )
        await session.commit()

    # 仍只有一行（未新增副本），且五要素已被覆盖。
    async with async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(ChapterCard).where(
                        ChapterCard.user_id == user_id,
                        ChapterCard.project_id == project_id,
                        ChapterCard.chapter_number == 1,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].what_happened == "第一章发生了什么（重跑覆盖）"
        assert rows[0].end_state == "章末状态（重跑覆盖）"


# ---------- story_state_repo.upsert_story_state ----------


@requires_db
@pytest.mark.asyncio
async def test_upsert_story_state_create_then_overwrite(db_engine: Engine) -> None:
    """upsert 幂等：一作品一份快照，重跑覆盖三列、不产生第二行。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await story_state_repo.upsert_story_state(
            session,
            user_id=user_id,
            project_id=project_id,
            protagonist_state="程野心智动摇（第 1 章）",
            world_rules_state="灵气复苏",
            current_stage="第七码头",
        )
        await session.commit()

    # 第 2 章投影：覆盖三列快照。
    async with async_session_maker() as session:
        await story_state_repo.upsert_story_state(
            session,
            user_id=user_id,
            project_id=project_id,
            protagonist_state="程野行动果决（第 2 章）",
            world_rules_state="灵气复苏 + 时间裂缝",
            current_stage="地下档案库",
        )
        await session.commit()

    async with async_session_maker() as session:
        rows = (
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
        assert len(rows) == 1
        assert rows[0].protagonist_state == "程野行动果决（第 2 章）"
        assert rows[0].world_rules_state == "灵气复苏 + 时间裂缝"
        assert rows[0].current_stage == "地下档案库"


# ---------- story_thread_repo.upsert_new_thread ----------


@requires_db
@pytest.mark.asyncio
async def test_upsert_new_thread_idempotent_same_content(db_engine: Engine) -> None:
    """同内容已存在 open thread → 仅更新 last_touched，不新建行（defer 台账 B2 防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        thread1, created1 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=1,
        )
        await session.commit()
        assert created1 is True

    # 同内容重跑（data-agent 断点续跑）→ 不新建行，只更新 last_touched。
    async with async_session_maker() as session:
        thread2, created2 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=3,
        )
        await session.commit()
        assert created2 is False
        assert thread2.id == thread1.id
        assert thread2.last_touched_chapter_number == 3  # 更新为新值（取 max）


@requires_db
@pytest.mark.asyncio
async def test_upsert_new_thread_content_normalization(db_engine: Engine) -> None:
    """内容匹配归一化（strip + lower）：首尾空白/英文大小写漂移被当同内容（受控决策 5）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        _, created1 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔 Clue A",
            chapter_number=1,
        )
        await session.commit()
        assert created1 is True

    # 同内容但首尾空白 + 英文大小写漂移 → 视为同内容，不新建行。
    async with async_session_maker() as session:
        _, created2 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="  邮戳伏笔 clue a  ",
            chapter_number=2,
        )
        await session.commit()
        assert created2 is False


@requires_db
@pytest.mark.asyncio
async def test_upsert_new_thread_distinct_content_creates_new(db_engine: Engine) -> None:
    """不同内容 → 新建独立 thread（多条 open thread 并存，Story 5.1 已论证无复合唯一约束）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        _, created1 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=1,
        )
        _, created2 = await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="信纸伏笔",
            chapter_number=1,
        )
        await session.commit()
        assert created1 is True
        assert created2 is True

    async with async_session_maker() as session:
        threads = await story_thread_repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert len(threads) == 2


# ---------- story_thread_repo.resolve_thread_by_content ----------


@requires_db
@pytest.mark.asyncio
async def test_resolve_thread_success(db_engine: Engine) -> None:
    """按内容匹配既有 open thread → UPDATE status='resolved' + resolved_chapter_number。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=1,
        )
        await session.commit()

    # 第 3 章回收。
    async with async_session_maker() as session:
        thread = await story_thread_repo.resolve_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            resolved_chapter_number=3,
        )
        await session.commit()
        assert thread is not None
        assert thread.status == "resolved"
        assert thread.resolved_chapter_number == 3
        assert thread.last_touched_chapter_number == 3  # 同步推进

    # resolved 后 list_open_by_project 不再返回。
    async with async_session_maker() as session:
        threads = await story_thread_repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert threads == []


@requires_db
@pytest.mark.asyncio
async def test_resolve_thread_chapter_inversion_skipped(db_engine: Engine) -> None:
    """章号倒挂（resolved < introduced）跳过更新 + 不阻断投影（defer 台账 E5 防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=5,  # 第 5 章埋的
        )
        await session.commit()

    # LLM 产倒挂：resolved=3 < introduced=5 → 跳过。
    async with async_session_maker() as session:
        thread = await story_thread_repo.resolve_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            resolved_chapter_number=3,
        )
        await session.commit()
        assert thread is None  # 跳过返 None

    # thread 仍是 open 未被改动。
    async with async_session_maker() as session:
        rows = (
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
        assert len(rows) == 1
        assert rows[0].status == "open"
        assert rows[0].resolved_chapter_number is None


# ---------- story_thread_repo.touch_thread_by_content ----------


@requires_db
@pytest.mark.asyncio
async def test_touch_thread_updates_last_touched(db_engine: Engine) -> None:
    """按内容匹配 → UPDATE last_touched 为新值。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=1,
        )
        await session.commit()

    # 第 4 章再提。
    async with async_session_maker() as session:
        thread = await story_thread_repo.touch_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            last_touched_chapter_number=4,
        )
        await session.commit()
        assert thread is not None
        assert thread.last_touched_chapter_number == 4


@requires_db
@pytest.mark.asyncio
async def test_touch_thread_regression_skipped(db_engine: Engine) -> None:
    """last_touched 倒退（new <= old）跳过更新 + 不阻断投影（defer 台账 E6 防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await story_thread_repo.upsert_new_thread(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            chapter_number=5,  # last_touched=5
        )
        await session.commit()

    # LLM 产倒退：last_touched=3 <= 5 → 跳过。
    async with async_session_maker() as session:
        thread = await story_thread_repo.touch_thread_by_content(
            session,
            user_id=user_id,
            project_id=project_id,
            content="邮戳伏笔",
            last_touched_chapter_number=3,
        )
        await session.commit()
        assert thread is None  # 跳过返 None

    # last_touched 仍是 5 未被改动。
    async with async_session_maker() as session:
        rows = (
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
        assert len(rows) == 1
        assert rows[0].last_touched_chapter_number == 5
