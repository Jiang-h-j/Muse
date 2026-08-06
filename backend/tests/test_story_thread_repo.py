"""Story 5.1 Task 5 验证：story_thread repo 最小读法（list_open_by_project，@requires_db）。

覆盖：
- list_open_by_project：列出 status='open' 的全部 thread，按 last_touched_chapter_number
  降序；无 open thread → 空列表；租户守卫（他人 user_id 列不到）；resolved/abandoned
  被过滤。

repo 方法全 async，用应用 async_session_maker 跑；user/project/story_thread 种子
用同步 Session 造（同 test_chapter_card_repo.py 范式——本 story 无 insert_thread
写路径（归 5.2），seed 直接 add ORM 对象进库）。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.models.story_thread import StoryThread
from muse.repositories import story_thread_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"str-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="伏笔 repo 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _seed_thread(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    content: str,
    introduced: int,
    last_touched: int,
    status: str = "open",
    resolved: int | None = None,
) -> None:
    """同步 Session 直接插一条 thread（本 story 无 repo 写路径）。"""
    with Session(engine) as session:
        session.add(
            StoryThread(
                user_id=user_id,
                project_id=project_id,
                content=content,
                status=status,
                introduced_chapter_number=introduced,
                last_touched_chapter_number=last_touched,
                resolved_chapter_number=resolved,
            )
        )
        session.commit()


@requires_db
@pytest.mark.asyncio
async def test_list_open_returns_only_open_sorted_desc(db_engine: Engine) -> None:
    """只列 status='open' 的 thread，按 last_touched_chapter_number 降序。

    - resolved 不计入（伏笔已收回）。
    - 最近活跃的 thread 在前——是 5.6 RAG「N 章未回收伏笔」召回的排序依据。
    """
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="埋点 A 在第 1 章，第 5 章再提",
        introduced=1,
        last_touched=5,
    )
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="埋点 B 在第 2 章一次埋伏后再没动",
        introduced=2,
        last_touched=2,
    )
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="埋点 C 已回收（第 4 章收的）",
        introduced=1,
        last_touched=4,
        status="resolved",
        resolved=4,
    )

    async with async_session_maker() as session:
        threads = await repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert len(threads) == 2
        # 降序：last_touched=5 在前、last_touched=2 在后
        assert threads[0].content == "埋点 A 在第 1 章，第 5 章再提"
        assert threads[0].last_touched_chapter_number == 5
        assert threads[1].content == "埋点 B 在第 2 章一次埋伏后再没动"
        assert threads[1].last_touched_chapter_number == 2


@requires_db
@pytest.mark.asyncio
async def test_list_open_empty_when_none_open(db_engine: Engine) -> None:
    """无 open thread（全 resolved / 作品刚建）→ 空列表（非错误，5.6 RAG 召回空块）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="已回收伏笔",
        introduced=1,
        last_touched=3,
        status="resolved",
        resolved=3,
    )

    async with async_session_maker() as session:
        threads = await repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert threads == []


@requires_db
@pytest.mark.asyncio
async def test_list_open_filters_abandoned(db_engine: Engine) -> None:
    """status='abandoned' 也被 list_open 滤掉（5-1 code review E1 patch）。

    变异测试防线：若有人把 where 从 `status == "open"` 改成 `status != "resolved"`，
    abandoned 会泄漏进结果——现有测试只断言 resolved 被滤、本用例补 abandoned 断言。
    """
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="open 伏笔",
        introduced=1,
        last_touched=2,
        status="open",
    )
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="abandoned 伏笔（V2 手动放弃路径）",
        introduced=1,
        last_touched=3,
        status="abandoned",
    )

    async with async_session_maker() as session:
        threads = await repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert len(threads) == 1
        assert threads[0].content == "open 伏笔"
        assert threads[0].status == "open"


@requires_db
@pytest.mark.asyncio
async def test_list_open_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 列不到本作品的 thread（租户守卫，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        content="我内心秘密伏笔",
        introduced=1,
        last_touched=1,
    )

    async with async_session_maker() as session:
        threads = await repo.list_open_by_project(
            session, user_id=other_user_id, project_id=project_id
        )
        assert threads == []


@requires_db
@pytest.mark.asyncio
async def test_list_open_cross_project_isolation(db_engine: Engine) -> None:
    """同 user_id 不同 project_id 列不到——project_id 隔离生效。"""
    user_id, project_id_x = _seed_user_and_project(db_engine)
    with Session(db_engine) as session:
        project_y = Project(user_id=user_id, title="同用户另一作品", mode="free")
        session.add(project_y)
        session.commit()
        project_id_y = project_y.id

    _seed_thread(
        db_engine,
        user_id=user_id,
        project_id=project_id_x,
        content="作品 X 的伏笔",
        introduced=1,
        last_touched=1,
    )

    async with async_session_maker() as session:
        threads = await repo.list_open_by_project(
            session, user_id=user_id, project_id=project_id_y
        )
        assert threads == []
