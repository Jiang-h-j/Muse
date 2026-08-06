"""Story 4.3 Task 2 验证：stage_plan repo（阶段规划落库，@requires_db）。

覆盖：
- upsert_stage_plan：首建阶段规划，goal + chapters JSONB 落库、stage_number 默认 1
- get_stage_plan：按幂等键读回；不存在返 None；租户守卫（他人 user_id 读不到）
- 幂等：同键重写覆盖 goal/chapters、不新增行（重进不重生成的落库侧一致）

repo 方法全 async，用应用 async_session_maker 跑；user/project 用同步 Session 造种子
（照 test_chapter_generation_repo.py 范式）。
"""

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.models.stage_plan import StagePlan
from muse.repositories import stage_plan_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"sp-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="阶段规划测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
@pytest.mark.asyncio
async def test_upsert_and_get_stage_plan(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)
    chapters = [
        {"title": "废物觉醒", "brief": "林凡觉醒传承。"},
        {"title": "外门试炼", "brief": "遭同门排挤。"},
    ]

    async with async_session_maker() as session:
        plan = await repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal="站稳外门。",
            chapters=chapters,
        )
        await session.commit()
        plan_id = plan.id

    # 新建态断言
    assert plan.stage_number == 1
    assert plan.goal == "站稳外门。"

    # 跨 session 读回
    async with async_session_maker() as session:
        got = await repo.get_stage_plan(
            session, user_id=user_id, project_id=project_id
        )
        assert got is not None
        assert got.id == plan_id
        assert got.goal == "站稳外门。"
        assert got.chapters == chapters


@requires_db
@pytest.mark.asyncio
async def test_get_stage_plan_absent_returns_none(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        got = await repo.get_stage_plan(
            session, user_id=user_id, project_id=project_id
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_stage_plan_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读不到本作品的阶段规划（二义合一 None，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal="目标。",
            chapters=[{"title": "t", "brief": "b"}],
        )
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_stage_plan(
            session, user_id=other_user_id, project_id=project_id
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_upsert_idempotent_overwrites_same_row(db_engine: Engine) -> None:
    """同键重写覆盖 goal/chapters、不新增行（重进不重生成的落库侧一致）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal="旧目标。",
            chapters=[{"title": "旧章", "brief": "旧简介"}],
        )
        await session.commit()

    async with async_session_maker() as session:
        await repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal="新目标。",
            chapters=[{"title": "新章", "brief": "新简介"}],
        )
        await session.commit()

    # 读回：值被覆盖为新值。
    async with async_session_maker() as session:
        got = await repo.get_stage_plan(
            session, user_id=user_id, project_id=project_id
        )
        assert got is not None
        assert got.goal == "新目标。"
        assert got.chapters == [{"title": "新章", "brief": "新简介"}]

    # 只有一行（未新增）。
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(StagePlan).where(
                    StagePlan.user_id == user_id,
                    StagePlan.project_id == project_id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1


@requires_db
@pytest.mark.asyncio
async def test_get_latest_stage_returns_highest_stage_number(db_engine: Engine) -> None:
    """Story 4.7：多阶段后 get_latest_stage 返回 stage_number 最大的一行（当前所处阶段）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        for n in (1, 2, 3):
            await repo.upsert_stage_plan(
                session,
                user_id=user_id,
                project_id=project_id,
                goal=f"第 {n} 阶段目标。",
                chapters=[{"title": f"s{n}", "brief": "b"}],
                stage_number=n,
            )
        await session.commit()

    async with async_session_maker() as session:
        latest = await repo.get_latest_stage(
            session, user_id=user_id, project_id=project_id
        )
        assert latest is not None
        assert latest.stage_number == 3
        assert latest.goal == "第 3 阶段目标。"


@requires_db
@pytest.mark.asyncio
async def test_get_latest_stage_absent_returns_none(db_engine: Engine) -> None:
    """无任何阶段规划 → None。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        latest = await repo.get_latest_stage(
            session, user_id=user_id, project_id=project_id
        )
        assert latest is None


@requires_db
@pytest.mark.asyncio
async def test_get_latest_stage_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读不到本作品最新阶段（租户守卫）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        await repo.upsert_stage_plan(
            session,
            user_id=user_id,
            project_id=project_id,
            goal="目标。",
            chapters=[{"title": "t", "brief": "b"}],
        )
        await session.commit()

    async with async_session_maker() as session:
        latest = await repo.get_latest_stage(
            session, user_id=other_user_id, project_id=project_id
        )
        assert latest is None
