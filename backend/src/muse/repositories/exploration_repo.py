"""探索域 DAO：exploration_session 的按作品取会话与创建。

命名注意：**不叫 session_repo**——该名已被 auth refresh 会话 DAO 占用
（repositories/session_repo.py），探索会话用 exploration_repo 避免语义撞车。

延续 project_repo/base_repo 约定：repo 只 flush/查询，事务边界（commit/rollback）归
service。所有查询显式绑定 user_id 租户守卫（base_repo 约定，NFR3）——不提供任何绕过
user_id 的全表查询入口。
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.exploration_message import ExplorationMessage
from muse.models.exploration_session import ExplorationSession


async def get_session_by_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession | None:
    """按 user_id + project_id 取该作品的探索会话（get-or-create 的 get 步，NFR3）。

    user_id 与 project_id **写在同一个 where 里一次过滤**（仿 project_repo.get_owned_project
    的「二义合一」范式）：取不到即 None，「会话不存在」与「作品不属于我」不产生分支差异。
    (user_id, project_id) 复合唯一（见模型 __table_args__）保证至多一条。
    """
    stmt = select(ExplorationSession).where(
        ExplorationSession.user_id == user_id,
        ExplorationSession.project_id == project_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_session(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, mode: str
) -> ExplorationSession:
    """新建探索会话并 flush（拿应用侧生成的 UUID id）；是否提交由 service 决定。

    mode 由 service 传入 project.mode（AC2 单一事实源，非客户端）。
    """
    exploration_session = ExplorationSession(
        user_id=user_id, project_id=project_id, mode=mode
    )
    session.add(exploration_session)
    await session.flush()
    return exploration_session


async def upsert_guided_answer(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    question_index: int,
    question: str,
    answer: str,
    answer_type: str,
) -> ExplorationMessage:
    """定点写某题位答案：不存在则插入，撞 (session_id, question_index) 唯一约束则覆盖（AC4/AC5）。

    PG 原生 upsert（on_conflict_do_update）：一次往返、并发安全（仿 2.2 用唯一约束兜底并发
    TOCTOU 的精神，且比「先查后写」少一次往返）。用 RETURNING 一并取回写入行（无需再 flush 或
    额外 SELECT），事务边界（commit）归 service。

    陷阱②（updated_at 不刷新）：on_conflict_do_update 走 core insert 路径，SQLAlchemy 列级
    onupdate=func.now()（base.py:26）**不触发**——set_ 里必须显式 updated_at=func.now()，否则
    重选覆盖后 updated_at 停在首答时间，违反 updated_at=内容最后修改时间（改答即刷新）。
    陷阱③（created_at 不可覆盖）：set_ 只更 answer/answer_type/question/updated_at，不含
    created_at（保留首答时间）；values(...) 含全部列供插入分支，set_ 只列更新分支要改的列。
    """
    insert_stmt = insert(ExplorationMessage).values(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        question_index=question_index,
        question=question,
        answer=answer,
        answer_type=answer_type,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint="uq_exploration_message_session_id_question_index",
        set_={
            "question": insert_stmt.excluded.question,
            "answer": insert_stmt.excluded.answer,
            "answer_type": insert_stmt.excluded.answer_type,
            "updated_at": func.now(),
        },
    ).returning(ExplorationMessage)
    result = await session.execute(upsert_stmt)
    return result.scalar_one()


async def list_guided_answers_by_session(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[ExplorationMessage]:
    """列出该会话全部答案，按 question_index 升序（前端按题位顺序回填 explorationHistory）。

    where 显式带 user_id（租户守卫，base_repo 约定 NFR3，勿只按 session_id 查）——session_id
    已足够定位，但守卫列必带 user_id 是硬红线（architecture.md:357）。
    """
    stmt = (
        select(ExplorationMessage)
        .where(
            ExplorationMessage.user_id == user_id,
            ExplorationMessage.project_id == project_id,
            ExplorationMessage.session_id == session_id,
        )
        .order_by(ExplorationMessage.question_index.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
