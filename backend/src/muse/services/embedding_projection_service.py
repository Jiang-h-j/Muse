"""章节 embedding 投影（Story 5.5 Task 3，AC3/AC4）。

**定位**：章节定稿后，把正文 chunk 化 + 向量化 + 写入 embedding 表——是 chapter-commit
三表投影**之外、紧随其后的独立步骤**（受控决策 3、5）。不进 chapter_commit 单事务、不进
五段流水线（run 表）。由 chapter_service.finalize_and_project_chapter 在三表 commit 成功
后调用。

**事务边界（陷阱③）**：向量化外部 API 调用（provider.embed）在 DB 事务/session 块**之外**
——外部 HTTP 可能几百 ms~数秒，绝不在事务内调（占用连接等外部 API）。顺序：
① embed() 拿 vectors（无 session）→ ② async_session_maker() 独立事务 delete+insert+commit。

**降级（AC4）**：无 embedding 配置（NullEmbeddingProvider）或空 chunk/空向量 → early
return + logger.info，不打 API、不写库、不报错。
"""

import logging
import uuid

from muse.core.db import async_session_maker
from muse.core.settings import get_settings
from muse.providers.embedding_factory import get_embedding_provider
from muse.providers.embedding_null import NullEmbeddingProvider
from muse.rag.chunking import chunk_chapter_text
from muse.repositories import embedding_repo

logger = logging.getLogger("muse")


async def project_chapter_embeddings(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_text: str,
) -> None:
    """把定稿正文 chunk 化 + 向量化 + 写入 embedding（独立事务，失败由调用方吞）。

    chapter_text：**chapter 表实际入库的定稿正文**（陷阱⑥，调用方传 existing.text——不用
    polisher 产物），语义上「向量化的是实际定稿正文」。

    流程（AC3/AC4）：
    1. 取 provider + chunk 化。
    2. 无 chunk 或 provider 是 Null → early return + info（AC4 降级）。
    3. 向量化（**事务外**，陷阱③）；embed 返 [] → early return。
    4. 长度校验：vectors 数 ≠ chunks 数 → warning + return（不写半截，防错位）。
    5. **独立事务**：delete_by_chapter（先删旧 chunk，重跑幂等，陷阱④）→ bulk_insert → commit。
    """
    provider = get_embedding_provider()
    chunks = chunk_chapter_text(chapter_text)

    # AC4 降级：无 chunk（空正文）或无 embedding 配置（Null）→ skip，不打 API 不写库。
    if not chunks or isinstance(provider, NullEmbeddingProvider):
        logger.info(
            "embedding 投影 skip（无 chunk 或未配置 embedding）：project=%s chapter=%s "
            "chunks=%d provider=%s",
            project_id,
            chapter_number,
            len(chunks),
            type(provider).__name__,
        )
        return

    # 向量化在事务外（陷阱③）：外部 HTTP，绝不在 DB 事务/session 块内调。
    vectors = await provider.embed(chunks)
    if not vectors:
        # Null 兜底或空返回——skip 写入（AC4）。
        logger.info(
            "embedding 投影 skip（provider.embed 返空）：project=%s chapter=%s",
            project_id,
            chapter_number,
        )
        return

    # 长度校验：向量数须与 chunk 数一一对应；不等则不写半截（防 chunk 文本与向量错位，
    # 错位 = RAG 召回张冠李戴）。
    if len(vectors) != len(chunks):
        logger.warning(
            "embedding 投影跳过（向量数与 chunk 数不匹配，不写半截）：project=%s chapter=%s "
            "chunks=%d vectors=%d",
            project_id,
            chapter_number,
            len(chunks),
            len(vectors),
        )
        return

    model_name = get_settings().embedding_model
    # 独立事务写入（陷阱③④）：先删本章旧 chunk（重跑幂等）→ 批量插入 → commit。
    async with async_session_maker() as session:
        deleted = await embedding_repo.delete_by_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        inserted = await embedding_repo.bulk_insert(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            chunks=list(zip(range(len(chunks)), chunks, vectors, strict=True)),
            model_name=model_name,
        )
        await session.commit()

    logger.info(
        "embedding 投影完成：project=%s chapter=%s deleted=%d inserted=%d",
        project_id,
        chapter_number,
        deleted,
        inserted,
    )
