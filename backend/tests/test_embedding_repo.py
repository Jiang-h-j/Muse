"""Story 5.5 Task 4.1 验证：embedding_repo 写/读路径（@requires_db，需 pgvector）。

覆盖：
- bulk_insert + list_by_chapter 往返（chunk_index 升序、content/向量/model_name 落库）。
- delete_by_chapter 后重插「先删后插」幂等（同章重跑 chunk 数不翻倍，陷阱④）。
- 租户守卫（别的 user/project 读不到本章 chunk）。

user/project 用同步 Session 造种子（照 test_chapter_projection_repo.py 范式）。
需真实 PG（pgvector 扩展）——@requires_db（MUSE_DB_READY=1）。
"""

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.repositories import embedding_repo
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        user = User(email=f"emb-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="embedding repo 测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


def _vec(fill: float) -> list[float]:
    """构造 1024 维定值向量（与建表 Vector(1024) 对齐）。"""
    return [fill] * 1024


@requires_db
@pytest.mark.asyncio
async def test_bulk_insert_then_list(db_engine: Engine) -> None:
    """bulk_insert + list_by_chapter 往返：chunk_index 升序、字段落库正确。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        inserted = await embedding_repo.bulk_insert(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chunks=[(0, "chunk 零", _vec(0.1)), (1, "chunk 一", _vec(0.2))],
            model_name="text-embedding-v3",
        )
        await session.commit()
    assert inserted == 2

    async with async_session_maker() as session:
        rows = await embedding_repo.list_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
    assert [r.chunk_index for r in rows] == [0, 1]
    assert rows[0].content == "chunk 零"
    assert rows[1].content == "chunk 一"
    assert rows[0].model_name == "text-embedding-v3"
    assert len(rows[0].embedding) == 1024


@requires_db
@pytest.mark.asyncio
async def test_delete_then_reinsert_idempotent(db_engine: Engine) -> None:
    """先删后插幂等（陷阱④）：同章重跑不产副本、chunk 数不翻倍。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await embedding_repo.bulk_insert(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chunks=[(0, "旧chunk0", _vec(0.1)), (1, "旧chunk1", _vec(0.2))],
            model_name="v3",
        )
        await session.commit()

    # 重跑投影：先删本章旧 chunk 再插新的（chunk 数变为 1）。
    async with async_session_maker() as session:
        deleted = await embedding_repo.delete_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
        assert deleted == 2
        await embedding_repo.bulk_insert(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chunks=[(0, "新chunk0", _vec(0.3))],
            model_name="v3",
        )
        await session.commit()

    async with async_session_maker() as session:
        rows = await embedding_repo.list_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
    assert len(rows) == 1  # 不翻倍
    assert rows[0].content == "新chunk0"


@requires_db
@pytest.mark.asyncio
async def test_tenant_guard(db_engine: Engine) -> None:
    """租户守卫：别的 user/project 读不到本章 chunk。"""
    user_a, project_a = _seed_user_and_project(db_engine)
    user_b, project_b = _seed_user_and_project(db_engine)

    async with async_session_maker() as session:
        await embedding_repo.bulk_insert(
            session,
            user_id=user_a,
            project_id=project_a,
            chapter_number=1,
            chunks=[(0, "A的chunk", _vec(0.1))],
            model_name="v3",
        )
        await session.commit()

    async with async_session_maker() as session:
        # 别的 user + project 组合读不到 A 的行。
        rows_b = await embedding_repo.list_by_chapter(
            session, user_id=user_b, project_id=project_b, chapter_number=1
        )
        assert rows_b == []
        # 即使章号相同，别的 project 也读不到（防跨作品泄露）。
        rows_cross = await embedding_repo.list_by_chapter(
            session, user_id=user_a, project_id=project_b, chapter_number=1
        )
        assert rows_cross == []
