"""Story 5.1 Task 5 验证：story_state repo 最小读法（get_by_project，@requires_db）。

覆盖：
- get_by_project：按 (user_id, project_id) 读回当前快照；不存在返 None；租户
  守卫（他人 user_id 读不到）；同 user 不同 project 也读不到。

repo 方法全 async，用应用 async_session_maker 跑；user/project/story_state 种子
用同步 Session 造（同 test_chapter_card_repo.py 范式——本 story 无 upsert 写路径
（归 5.2），seed 直接 add ORM 对象进库）。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.models.story_state import StoryState
from muse.repositories import story_state_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"ssr-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="状态 repo 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _seed_state(
    engine: Engine,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    protagonist_state: str = "",
    world_rules_state: str = "",
    current_stage: str = "",
) -> None:
    """同步 Session 直接插一条 story_state（本 story 无 repo 写路径）。"""
    with Session(engine) as session:
        session.add(
            StoryState(
                user_id=user_id,
                project_id=project_id,
                protagonist_state=protagonist_state,
                world_rules_state=world_rules_state,
                current_stage=current_stage,
            )
        )
        session.commit()


@requires_db
@pytest.mark.asyncio
async def test_get_by_project_returns_row(db_engine: Engine) -> None:
    """按 (user_id, project_id) 一步取回本作品的故事状态快照。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    _seed_state(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        protagonist_state="程野心智动摇",
        world_rules_state="灵气复苏、境界分九品",
        current_stage="第七码头地下档案库",
    )

    async with async_session_maker() as session:
        got = await repo.get_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert got is not None
        assert got.protagonist_state == "程野心智动摇"
        assert got.world_rules_state == "灵气复苏、境界分九品"
        assert got.current_stage == "第七码头地下档案库"


@requires_db
@pytest.mark.asyncio
async def test_get_by_project_absent_returns_none(db_engine: Engine) -> None:
    """未写过任何章节、无快照 → None（与「不属于我」二义合一）。

    写前上下文注入空块 / 归档页空态消费此 None——非错误。
    """
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        got = await repo.get_by_project(
            session, user_id=user_id, project_id=project_id
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_by_project_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读不到本作品的故事状态（租户守卫，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    _seed_state(
        db_engine,
        user_id=user_id,
        project_id=project_id,
        protagonist_state="我的内心秘密",
    )

    async with async_session_maker() as session:
        got = await repo.get_by_project(
            session, user_id=other_user_id, project_id=project_id
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_by_project_cross_project_isolation(db_engine: Engine) -> None:
    """同 user_id 不同 project_id 读不到——project_id 隔离生效。"""
    user_id, project_id_x = _seed_user_and_project(db_engine)
    with Session(db_engine) as session:
        project_y = Project(user_id=user_id, title="同用户另一作品", mode="free")
        session.add(project_y)
        session.commit()
        project_id_y = project_y.id

    _seed_state(
        db_engine,
        user_id=user_id,
        project_id=project_id_x,
        protagonist_state="作品 X 的主角",
    )

    async with async_session_maker() as session:
        got = await repo.get_by_project(
            session, user_id=user_id, project_id=project_id_y
        )
        assert got is None
