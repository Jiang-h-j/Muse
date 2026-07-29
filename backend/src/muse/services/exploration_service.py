"""探索业务编排（AR2：业务在 service，不在 router）。

enter_exploration 是「进入探索」的 get-or-create 编排：先校验 project 属当前 user
（越权=不存在，统一 404），已有会话直接返回（AC1 幂等 / AC3 mode 不改写），否则以
project.mode 建会话（AC2 单一事实源）并 commit；若新建会话且 mode=free，同一事务内额外
播种 4 个预设线索槙位（Story 2.6 AC3）。

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
from muse.models.project import Project
from muse.models.story_clue import StoryClue
from muse.repositories import exploration_repo, project_repo, story_clue_repo

# 4 个预设线索槙位：(clue_key, 中文标签)，进入自由探索首次建会话时播种（AC3）。
# 顺序即 display_order 0-3，与 free_explorer_agent.PRESET_CLUE_KEYS 定义一致（勿改动顺序，
# 两处各自维护但语义须对齐——见 Dev Agent Record 说明本 story 在何处保证一致）。
_PRESET_CLUES: list[tuple[str, str]] = [
    ("opening", "最初的念头"),
    ("protagonist", "主角"),
    ("conflict", "核心冲突"),
    ("world", "世界与氛围"),
]


def _exploration_not_found() -> ErrorEnvelope:
    # 复用 project 的 404 语义（探索挂在 project 下，作品不存在即探索不存在，不新造 code）。
    # 越权与不存在共用同一 404（陷阱①）：不区分「不属于我」与「不存在」、不返回 403，
    # 不泄露 project_id 是否真实存在（消除 IDOR 侦察面，NFR3）。
    return ErrorEnvelope(
        code="project_not_found",
        message="作品不存在。",
        http_status=404,
    )


def _require_project_mode(project: Project, expected_mode: str) -> None:
    """mode 边界守卫（AC7，2.4 code review defer 至本 story 定档）。

    guided/free 两模式端点互相串门时拦下：project 确实存在、确实属于我，只是这个操作
    与当前探索模式不匹配——是「模式不匹配」的领域事实，不是「不存在/不属于我」，故不复用
    404 二义合一（那是租户/存在性语义），改用 409（幂等性冲突语义，仿 REST 惯例）。

    直接查 `project.mode`（单一事实源，2.2 AC2/AC3 建后不可改写）而非 `exploration_session.mode`
    ——省一次查询，也规避「会话尚未创建时如何判断 mode」的假问题；调用方已持有 `get_owned_project`
    查出的 project，本函数零额外 IO。
    """
    if project.mode != expected_mode:
        raise ErrorEnvelope(
            code="mode_mismatch",
            message="该操作与当前探索模式不匹配。",
            http_status=409,
        )


def _require_not_settled(project: Project) -> None:
    """确认后不可重新整理守卫（Story 3.5 code review High-1 修复，选项 1）。

    确认设定后 project.phase 推进到 chapter（story_settle_agent.confirm_profile_card），设定圣经
    成 status='confirmed' 的只读依据（AC2）。但 settle 触发端点（trigger_*_settle）只校验 mode、
    upsert_profile_card 又不带 status 过滤——若确认后重发 settle（前端 bug / 重放 / 双击），会把
    confirmed 行静默覆写回 pending，绕过 AC2 只读保护。此门禁在 mode 守卫后拦下：phase 已离开
    explore（即已确认进入创作）时不允许再整理，抛 409（与 _require_project_mode 同族冲突语义——
    「当前阶段不允许该操作」，非不存在/不属于我）。

    判据是 phase != 'explore'（而非 == 'chapter'）：只有仍在探索/设定阶段才允许触发整理，
    对未来 archive 等阶段同样拦下。
    """
    if project.phase != "explore":
        raise ErrorEnvelope(
            code="already_settled",
            message="故事设定已确认，无法重新整理探索内容。",
            http_status=409,
        )


def _exploration_not_ready() -> ErrorEnvelope:
    """自由探索「整理为故事设定」门禁未满足（2.7 AC4）：本会话尚无用户消息。

    用 400（前置条件未满足）而非 409/404——这既非「模式不匹配」（409）也非「不存在/不属于我」
    （404），而是「对话内容不足、门禁未开放」的前置条件未满足。message 直接复用原型 formingHint
    未开放态文案（prototype/app/app.js:904），保证前端 disabled 态与后端 400 态文案一致。

    这是本 story 相对 2.5 guided settle 的显式差异：2.5 不校验是否有引导答案（受控决策 C），本
    story 因门禁「补足信息才开放」是 user story 核心 benefit（FR10）、且延续 2.6「模式独立在数据
    写入层真正落地不止于前端」的先例，故后端做实门禁（前端 disabled + 后端 400 双防线）。
    """
    return ErrorEnvelope(
        code="exploration_not_ready",
        message="继续和 Agent 讨论，线索足够时就能整理为故事设定。",
        http_status=400,
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
        # 新建会话且 mode=free：同一事务内额外播种 4 个预设线索槙位（AC3）。已存在会话
        # 走上面第 2 步直接 return，不会重复播种（幂等，同 AC1 既有精神）。
        if project.mode == "free":
            await story_clue_repo.seed_preset_clues(
                session,
                user_id=user_id,
                project_id=project_id,
                session_id=created.id,
                presets=_PRESET_CLUES,
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
    2. mode 守卫（AC7）：project.mode 须为 guided，否则 409 mode_mismatch。
    3. get-or-create session（陷阱④）：复用 enter_exploration 幂等编排拿 session_id——作答隐含
       探索已开始，前端即使没先调 enter 也不失败；别自造 get 判空建会话（会漏并发兜底 + mode
       单一事实源）。
    4. upsert 定点写该题位（重选覆盖同题位）→ commit → 返回资源。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "guided")

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
    2. mode 守卫（AC7）：project.mode 须为 guided，否则 409 mode_mismatch。
    3. get session（不 create，陷阱⑨）：无会话（还没进探索/没答过）返回 []（自然空态，非 404）。
    4. 有会话则按题位升序列出。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "guided")

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
    settle_exploration 跑（真实 LLM 12 字段凝练，Story 3.3 已接入；guided 材料=引导答案）。

    1. 租户守卫（陷阱①）：get_owned_project → None 抛 project_not_found 404（二义合一，不 403、
       不区分「不属于我」与「不存在」，消除 IDOR 侦察面 NFR3）。复用 _exploration_not_found()。
    2. mode 守卫（AC7）：project.mode 须为 guided，否则 409 mode_mismatch。
    3. taskId = uuid4 hex（不可枚举，陷阱⑤，与 tasks.py:38 同款）。
    4. register_task_owner **必须在 enqueue_job 之前**（陷阱②，tasks.py:43-47 已论证）：否则
       worker 可能在属主键写入前就发首个事件、SSE 端点鉴权读不到属主而对合法属主误返 404。
    5. ARQ pool 每次 create_pool + aclose（照搬 tasks.py:41-49 spike 范式，应用级复用池待需要
       时再优化）；user_id/project_id 以 str 位置参数传给 worker（任务自己读答案凝练）。

    **不做**（受控决策 B/C）：不 check_quota（skeleton 任务无 LLM 调用、无成本，护栏随 3.3 真实
    凝练落地）、不生成设定卡（Epic 3）、不校验「是否有引导答案」（任务自己读、空答案也能跑管道）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "guided")
    _require_not_settled(project)

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # _job_id=task_id：stable id 作 pubsub 频道键；user_id/project_id 传给 worker 供凝练。
        await pool.enqueue_job(
            "settle_exploration", task_id, uid, pid, _job_id=task_id
        )
    finally:
        await pool.aclose()
    return task_id


async def trigger_free_settle(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> str:
    """自由探索触发「整理为故事设定」ARQ 后台任务（2.7 AC3/AC4）。返回 taskId 供前端连 SSE。

    结构照搬 `trigger_guided_settle`，仅两点差异：① mode 守卫要求 free；② **门禁硬校验**（AC4）
    ——2.5 guided settle 不校验是否有答案（受控决策 C），本 story 因门禁是 user story 核心 benefit
    （FR10「须补足信息才开放」）且延续 2.6「模式独立在数据写入层真正落地」先例，后端做实门禁。

    1. 租户守卫（陷阱①）：get_owned_project → None 抛 project_not_found 404（二义合一，NFR3）。
    2. mode 守卫（AC7）：project.mode 须为 free，否则 409 mode_mismatch。
    3. **门禁硬校验（AC4）**：本会话须至少有 1 条 free 用户消息，否则 400 exploration_not_ready。
       无会话（还没进探索）视为无消息、门禁不通过。门禁在入队前——不满足则不建 Redis 池、不登记
       属主、不入队（越权/不存在先于门禁返 404，不泄露存在性）。
    4. task_id = uuid4 hex（不可枚举，陷阱⑤）。
    5. register_task_owner **必须在 enqueue_job 之前**（陷阱②）：否则 worker 可能在属主键写入前
       发首个事件、SSE 端点鉴权读不到属主而对合法属主误返 404。
    6. **复用 `settle_exploration` 任务**（worker.py，mode-aware，Story 3.3）：任务体调
       story_settle_agent.settle_into_profile，按会话 mode 自取材料——free 会话取对话历史 +
       有效线索（非空 preset 槽 + custom）凝练成 12 字段候选卡（epics.md:715-717「接 2.5/2.7
       的 ARQ 任务」）。guided/free 凝练逻辑共享单任务（YAGNI，不拆两个任务体，受控决策 3）。

    **不做**（受控决策 B/C）：不 check_quota（skeleton 无 LLM 调用、无成本，护栏随 3.3 落地）、
    不生成设定卡（Epic 3）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")
    _require_not_settled(project)

    # 门禁硬校验（AC4）：无会话 → 无消息 → 门禁不通过；有会话则判是否有 free 用户消息。
    exploration_session = await exploration_repo.get_session_by_project(
        session, user_id, project_id
    )
    if exploration_session is None or not await exploration_repo.has_free_user_message(
        session,
        user_id=user_id,
        project_id=project_id,
        session_id=exploration_session.id,
    ):
        raise _exploration_not_ready()

    settings = get_settings()
    task_id = uuid.uuid4().hex
    uid = str(user_id)
    pid = str(project_id)

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        # 先登记属主（SSE 鉴权依据），再入队——顺序保证 SSE 端点总能读到属主（陷阱②）。
        await sse.register_task_owner(pool, task_id, uid)
        # 复用 settle_exploration（mode-aware：free 会话由凝练 service 自取对话+线索，3.3）。
        await pool.enqueue_job(
            "settle_exploration", task_id, uid, pid, _job_id=task_id
        )
    finally:
        await pool.aclose()
    return task_id


