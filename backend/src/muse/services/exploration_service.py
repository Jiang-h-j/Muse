"""探索业务编排（AR2：业务在 service，不在 router）。

enter_exploration 是「进入探索」的 get-or-create 编排：先校验 project 属当前 user
（越权=不存在，统一 404），已有会话直接返回（AC1 幂等 / AC3 mode 不改写），否则以
project.mode 建会话（AC2 单一事实源）并 commit。

并发竞态（陷阱②）：两请求同时 miss→双 insert，第二条撞 (user_id, project_id) 唯一约束
IntegrityError；此层 rollback 后重查返回已存在会话——只靠应用层「先查后建」在并发下必漏
（TOCTOU），唯一约束 + 重查是最终防线。

事务边界在此层（repo 只 flush）；业务错误抛 ErrorEnvelope 交全局 handler。
"""

import uuid

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from muse.core import sse
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.models.exploration_message import ExplorationMessage
from muse.models.exploration_session import ExplorationSession
from muse.repositories import exploration_repo, project_repo


def _exploration_not_found() -> ErrorEnvelope:
    # 复用 project 的 404 语义（探索挂在 project 下，作品不存在即探索不存在，不新造 code）。
    # 越权与不存在共用同一 404（陷阱①）：不区分「不属于我」与「不存在」、不返回 403，
    # 不泄露 project_id 是否真实存在（消除 IDOR 侦察面，NFR3）。
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在。",
        http_status=404,
    )


async def enter_exploration(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ExplorationSession:
    """进入探索的 get-or-create 编排（AC1/AC2/AC3/AC5）。返回该作品的探索会话根。"""
    # 1. 先校验 project 属当前 user（防对他人 project 建会话，AC5 陷阱①）。
    #    id+user_id 同一 where「二义合一」，取不到统一 404（越权=不存在）。
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()

    # 2. get：已有会话直接返回（AC1 幂等 / AC3 已存在会话 mode 不改写）。
    existing = await exploration_repo.get_session_by_project(session, user_id, project_id)
    if existing is not None:
        return existing

    # 3. create：mode 取自 project.mode（AC2，非客户端）。并发下第二插入撞唯一约束，
    #    rollback 后重查返回先到者建的会话（陷阱② 最终防线）。
    try:
        created = await exploration_repo.create_session(
            session, user_id=user_id, project_id=project_id, mode=project.mode
        )
        await session.commit()
        return created
    except IntegrityError:
        await session.rollback()
        existing = await exploration_repo.get_session_by_project(
            session, user_id, project_id
        )
        if existing is None:
            # 唯一约束触发却重查不到：状态异常（非预期路径），交全局 handler 兜底 500。
            raise
        return existing


async def save_guided_answer(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    question_index: int,
    question: str,
    answer: str,
    answer_type: str,
) -> ExplorationMessage:
    """保存/更新某题位引导答案（AC5）。纯 CRUD——不调 LLM、不涉护栏、不触发整理态。

    1. 租户守卫（陷阱①）：get_owned_project → None 抛 404 project_not_found（二义合一，不 403）。
    2. get-or-create session（陷阱④）：复用 enter_exploration 幂等编排拿 session_id——作答隐含
       探索已开始，前端即使没先调 enter 也不失败；别自造 get 判空建会话（会漏并发兜底 + mode
       单一事实源）。
    3. upsert 定点写该题位（重选覆盖同题位）→ commit → 返回资源。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()

    exploration_session = await enter_exploration(
        session, user_id=user_id, project_id=project_id
    )
    message = await exploration_repo.upsert_guided_answer(
        session,
        user_id=user_id,
        project_id=project_id,
        session_id=exploration_session.id,
        question_index=question_index,
        question=question,
        answer=answer,
        answer_type=answer_type,
    )
    await session.commit()
    return message


async def list_guided_answers(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[ExplorationMessage]:
    """列出该作品本会话全部已答，按题位升序（AC5 恢复查询）。get-only，不 create。

    1. 租户守卫同上（get_owned_project → None 抛 404）。
    2. get session（不 create，陷阱⑨）：无会话（还没进探索/没答过）返回 []（自然空态，非 404）。
    3. 有会话则按题位升序列出。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()

    existing = await exploration_repo.get_session_by_project(session, user_id, project_id)
    if existing is None:
        return []
    return await exploration_repo.list_guided_answers_by_session(
        session, user_id=user_id, project_id=project_id, session_id=existing.id
    )


async def trigger_guided_settle(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> str:
    """引导收尾触发「整理为故事设定」ARQ 后台任务（AC2）。返回 taskId 供前端连 SSE。

    异步模型二分（epics.md:457）：凝练走 ARQ 后台任务（POST→taskId→GET /events），非交互式
    流式（那是 2.3 interpret）。本函数只「触发」——登记属主 + 入队，任务体在 worker
    settle_guided_exploration 跑（读答案 + 推 progress + 占位 result）。

    1. 租户守卫（陷阱①）：get_owned_project → None 抛 project_not_found 404（二义合一，不 403、
       不区分「不属于我」与「不存在」，消除 IDOR 侦察面 NFR3）。复用 _exploration_not_found()。
    2. taskId = uuid4 hex（不可枚举，陷阱⑤，与 tasks.py:38 同款）。
    3. register_task_owner **必须在 enqueue_job 之前**（陷阱②，tasks.py:43-47 已论证）：否则
       worker 可能在属主键写入前就发首个事件、SSE 端点鉴权读不到属主而对合法属主误返 404。
    4. ARQ pool 每次 create_pool + aclose（照搬 tasks.py:41-49 spike 范式，应用级复用池待需要
       时再优化）；user_id/project_id 以 str 位置参数传给 worker（任务自己读答案凝练）。

    **不做**（受控决策 B/C）：不 check_quota（skeleton 任务无 LLM 调用、无成本，护栏随 3.3 真实
    凝练落地）、不生成设定卡（Epic 3）、不校验「是否有引导答案」（任务自己读、空答案也能跑管道）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # _job_id=task_id：stable id 作 pubsub 频道键；user_id/project_id 传给 worker 供读答案。
        await pool.enqueue_job(
            "settle_guided_exploration", task_id, uid, pid, _job_id=task_id
        )
    finally:
        await pool.aclose()
    return task_id
