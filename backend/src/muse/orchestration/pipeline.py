"""章节生成编排器（Story 4.2，AR11）：串四段 step + 断点续跑。

`run_chapter_pipeline` 按序驱动 context→drafter→reviewer→polisher 四段，用
chapter_generation_run 表持久化各段状态与产物，实现 AR11「每 step 幂等可重入、状态落 PG、
天然断点续跑」：

- 幂等键 (user_id, project_id, chapter_number)：同章重入复用同一 run 行。
- 断点续跑：每段前查 run.steps——该段已 succeeded 则跳过、直接用其落库 output 喂下一段；
  否则跑该段、成功即写 output 落库。某段失败（抛异常）→ run 标 failed 并冒泡，重入时从该
  失败段续跑（前面 succeeded 段不重跑，不重复付费 NFR5）。
- 全四段完成 → run 标 succeeded，返回终稿正文。

**session 分工**：编排器用一个 session 读写 run 表（纯 CRUD、不调 provider）；四段 step
各自管独立 session（调 provider 走 MeteredProvider 记账，陷阱⑩）——故编排器不把 session 传
给 step。run 表的 CRUD 与各段 LLM 调用是独立事务，符合「每段落库即持久化」的断点语义。

**范围（AC6）**：本 story 编排器接受 chapter_idea 并透传给 context-agent，但不接用户可见
POST 入口（归 4.4）。返回终稿正文，由 worker（Task 5）经 SSE 推给前端 / 由装置脚本打印。
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import IntegrityError

from muse.core.db import async_session_maker
from muse.orchestration import steps
from muse.repositories import chapter_generation_repo as run_repo
from muse.repositories import chapter_repo

logger = logging.getLogger("muse")

# 段名常量（= run.steps 的键、= worker 推 progress 的段序）。
# Story 4.2 V1 四段（context/drafter/reviewer/polisher）是「生成/修订」核心段；
# Story 5.2 追加第五段 data_agent（写后投影，只在定稿时跑——受控决策 1）。
# 两个常量分开：
# - PIPELINE_CORE_STEPS：生成/修订路径（generate/revise）固定跑的 4 段，progress 按 4 推 100%。
# - STEP_DATA_AGENT：定稿路径（finalize_and_project_chapter）追加的可选段。
# worker._CHAPTER_TOTAL_STEPS 派生用 PIPELINE_CORE_STEPS（4）——generate/revise 完成时
# 仍推 100%；finalize 路径同步等 data-agent 跑完不走 SSE，无 progress 推送。
STEP_CONTEXT = "context"
STEP_DRAFTER = "drafter"
STEP_REVIEWER = "reviewer"
STEP_POLISHER = "polisher"
STEP_DATA_AGENT = "data_agent"
PIPELINE_CORE_STEPS: tuple[str, ...] = (
    STEP_CONTEXT,
    STEP_DRAFTER,
    STEP_REVIEWER,
    STEP_POLISHER,
)
# 兼容别名：worker._CHAPTER_STEP_ORDER/_CHAPTER_TOTAL_STEPS 派生仍用 PIPELINE_STEPS 名字
# ——但语义已收窄为「生成/修订核心段」（4 段），data_agent 不在其内。故 generate/revise
# 路径 progress 仍按 4 段推 100%，不被 data_agent 拖累。
PIPELINE_STEPS: tuple[str, ...] = PIPELINE_CORE_STEPS


def _succeeded_output(steps_state: dict | None, step_name: str) -> str | None:
    """若某段已 succeeded，返回其落库 output（断点续跑复用）；否则 None（需跑该段）。"""
    if not steps_state:
        return None
    entry = steps_state.get(step_name)
    if entry and entry.get("status") == "succeeded":
        return entry.get("output")
    return None


async def _run_or_resume(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    step_name: str,
    runner: Callable[[], Awaitable[str]],
    on_progress: Callable[[str], Awaitable[None]] | None,
) -> str:
    """执行一段：若 run 表里该段已 succeeded 则复用产物，否则跑 runner 并落库。

    每段独立一个 run 表 session（读当前 steps → 判断 → 跑 → 写 output）。runner 抛异常时
    把该段标 failed 落库后冒泡（重入从此段续跑）。返回该段产物 output。

    **progress 语义**：`on_progress(step_name)` 在该段**成功落库后**调用（含复用段——复用即已
    成功），表达「第 N 段已完成」。故 percent=step_no/total 是真实完成比例，polisher 跑完才
    100%，不会出现「最长一段开跑前就显示 100%」。on_progress 异常（如 Redis 断、SSE 发布失败）
    **不中断生成**——进度推送是旁路、正文生成才是主路径，故单独捕获只记日志（patch 修复）。
    """
    # 1. 读当前 run 状态判断是否可复用。
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        cached = _succeeded_output(run.steps if run else None, step_name)
    if cached is not None:
        logger.info(
            "pipeline 复用已完成段：chapter=%s step=%s", chapter_number, step_name
        )
        await _safe_on_progress(on_progress, step_name, chapter_number)
        return cached

    # 2. 跑该段（step 自管独立 session 调 provider）。异常 → 标 failed 落库后冒泡。
    # on_progress 不在此推（见上方语义：成功后才推）。
    try:
        output = await runner()
    except Exception:
        async with async_session_maker() as session:
            run = await run_repo.get_run(
                session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
            )
            if run is not None:
                await run_repo.update_step(
                    session, run=run, step_name=step_name, status="failed", output=""
                )
                await run_repo.mark_run_status(session, run=run, status="failed")
                await session.commit()
        raise

    # 3. 落库该段产物（succeeded）供断点续跑。
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        if run is not None:
            await run_repo.update_step(
                session,
                run=run,
                step_name=step_name,
                status="succeeded",
                output=output,
            )
            await session.commit()
    await _safe_on_progress(on_progress, step_name, chapter_number)
    return output


async def _safe_on_progress(
    on_progress: Callable[[str], Awaitable[None]] | None,
    step_name: str,
    chapter_number: int,
) -> None:
    """推一次 progress，吞掉其异常——进度推送是旁路，不应中断正文生成（patch 修复）。

    on_progress 失败（如 Redis 断、SSE 发布失败）只记日志：worker 据终态 result/error 仍能给
    前端结论；丢一两条 progress 事件比「整章因 Redis 抖动失败」可接受得多。
    """
    if on_progress is None:
        return
    try:
        await on_progress(step_name)
    except Exception:  # noqa: BLE001  旁路容错：进度发布失败不中断主路径
        logger.warning(
            "pipeline progress 推送失败（已忽略，不中断生成）：chapter=%s step=%s",
            chapter_number,
            step_name,
            exc_info=True,
        )


async def run_chapter_pipeline(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    chapter_number: int,
    chapter_idea: str | None = None,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
    revision_input: dict | None = None,
    target_revision: int = 1,
    run_data_agent_step: bool = False,
) -> str:
    """驱动流水线生成一章正文，返回终稿。断点续跑：重入复用已完成段。

    on_progress(step_name)：每段开跑前回调（worker 用它推 SSE progress；装置脚本可传 None）。
    复用的段不回调（已完成、无需再推进度）。

    幂等：同 (user_id, project_id, chapter_number) 重入复用同一 run 行。若 run 已整体
    succeeded，直接返回 polisher 段产物、不重跑。

    **Story 4.6 修订模式**：`revision_input`（含 action/feedback/annotations/previous_text）非
    None 时为「改进/重生」——调用方（chapter_service）已先 reset_run（清 steps + status→running），
    故此处 run 不会命中「已 succeeded 早返回」分支，正常重跑全四段；`revision_input` 透传给
    context-agent 拼进写作任务书（改进注入旧正文+点评+批注作保留基础、重生注入方向）。
    `target_revision` 为落库版本号（改进/重生 = 旧 revision+1；4.4 首次生成 = 1）。
    `revision_input=None` 时行为与 4.4 完全一致（向后兼容）。

    **Story 5.2 第五段 data_agent**：`run_data_agent_step=True` 时在 polisher 段之后追加
    data-agent 段（写后投影，从定稿正文提取结构化 JSON 落 run 表 steps）。**默认 False**
    ——generate_chapter/revise_chapter 走 ARQ 的「生成/修订」路径**不跑** data-agent（受控
    决策 1：未定稿不污染归档）；只有 chapter_service.finalize_and_project_chapter 在「用户
    显式点定稿」时传 True 才跑。data-agent 段产物（dict）落 run.steps.data_agent 供断点续
    跑复用；函数返回值仍是 str（章节正文），投影产物由 chapter_projection_service 从 run
    表读出。
    """
    # get-or-create run 行（首次开跑建行；已存在复用）。竞态兜底：并发首建撞唯一约束
    # → rollback 重查（照 story_settle_agent._persist_card_with_race_guard 先例）。
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        if run is None:
            try:
                run = await run_repo.create_run(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_idea=chapter_idea,
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                run = await run_repo.get_run(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                )
        # 已整体成功 → 直接返回终稿（polisher 段产物），不重跑。
        # **Story 5.2 例外**：`run_data_agent_step=True` 时若 data_agent 段未 succeeded（如
        # 第一遍 generate 只跑了四段、定稿时才来跑 data_agent），**不早返回**——继续走下方
        # `_run_or_resume`，让 data_agent 段跑起来（其他四段因 cached 命中自动复用产物、不
        # 重复付费 NFR5）。
        if run is not None and run.status == "succeeded":
            data_agent_needed = run_data_agent_step and (
                _succeeded_output(run.steps, STEP_DATA_AGENT) is None
            )
            final = _succeeded_output(run.steps, STEP_POLISHER)
            if final is not None and not data_agent_needed:
                # 早返回也确保 chapter 业务表有行（get-or-upsert 幂等）：run 表 succeeded 与 chapter
                # 表可能脱节——chapter 表是 4.4 才建，4.2/4.3 联调/迁移期产生的 succeeded run 没有
                # 对应 chapter 行；若此处只 return final 不补写，则 GET /chapters/{n} 恒 204、
                # list_recent_chapters 读不到该章（前序注入缺失、多章连续性断裂）。upsert 幂等：已有
                # 行则覆盖同内容、无副作用。
                await chapter_repo.upsert_chapter(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    text=final,
                )
                await session.commit()
                return final
            # run 标 succeeded 但 polisher 段 output 缺失 → 数据损坏（脏数据/迁移残留）。
            # 显式告警并把状态重置为 running，让下方正常续跑（而非静默 fall through 重跑全流程）。
            logger.warning(
                "pipeline run 标 succeeded 但 polisher 段 output 缺失，视为损坏重置："
                "chapter=%s",
                chapter_number,
            )
            await run_repo.mark_run_status(session, run=run, status="running")
            await session.commit()
        # 复用建行时落库的 chapter_idea（保证重入产出一致），忽略本次可能不同的传参。
        effective_idea = run.chapter_idea if run is not None else chapter_idea

    # context-agent（纯组装、不调 LLM，但仍作为一段推 progress——让前端看到四段推进）。
    writing_brief = await _run_or_resume(
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        step_name=STEP_CONTEXT,
        runner=lambda: steps.run_context_agent(
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_idea=effective_idea,
            revision_input=revision_input,
        ),
        on_progress=on_progress,
    )

    # drafter：起草初稿。
    draft = await _run_or_resume(
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        step_name=STEP_DRAFTER,
        runner=lambda: steps.run_drafter(
            user_id=user_id, project_id=project_id, writing_brief=writing_brief
        ),
        on_progress=on_progress,
    )

    # reviewer：审查意见。
    review_notes = await _run_or_resume(
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        step_name=STEP_REVIEWER,
        runner=lambda: steps.run_reviewer(
            user_id=user_id,
            project_id=project_id,
            writing_brief=writing_brief,
            draft=draft,
        ),
        on_progress=on_progress,
    )

    # polisher：去 AI 味终稿。
    final = await _run_or_resume(
        user_id=user_id,
        project_id=project_id,
        chapter_number=chapter_number,
        step_name=STEP_POLISHER,
        runner=lambda: steps.run_polisher(
            user_id=user_id,
            project_id=project_id,
            draft=draft,
            review_notes=review_notes,
        ),
        on_progress=on_progress,
    )

    # Story 5.2 第五段 data_agent（写后投影，AR17）：只在「定稿」时跑（受控决策 1）。
    # 输入：polisher 段产物 `final`（定稿正文）+ confirmed 设定；输出：结构化 JSON dict 落
    # run.steps.data_agent 供断点续跑复用——重试不重复调 LLM（NFR5）。产物由
    # chapter_projection_service 从 run 表读出、单事务投影回 story_state/chapter_card/
    # story_thread（不在此 step 内投影——保持「step 只做 LLM 提取、service 只做 DB 投影」
    # 分层）。
    if run_data_agent_step:
        await _run_or_resume(
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            step_name=STEP_DATA_AGENT,
            runner=lambda: steps.run_data_agent(
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_text=final,
            ),
            on_progress=on_progress,
        )

    # 四段全成 → run 标 succeeded + 终稿正文落业务表 chapter（Story 4.4）。
    # 同一 session 内两件事：mark run succeeded（编排状态源）+ upsert 正文（业务正文源，供阅读/
    # 恢复/前序注入）。upsert 幂等——ARQ 重试/重入复用 succeeded run 再次落库时覆盖同行、不产生
    # 正文副本（chapter 表 (user_id, project_id, chapter_number) 复合唯一）。分层见
    # chapter_generation.py:1-9（编排状态表 vs 业务表）。
    # **Story 4.6**：target_revision 落业务表版本列——改进/重生 = 旧 revision+1、4.4 首次 = 1；
    # status 恒 "draft"（改进/重生后仍未定稿，定稿是 4.7 才置 finalized）。
    # **Story 5.2**：`run_data_agent_step=True`（finalize 路径）时**跳过此 upsert**——
    # chapter 行已在 chapter_service.finalize_chapter 中 upsert 为 status="finalized" + 保留
    # 原 revision；此处若再 upsert 会用默认 status="draft" + revision=target_revision=1 覆盖，
    # 把定稿状态改回 draft、版本号回退（Edge Case Hunter 发现的严重 bug）。finalize 路径只需
    # 跑 data_agent 段 + 投影，不需再动 chapter 行。
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        if run is not None:
            await run_repo.mark_run_status(session, run=run, status="succeeded")
        if not run_data_agent_step:
            # 非 finalize 路径（generate/revise）：正常 upsert chapter 行（status=draft）。
            await chapter_repo.upsert_chapter(
                session,
                user_id=user_id,
                project_id=project_id,
                chapter_number=chapter_number,
                text=final,
                revision=target_revision,
            )
        await session.commit()
    return final
