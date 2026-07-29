"""探索域 DAO：story_clue 的增删改查（Story 2.6）。

延续 exploration_repo/project_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service。所有查询显式绑定 user_id 租户守卫（base_repo 约定，NFR3）——不提供任何绕过
user_id 的全表查询入口。
"""

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.story_clue import StoryClue


async def list_clues_by_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[StoryClue]:
    """列出该会话全部线索（预设槙位 + 自定义），按 display_order 升序（AC3/AC6）。"""
    stmt = (
        select(StoryClue)
        .where(
            StoryClue.user_id == user_id,
            StoryClue.project_id == project_id,
            StoryClue.session_id == session_id,
        )
        .order_by(StoryClue.display_order.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_clue_by_id(
    session: AsyncSession,
    clue_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> StoryClue | None:
    """按 id + user_id + project_id 一步取本人线索（二义合一，仿 get_owned_project 范式）。

    取不到即 None，「线索不存在」与「线索不属于我」二义合一——调用方统一转 404，消除 IDOR
    侦察面。
    """
    stmt = select(StoryClue).where(
        StoryClue.id == clue_id,
        StoryClue.user_id == user_id,
        StoryClue.project_id == project_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def seed_preset_clues(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    presets: list[tuple[str, str]],
) -> None:
    """播种预设线索槙位（进入自由探索首次建会话时，AC3）：presets 为 [(clue_key, label), ...]。

    只 add 不 flush/commit——调用方（exploration_service.enter_exploration）在同一事务内随
    会话一并 commit。display_order 按 presets 列表顺序取 0..N-1。
    """
    for index, (clue_key, label) in enumerate(presets):
        session.add(
            StoryClue(
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
                kind="preset",
                clue_key=clue_key,
                label=label,
                value="",
                user_edited=False,
                display_order=index,
            )
        )


async def create_custom_clue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    label: str,
    value: str,
) -> StoryClue:
    """新增自定义线索（AC3）：display_order 取本会话现有最大值 +1（单用户场景无并发竞态）。"""
    stmt = select(func.max(StoryClue.display_order)).where(
        StoryClue.session_id == session_id
    )
    result = await session.execute(stmt)
    max_order = result.scalar_one_or_none()
    next_order = (max_order + 1) if max_order is not None else 0

    clue = StoryClue(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        kind="custom",
        clue_key=None,
        label=label,
        value=value,
        user_edited=False,
        display_order=next_order,
    )
    session.add(clue)
    await session.flush()
    return clue


async def update_clue(
    session: AsyncSession,
    clue: StoryClue,
    *,
    value: str,
    label: str | None = None,
) -> StoryClue:
    """用户编辑线索（AC3/AC5）：置 user_edited=true（写入侧的核心约束）。

    updated_at 走列级 onupdate=func.now()——flush 时 SQLAlchemy 把该属性标记为 expired
    等待再次访问时重查，若下游是同步上下文（如 pydantic model_validate 序列化响应）触发
    懒加载则抛 MissingGreenlet。故 flush 后**立即 async refresh** 把 updated_at 从 DB 回填
    到对象上，让 ORM 属性访问不再触发 IO。update_clue_value（Agent 整理路径）同款处理。
    """
    clue.value = value
    if label is not None:
        clue.label = label
    clue.user_edited = True
    await session.flush()
    await session.refresh(clue)
    return clue


async def update_clue_value(
    session: AsyncSession, *, clue: StoryClue, value: str
) -> bool:
    """Agent 整理线索更新 value（AC5）：**条件 UPDATE，仅当 user_edited=false 才写入**。

    与 update_clue（用户编辑路径）语义不同：本函数不改 user_edited（保持 false，仍可被后续
    整理继续覆盖，直到用户真正手动编辑一次），故独立成函数避免误用同一函数导致两条写入路径混淆。

    **条件 WHERE user_edited=false（AC5 竞态防护，2026-07-29 code review 裁定）**：extract_clues
    先读 pending 快照（user_edited=false）、再调 LLM（秒级），若这期间用户手动 PATCH 了该槙位
    （置 user_edited=true），本 UPDATE 会命中 0 行、跳过——保证"用户编辑优先不被 Agent 覆盖"
    在读-算-写时序下仍成立（否则按旧快照覆盖用户刚写入的内容，AC5 硬承诺失守）。返回是否命中
    （True=已更新，False=被用户编辑抢先、跳过），供调用方据实汇报实际更新的槙位。

    走 Core UPDATE（非 ORM 对象改属性 flush）：条件过滤在 SQL 层原子完成，规避先读 user_edited
    再判断的二次 TOCTOU；传入 clue 仅用于取 id，其 ORM 属性此后可能与库不一致（调用方不复用）。
    """
    stmt = (
        update(StoryClue)
        .where(StoryClue.id == clue.id, StoryClue.user_edited.is_(False))
        .values(value=value, updated_at=func.now())
    )
    result = await session.execute(stmt)
    # CursorResult.rowcount：DML 影响行数（0=被用户编辑抢先跳过，1=已更新）。
    return cast("CursorResult[Any]", result).rowcount > 0


async def delete_custom_clue(session: AsyncSession, clue: StoryClue) -> None:
    """删除自定义线索（AC3）：调用方须先校验 clue.kind == "custom"（service 层判断，本函数
    不做物理限制，职责更清晰）。
    """
    await session.delete(clue)
    await session.flush()
