"""Story 5.1 Task 5 验证：chapter_card repo 最小读法（get_by_chapter，@requires_db）。

覆盖：
- get_by_chapter：按幂等键读回；不存在返 None；租户守卫（他人 user_id 读不到）。
- chapter_number 隔离：同作品不同章的卡分别读得到。

repo 方法全 async，用应用 async_session_maker 跑；user/project/chapter_card 种子
用同步 Session 造（照 test_chapter_repo.py / test_stage_plan_repo.py 范式——本 story
无 upsert_chapter_card 写路径（归 5.2），seed 直接 add ORM 对象进库）。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.chapter_card import ChapterCard
from muse.models.project import Project
from muse.repositories import chapter_card_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"ccr-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="章节卡 repo 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _seed_card(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    what_happened: str = "本章内容",
) -> None:
    """同步 Session 直接插一张章节卡（本 story 无 repo 写路径）。"""
    with Session(engine) as session:
        session.add(
            ChapterCard(
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                what_happened=what_happened,
            )
        )
        session.commit()


@requires_db
@pytest.mark.asyncio
async def test_get_by_chapter_returns_row(db_engine: Engine) -> None:
    """按 (user_id, project_id, chapter_number) 一步取回本作品的章节卡。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        chapter_number=2,
        what_happened="第二章发生的事",
    )

    async with async_session_maker() as session:
        got = await repo.get_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=2
        )
        assert got is not None
        assert got.chapter_number == 2
        assert got.what_happened == "第二章发生的事"


@requires_db
@pytest.mark.asyncio
async def test_get_by_chapter_absent_returns_none(db_engine: Engine) -> None:
    """该章尚未投影卡 → None（与「不属于我」二义合一）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        got = await repo.get_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_by_chapter_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读取不到本作品的章节卡（二义合一 None，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    _seed_card(
        db_engine, user_id=user_id, project_id=project_id, chapter_number=1
    )

    async with async_session_maker() as session:
        got = await repo.get_by_chapter(
            session, user_id=other_user_id, project_id=project_id, chapter_number=1
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_by_chapter_number_isolation(db_engine: Engine) -> None:
    """同作品不同章的卡分别读得到——chapter_number 是幂等键的一部分。

    第 1 章与第 2 章各有独立的卡片行，按章号取不会串。
    """
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        chapter_number=1,
        what_happened="第一章内容",
    )
    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        chapter_number=2,
        what_happened="第二章内容",
    )

    async with async_session_maker() as session:
        c1 = await repo.get_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        c2 = await repo.get_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=2
        )
        assert c1 is not None and c2 is not None
        assert c1.what_happened == "第一章内容"
        assert c2.what_happened == "第二章内容"


@requires_db
@pytest.mark.asyncio
async def test_get_by_chapter_cross_project_isolation(db_engine: Engine) -> None:
    """同 user_id 不同 project_id 也读不到——project_id 是租户守卫的一部分。

    攻者拿到 project_id X 处第 1 章的卡，换用自己 project_id Y 同章号仍读不到
    （即便 user_id 相同，project_id 也必须一致）。
    """
    user_id, project_id_x = _seed_user_and_project(db_engine)
    with Session(db_engine) as session:
        # 同 user 名下另一个 project
        project_y = Project(user_id=user_id, title="同用户另一作品", mode="free")
        session.add(project_y)
        session.commit()
        project_id_y = project_y.id

    _seed_card(
        db_engine,
        user_id=user_id,
        project_id=project_id_x,
        chapter_number=1,
        what_happened="作品 X 的第 1 章",
    )

    async with async_session_maker() as session:
        got = await repo.get_by_chapter(
            session, user_id=user_id, project_id=project_id_y, chapter_number=1
        )
        assert got is None
