"""归档域 DAO：embedding（章节向量 chunk）写/读路径（Story 5.5）。

延续 chapter_card_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service（embedding_projection_service 在独立事务内 delete+insert+commit）。所有查询
显式绑定 user_id 租户守卫（NFR3）——不提供绕过 user_id 的全表查询入口。

**方法**：
- delete_by_chapter：删本章全部旧 chunk（重跑投影「先删后插」保幂等，陷阱④）。
- bulk_insert：批量插入本章 chunk 行（session.add_all + flush，不 commit）。
- list_by_chapter：按 (user_id, project_id, chapter_number) 升序取全部 chunk
  （供测试断言 + 5.6 召回读用）。

**与 chapter_card_repo「一章一行 upsert」的区别**：embedding 一章多行、chunk 数可能随
正文变化，故用「先删后插」（delete_by_chapter → bulk_insert）而非 get-or-create upsert。
"""

import uuid
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.embedding import Embedding


async def delete_by_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> int:
    """删本作品本章的全部旧 chunk 行（重跑投影先删后插保幂等，陷阱④）。返回删除行数。

    租户守卫：user_id + project_id + chapter_number 三列一起过滤，只删自己本章的行。
    **不 commit**（事务边界归 service：与随后的 bulk_insert 同一独立事务）。
    """
    stmt = delete(Embedding).where(
        Embedding.user_id == user_id,
        Embedding.project_id == project_id,
        Embedding.chapter_number == chapter_number,
    )
    result = await session.execute(stmt)
    # rowcount：被删行数（psycopg CursorResult；用于测试断言/日志）。
    return cast(CursorResult, result).rowcount or 0


async def bulk_insert(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chunks: list[tuple[int, str, list[float]]],
    model_name: str,
) -> int:
    """批量插入本章 chunk 行（Story 5.5 投影落点）。返回插入行数。

    chunks：`(chunk_index, content, embedding_vector)` 三元组列表——顺序由 service 组装
    （zip(range(n), chunks_text, vectors)）。空列表直接返 0（不 add）。

    session.add_all + flush（不 refresh——插入行无需回读，减一次往返；同 story_thread_repo
    批量写路径）。**不 commit**（事务边界归 embedding_projection_service 独立事务）。
    """
    if not chunks:
        return 0
    rows = [
        Embedding(
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            chunk_index=chunk_index,
            content=content,
            embedding=vector,
            model_name=model_name,
        )
        for chunk_index, content, vector in chunks
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def list_by_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
) -> list[Embedding]:
    """按 (user_id, project_id, chapter_number) 升序取全部 chunk（chunk_index 升序）。

    供测试断言 + 5.6 召回读用。租户守卫（三列过滤），不泄露其他作品/用户的向量行（NFR3）。
    """
    stmt = (
        select(Embedding)
        .where(
            Embedding.user_id == user_id,
            Embedding.project_id == project_id,
            Embedding.chapter_number == chapter_number,
        )
        .order_by(Embedding.chunk_index.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
