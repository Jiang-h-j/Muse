"""Story 4.4 Task 1 验证：chapter repo（章节终稿正文落库，@requires_db）。

覆盖：
- upsert_chapter：首建章节正文，text/revision/status 落库、复合唯一键
- get_chapter：按幂等键读回；不存在返 None；租户守卫（他人 user_id 读不到）
- upsert 幂等：同键重写覆盖 text、不新增行（重生成/ARQ 重试不产生正文副本）
- list_recent_chapters：取 before_number 之前最近若干章，降序、limit、租户守卫、第一章空

repo 方法全 async，用应用 async_session_maker 跑；user/project 用同步 Session 造种子
（照 test_stage_plan_repo.py 范式）。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.chapter import Chapter
from muse.models.project import Project
from muse.repositories import chapter_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"ch-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="章节正文测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
@pytest.mark.asyncio
async def test_upsert_and_get_chapter(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        chapter = await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="雨落下来了。",
        )
        await session.commit()
        chapter_id = chapter.id

    # 新建态默认值断言（revision=1、status=draft）。
    assert chapter.chapter_number == 1
    assert chapter.text == "雨落下来了。"
    assert chapter.revision == 1
    assert chapter.status == "draft"

    # 跨 session 读回。
    async with async_session_maker() as session:
        got = await repo.get_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.id == chapter_id
        assert got.text == "雨落下来了。"


@requires_db
@pytest.mark.asyncio
async def test_get_chapter_absent_returns_none(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        got = await repo.get_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_chapter_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读不到本作品的章节正文（二义合一 None，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="正文。",
        )
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_chapter(
            session, user_id=other_user_id, project_id=project_id, chapter_number=1
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_upsert_idempotent_overwrites_same_row(db_engine: Engine) -> None:
    """同键重写覆盖 text、不新增行（重生成/ARQ 重试不产生正文副本）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="旧正文。",
        )
        await session.commit()

    async with async_session_maker() as session:
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="新正文。",
        )
        await session.commit()

    # 读回：值被覆盖为新值。
    async with async_session_maker() as session:
        got = await repo.get_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.text == "新正文。"

    # 只有一行（未新增）。
    async with async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    select(Chapter).where(
                        Chapter.user_id == user_id,
                        Chapter.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@requires_db
@pytest.mark.asyncio
async def test_list_recent_chapters_order_and_limit(db_engine: Engine) -> None:
    """取最近若干**已定稿**章：降序、limit=1 取前一章（4.7 只读 finalized）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        for n in (1, 2, 3):
            await repo.upsert_chapter(
                session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=n,
                text=f"第 {n} 章正文。",
                status="finalized",
            )
        await session.commit()

    # 写第 4 章时取最近 1 章 → 第 3 章。
    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=4,
            limit=1,
        )
        assert len(recent) == 1
        assert recent[0].chapter_number == 3

    # 取最近 2 章 → 第 3、2 章（降序）。
    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=4,
            limit=2,
        )
        assert [c.chapter_number for c in recent] == [3, 2]


@requires_db
@pytest.mark.asyncio
async def test_list_recent_chapters_first_chapter_empty(db_engine: Engine) -> None:
    """第一章无前序 → 空列表（context-agent 注入空块，不报错）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=1,
            limit=1,
        )
        assert recent == []


@requires_db
@pytest.mark.asyncio
async def test_list_recent_chapters_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 列不到本作品章节（租户守卫）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="正文。",
            status="finalized",
        )
        await session.commit()

    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=other_user_id,
            project_id=project_id,
            before_number=2,
            limit=1,
        )
        assert recent == []


@requires_db
@pytest.mark.asyncio
async def test_list_recent_chapters_only_finalized(db_engine: Engine) -> None:
    """Story 4.7：只召回 status='finalized' 的前序章，draft 不注入（FR21 定稿成正式上下文）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        # 第 1 章已定稿、第 2 章仍是草稿（未定稿）。
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            text="第 1 章正文（已定稿）。",
            status="finalized",
        )
        await repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=2,
            text="第 2 章正文（草稿）。",
            status="draft",
        )
        await session.commit()

    # 写第 3 章时取最近 2 章：只应召回已定稿的第 1 章，草稿第 2 章被过滤。
    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=3,
            limit=2,
        )
        assert [c.chapter_number for c in recent] == [1]


@requires_db
@pytest.mark.asyncio
async def test_list_recent_chapters_all_draft_empty(db_engine: Engine) -> None:
    """Story 4.7：前序章全是草稿（无定稿）→ 空列表（context-agent 仅用全量设定，不崩）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        for n in (1, 2):
            await repo.upsert_chapter(
                session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=n,
                text=f"第 {n} 章草稿。",
                status="draft",
            )
        await session.commit()

    async with async_session_maker() as session:
        recent = await repo.list_recent_chapters(
            session,
            user_id=user_id,
            project_id=project_id,
            before_number=3,
            limit=2,
        )
        assert recent == []
