"""Story 4.2 Task 2 验证：chapter_generation_run repo（断点续跑状态源，@requires_db）。

覆盖：
- create_run：新建运行记录，status=running、steps=None、chapter_idea 落库
- get_run：按幂等键读回；不存在返 None；租户守卫（他人 user_id 读不到）
- update_step：写某段状态+产物到 steps JSONB；幂等（同段覆盖、其余段不动）；
  验证 JSONB flag_modified 生效（跨 session 读回持久化）
- mark_run_status：running→succeeded

repo 方法全 async，用应用 async_session_maker 跑；user/project 用同步 Session 造种子
（照 test_story_bible.py 范式）。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.repositories import chapter_generation_repo as repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """造一个 user + 其名下一个 project，返回 (user_id, project_id)。"""
    with Session(engine) as session:
        user = User(email=f"cg-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="章节编排测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


@requires_db
@pytest.mark.asyncio
async def test_create_and_get_run(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        run = await repo.create_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chapter_idea="想看一场雨夜的重逢",
        )
        await session.commit()
        run_id = run.id

    # 新建态断言
    assert run.status == "running"
    assert run.steps is None
    assert run.chapter_idea == "想看一场雨夜的重逢"

    # 跨 session 读回
    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.id == run_id
        assert got.chapter_number == 1


@requires_db
@pytest.mark.asyncio
async def test_get_run_absent_returns_none(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=user_id, project_id=project_id, chapter_number=99
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_get_run_tenant_guard(db_engine: Engine) -> None:
    """他人 user_id 读不到本作品的运行记录（二义合一 None，NFR3）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    other_user_id, _ = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await repo.create_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=other_user_id, project_id=project_id, chapter_number=1
        )
        assert got is None


@requires_db
@pytest.mark.asyncio
async def test_update_step_persists_jsonb(db_engine: Engine) -> None:
    """update_step 写 JSONB 并持久化（验证 flag_modified 生效，跨 session 读回）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        run = await repo.create_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        await repo.update_step(
            session, run=run, step_name="context", status="succeeded", output="写作任务书X"
        )
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.steps == {"context": {"status": "succeeded", "output": "写作任务书X"}}


@requires_db
@pytest.mark.asyncio
async def test_update_step_idempotent_and_isolated(db_engine: Engine) -> None:
    """同段重写覆盖、其余段不受影响（断点续跑幂等）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        run = await repo.create_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        await repo.update_step(
            session, run=run, step_name="context", status="succeeded", output="brief"
        )
        await repo.update_step(
            session, run=run, step_name="drafter", status="failed", output="半截草稿"
        )
        # drafter 重试成功后覆盖
        await repo.update_step(
            session, run=run, step_name="drafter", status="succeeded", output="完整初稿"
        )
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.steps["context"] == {"status": "succeeded", "output": "brief"}
        assert got.steps["drafter"] == {"status": "succeeded", "output": "完整初稿"}


@requires_db
@pytest.mark.asyncio
async def test_mark_run_status(db_engine: Engine) -> None:
    user_id, project_id = _seed_user_and_project(db_engine)
    async with async_session_maker() as session:
        run = await repo.create_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        await repo.mark_run_status(session, run=run, status="succeeded")
        await session.commit()

    async with async_session_maker() as session:
        got = await repo.get_run(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert got is not None
        assert got.status == "succeeded"
