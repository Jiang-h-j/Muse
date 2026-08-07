"""Story 5.5 Task 4.4 验证：embedding_projection_service（@requires_db + 离线降级用例）。

覆盖：
- chunk→embed→写入链路：mock provider 返固定向量，断言 embedding 表落本章 chunk 行。
- NullEmbeddingProvider 时 skip 不写库（AC4）。
- len(vectors)!=len(chunks) 时不写半截（错位防线）。
- provider.embed 抛异常时向上抛（由 finalize 层吞——本 service 不吞，调用方降级）。

用真实 session 验证写入（@requires_db）；mock get_embedding_provider 注入 fake provider。
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from muse.core.db import async_session_maker
from muse.models.account import User
from muse.models.project import Project
from muse.providers.embedding_base import EmbeddingProvider
from muse.providers.embedding_null import NullEmbeddingProvider
from muse.repositories import embedding_repo
from muse.services import embedding_projection_service
from tests.conftest import requires_db


def _seed_user_and_project(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        user = User(email=f"embproj-{uuid.uuid4()}@test.local", password_hash="x")
        session.add(user)
        session.flush()
        project = Project(user_id=user.id, title="embedding 投影测试作品", mode="guided")
        session.add(project)
        session.commit()
        return user.id, project.id


class _FakeProvider(EmbeddingProvider):
    """返每个 chunk 一个 1024 维定值向量的 fake（数量与输入对齐）。"""

    def __init__(self, *, mismatch: bool = False, raises: bool = False) -> None:
        self._mismatch = mismatch
        self._raises = raises

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._raises:
            raise RuntimeError("模拟阿里 API 抖动")
        if not texts:
            return []
        vectors = [[float(i)] * 1024 for i in range(len(texts))]
        if self._mismatch:
            return vectors[:-1]  # 故意少一个，触发长度校验
        return vectors

    @property
    def dimensions(self) -> int:
        return 1024


@requires_db
@pytest.mark.asyncio
async def test_project_writes_chunks(db_engine: Engine) -> None:
    """chunk→embed→写入链路：embedding 表落本章 chunk 行。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    text = "\n\n".join(["第一段正文。" * 20, "第二段正文。" * 20, "第三段正文。" * 20])

    with patch.object(
        embedding_projection_service, "get_embedding_provider", return_value=_FakeProvider()
    ):
        await embedding_projection_service.project_chapter_embeddings(
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chapter_text=text,
        )

    async with async_session_maker() as session:
        rows = await embedding_repo.list_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
    assert len(rows) >= 1
    assert all(len(r.embedding) == 1024 for r in rows)
    assert rows[0].model_name == "text-embedding-v3"


@requires_db
@pytest.mark.asyncio
async def test_null_provider_skips_write(db_engine: Engine) -> None:
    """NullEmbeddingProvider → skip 不写库（AC4 降级）。"""
    user_id, project_id = _seed_user_and_project(db_engine)

    with patch.object(
        embedding_projection_service,
        "get_embedding_provider",
        return_value=NullEmbeddingProvider(),
    ):
        await embedding_projection_service.project_chapter_embeddings(
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chapter_text="有正文但没配置 embedding。" * 10,
        )

    async with async_session_maker() as session:
        rows = await embedding_repo.list_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
    assert rows == []


@requires_db
@pytest.mark.asyncio
async def test_length_mismatch_no_partial_write(db_engine: Engine) -> None:
    """len(vectors)!=len(chunks) → 不写半截（错位防线）。"""
    user_id, project_id = _seed_user_and_project(db_engine)
    text = "\n\n".join(["段落甲。" * 30, "段落乙。" * 30, "段落丙。" * 30])

    with patch.object(
        embedding_projection_service,
        "get_embedding_provider",
        return_value=_FakeProvider(mismatch=True),
    ):
        await embedding_projection_service.project_chapter_embeddings(
            user_id=user_id,
            project_id=project_id,
            chapter_number=1,
            chapter_text=text,
        )

    async with async_session_maker() as session:
        rows = await embedding_repo.list_by_chapter(
            session, user_id=user_id, project_id=project_id, chapter_number=1
        )
    assert rows == []  # 不写半截


@pytest.mark.asyncio
async def test_embed_exception_propagates() -> None:
    """provider.embed 抛异常 → 本 service 不吞、向上抛（由 finalize 层降级吞）。

    离线用例（异常在写库前抛，不触碰 DB）。
    """
    with patch.object(
        embedding_projection_service,
        "get_embedding_provider",
        return_value=_FakeProvider(raises=True),
    ):
        with pytest.raises(RuntimeError):
            await embedding_projection_service.project_chapter_embeddings(
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                chapter_number=1,
                chapter_text="正文。" * 30,
            )
