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

# 段名常量（= run.steps 的键、= worker 推 progress 的段序）。V1 四段，V2 补 data-agent。
STEP_CONTEXT = "context"
STEP_DRAFTER = "drafter"
STEP_REVIEWER = "reviewer"
STEP_POLISHER = "polisher"
PIPELINE_STEPS: tuple[str, ...] = (
    STEP_CONTEXT,
    STEP_DRAFTER,
    STEP_REVIEWER,
    STEP_POLISHER,
)


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
) -> str:
    """驱动四段流水线生成一章正文，返回终稿。断点续跑：重入复用已完成段。

    on_progress(step_name)：每段开跑前回调（worker 用它推 SSE progress；装置脚本可传 None）。
    复用的段不回调（已完成、无需再推进度）。

    幂等：同 (user_id, project_id, chapter_number) 重入复用同一 run 行。若 run 已整体
    succeeded，直接返回 polisher 段产物、不重跑。
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
        if run is not None and run.status == "succeeded":
            final = _succeeded_output(run.steps, STEP_POLISHER)
            if final is not None:
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

    # 四段全成 → run 标 succeeded + 终稿正文落业务表 chapter（Story 4.4）。
    # 同一 session 内两件事：mark run succeeded（编排状态源）+ upsert 正文（业务正文源，供阅读/
    # 恢复/前序注入）。upsert 幂等——ARQ 重试/重入复用 succeeded run 再次落库时覆盖同行、不产生
    # 正文副本（chapter 表 (user_id, project_id, chapter_number) 复合唯一）。分层见
    # chapter_generation.py:1-9（编排状态表 vs 业务表）。
    async with async_session_maker() as session:
        run = await run_repo.get_run(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
        )
        if run is not None:
            await run_repo.mark_run_status(session, run=run, status="succeeded")
        await chapter_repo.upsert_chapter(
            session,
            user_id=user_id,
            project_id=project_id,
            chapter_number=chapter_number,
            text=final,
        )
        await session.commit()
    return final