async def list_free_messages(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[ExplorationMessage]:
    """列出该作品本会话全部自由对话消息，按创建时间升序（AC6 恢复查询）。get-only，不 create。

    1. 租户守卫（get_owned_project → None 抛 404）。
    2. mode 守卫（AC7）：project.mode 须为 free，否则 409 mode_mismatch。
    3. get session（不 create，同 list_guided_answers 陷阱⑨范式）：无会话返回 []（自然空态）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")

    existing = await exploration_repo.get_session_by_project(session, user_id, project_id)
    if existing is None:
        return []
    return await exploration_repo.list_free_messages_by_session(
        session, user_id=user_id, project_id=project_id, session_id=existing.id
    )


async def list_clues(
    session: AsyncSession, *, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[StoryClue]:
    """列出该作品本会话全部故事线索，按 display_order 升序（AC3/AC6）。get-only，不 create。

    无会话（未进入自由探索）返回 []（自然空态，同 list_free_messages 范式）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")

    existing = await exploration_repo.get_session_by_project(session, user_id, project_id)
    if existing is None:
        return []
    return await story_clue_repo.list_clues_by_session(
        session, user_id=user_id, project_id=project_id, session_id=existing.id
    )


async def create_custom_clue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    label: str,
    value: str,
) -> StoryClue:
    """新增自定义线索（AC3）：未进入自由探索无从新增，写操作先 get-or-create 会话
    （同「先 enter 后写」既有约定，仿 save_guided_answer 对 guided 会话的处理）。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")

    exploration_session = await enter_exploration(
        session, user_id=user_id, project_id=project_id
    )
    clue = await story_clue_repo.create_custom_clue(
        session,
        user_id=user_id,
        project_id=project_id,
        session_id=exploration_session.id,
        label=label,
        value=value,
    )
    await session.commit()
    return clue


async def edit_clue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    clue_id: uuid.UUID,
    value: str,
    label: str | None = None,
) -> StoryClue:
    """编辑线索（AC3/AC5）：置 user_edited=true（写入侧核心约束，保证后续 Agent 整理不覆盖）。

    线索不存在/不属于我 → 复用 _exploration_not_found()（二义合一 404，不新造 code——线索
    本身也挂在 project 下，越权语义与探索资源一致）。

    **preset 的 label 不可改（2026-07-29 code review 裁定）**：preset 槙位的中文标签
    （最初的念头/主角/核心冲突/世界与氛围）是 free_explorer_agent 整理端点组 prompt 的固定
    匹配键（PRESET_CLUE_KEYS）——若允许用户改 preset label，会导致「用户看到的新 label」与
    「整理端点用的旧固定 label」语义分裂。故对 preset 传 label 直接拒绝（400
    preset_label_immutable）；custom 线索 label 可自由改（无匹配键约束）。value 两类均可改。
    """
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")

    clue = await story_clue_repo.get_clue_by_id(
        session, clue_id, user_id=user_id, project_id=project_id
    )
    if clue is None:
        raise _exploration_not_found()
    if label is not None and clue.kind == "preset":
        raise _preset_label_immutable()

    updated = await story_clue_repo.update_clue(session, clue, value=value, label=label)
    await session.commit()
    return updated


def _clue_not_deletable() -> ErrorEnvelope:
    # 预设槙位不可删除（AC3）：线索存在只是不允许这个操作，不用 404（那是存在性语义）。
    return ErrorEnvelope(
        code="clue_not_deletable",
        message="预设线索不可删除。",
        http_status=400,
    )


def _preset_label_immutable() -> ErrorEnvelope:
    # 预设槙位标签不可改（P7）：preset label 是整理端点组 prompt 的固定匹配键，改了会语义分裂。
    # 线索存在、value 可改，只是 label 这个操作不允许——同 _clue_not_deletable 用 400 而非 404。
    return ErrorEnvelope(
        code="preset_label_immutable",
        message="预设线索的名称不可修改。",
        http_status=400,
    )


async def delete_clue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    clue_id: uuid.UUID,
) -> None:
    """删除自定义线索（AC3）：仅限 kind="custom"，preset 尝试删除抛 400 clue_not_deletable。"""
    project = await project_repo.get_owned_project(session, project_id, user_id)
    if project is None:
        raise _exploration_not_found()
    _require_project_mode(project, "free")

    clue = await story_clue_repo.get_clue_by_id(
        session, clue_id, user_id=user_id, project_id=project_id
    )
    if clue is None:
        raise _exploration_not_found()
    if clue.kind != "custom":
        raise _clue_not_deletable()

    await story_clue_repo.delete_custom_clue(session, clue)
    await session.commit()
