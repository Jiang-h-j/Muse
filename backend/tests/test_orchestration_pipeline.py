"""Story 4.2 Task 4 验证：章节生成编排器（断点续跑，离线 mock 四段 + run 表）。

覆盖：
- 全新跑：四段按序调用、产物链式传递、run 标 succeeded、返回终稿
- 断点续跑：context/drafter 已 succeeded → 跳过（不再调），从 reviewer 续跑
- 已整体成功：run.status=succeeded → 直接返回 polisher 产物，一段都不跑
- 某段失败：runner 抛异常 → run 标 failed、异常冒泡
- on_progress：每段开跑前回调；复用段不回调

用 mock 的 run 表（内存 dict 模拟 steps 状态）+ mock 四段 step 函数，纯离线。
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from muse.core.errors import ErrorEnvelope
from muse.orchestration import pipeline

_UID = uuid.uuid4()
_PID = uuid.uuid4()


class _FakeRun:
    """内存 run 行：steps dict + status，模拟 chapter_generation_run。"""

    def __init__(self, steps: dict | None = None, status: str = "running") -> None:
        self.steps = steps
        self.status = status
        self.chapter_idea = None


class _FakeSessionCtx:
    async def __aenter__(self) -> object:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _patch_pipeline(
    *,
    run: _FakeRun,
    context_ret: str = "写作任务书",
    drafter_ret: str = "初稿",
    reviewer_ret: str = "审查意见",
    polisher_ret: str = "终稿",
    step_side_effects: dict | None = None,
) -> tuple[ExitStack, dict]:
    """patch 编排器的 run 表 CRUD + 四段 step。返回 (stack, mocks)。

    run 表用同一个 _FakeRun 实例；update_step 原地改其 steps（模拟落库），mark_run_status
    改 status。四段 step 用 AsyncMock 记录调用。
    """
    stack = ExitStack()
    mocks: dict = {}

    stack.enter_context(
        patch.object(pipeline, "async_session_maker", lambda: _FakeSessionCtx())
    )

    async def _get_run(session, **kw):
        return run

    async def _create_run(session, **kw):
        run.chapter_idea = kw.get("chapter_idea")
        return run

    async def _update_step(session, *, run, step_name, status, output):
        steps = dict(run.steps) if run.steps else {}
        steps[step_name] = {"status": status, "output": output}
        run.steps = steps
        return run

    async def _mark(session, *, run, status):
        run.status = status
        return run

    stack.enter_context(
        patch.object(pipeline.run_repo, "get_run", AsyncMock(side_effect=_get_run))
    )
    stack.enter_context(
        patch.object(pipeline.run_repo, "create_run", AsyncMock(side_effect=_create_run))
    )
    stack.enter_context(
        patch.object(
            pipeline.run_repo, "update_step", AsyncMock(side_effect=_update_step)
        )
    )
    stack.enter_context(
        patch.object(pipeline.run_repo, "mark_run_status", AsyncMock(side_effect=_mark))
    )

    # Story 4.4：pipeline tail 把终稿 upsert 到 chapter 业务表。离线 mock 记录调用供断言。
    upsert_mock = AsyncMock(return_value=_FakeRun())
    stack.enter_context(
        patch.object(pipeline.chapter_repo, "upsert_chapter", upsert_mock)
    )
    mocks["upsert_chapter"] = upsert_mock

    se = step_side_effects or {}
    ctx_mock = AsyncMock(
        return_value=context_ret, side_effect=se.get("context")
    )
    draft_mock = AsyncMock(return_value=drafter_ret, side_effect=se.get("drafter"))
    review_mock = AsyncMock(return_value=reviewer_ret, side_effect=se.get("reviewer"))
    polish_mock = AsyncMock(return_value=polisher_ret, side_effect=se.get("polisher"))
    stack.enter_context(patch.object(pipeline.steps, "run_context_agent", ctx_mock))
    stack.enter_context(patch.object(pipeline.steps, "run_drafter", draft_mock))
    stack.enter_context(patch.object(pipeline.steps, "run_reviewer", review_mock))
    stack.enter_context(patch.object(pipeline.steps, "run_polisher", polish_mock))
    mocks.update(
        context=ctx_mock, drafter=draft_mock, reviewer=review_mock, polisher=polish_mock
    )
    return stack, mocks


@pytest.mark.asyncio
async def test_full_run_calls_all_four_and_chains() -> None:
    run = _FakeRun()
    stack, mocks = _patch_pipeline(run=run)
    with stack:
        final = await pipeline.run_chapter_pipeline(
            user_id=_UID, project_id=_PID, chapter_number=1, chapter_idea="想法X"
        )
    assert final == "终稿"
    mocks["context"].assert_awaited_once()
    mocks["drafter"].assert_awaited_once()
    mocks["reviewer"].assert_awaited_once()
    mocks["polisher"].assert_awaited_once()
    # 产物链式传递：drafter 收到 context 产物、reviewer 收到 draft、polisher 收到 draft+notes。
    assert mocks["drafter"].call_args.kwargs["writing_brief"] == "写作任务书"
    assert mocks["reviewer"].call_args.kwargs["draft"] == "初稿"
    assert mocks["polisher"].call_args.kwargs["draft"] == "初稿"
    assert mocks["polisher"].call_args.kwargs["review_notes"] == "审查意见"
    assert run.status == "succeeded"
    # Story 4.4：终稿落 chapter 业务表（tail upsert）。
    mocks["upsert_chapter"].assert_awaited_once()
    assert mocks["upsert_chapter"].call_args.kwargs["text"] == "终稿"
    assert mocks["upsert_chapter"].call_args.kwargs["chapter_number"] == 1


@pytest.mark.asyncio
async def test_resume_skips_succeeded_steps() -> None:
    # context/drafter 已 succeeded → 跳过，从 reviewer 续跑。
    run = _FakeRun(
        steps={
            "context": {"status": "succeeded", "output": "缓存的任务书"},
            "drafter": {"status": "succeeded", "output": "缓存的初稿"},
        }
    )
    stack, mocks = _patch_pipeline(run=run)
    with stack:
        final = await pipeline.run_chapter_pipeline(
            user_id=_UID, project_id=_PID, chapter_number=1
        )
    assert final == "终稿"
    mocks["context"].assert_not_awaited()  # 复用、不跑
    mocks["drafter"].assert_not_awaited()
    mocks["reviewer"].assert_awaited_once()
    mocks["polisher"].assert_awaited_once()
    # reviewer 收到的是缓存的 drafter 产物。
    assert mocks["reviewer"].call_args.kwargs["draft"] == "缓存的初稿"


@pytest.mark.asyncio
async def test_already_succeeded_short_circuits() -> None:
    run = _FakeRun(
        steps={"polisher": {"status": "succeeded", "output": "已完成的终稿"}},
        status="succeeded",
    )
    stack, mocks = _patch_pipeline(run=run)
    with stack:
        final = await pipeline.run_chapter_pipeline(
            user_id=_UID, project_id=_PID, chapter_number=1
        )
    assert final == "已完成的终稿"
    # 一段都不跑。
    for name in ("context", "drafter", "reviewer", "polisher"):
        mocks[name].assert_not_awaited()


@pytest.mark.asyncio
async def test_step_failure_marks_run_failed_and_reraises() -> None:
    run = _FakeRun()
    stack, mocks = _patch_pipeline(
        run=run,
        step_side_effects={"drafter": RuntimeError("provider 挂了")},
    )
    with stack:
        with pytest.raises(RuntimeError, match="provider 挂了"):
            await pipeline.run_chapter_pipeline(
                user_id=_UID, project_id=_PID, chapter_number=1
            )
    assert run.status == "failed"
    # context 已成功落库、drafter 失败落 failed、后两段没跑。
    assert run.steps["context"]["status"] == "succeeded"
    assert run.steps["drafter"]["status"] == "failed"
    mocks["reviewer"].assert_not_awaited()
    mocks["polisher"].assert_not_awaited()


@pytest.mark.asyncio
async def test_error_envelope_propagates() -> None:
    """step 抛 ErrorEnvelope（如 bible_not_confirmed 400）同样冒泡、run 标 failed。"""
    run = _FakeRun()
    err = ErrorEnvelope(code="bible_not_confirmed", message="先确认设定", http_status=400)
    stack, _ = _patch_pipeline(run=run, step_side_effects={"context": err})
    with stack:
        with pytest.raises(ErrorEnvelope) as ei:
            await pipeline.run_chapter_pipeline(
                user_id=_UID, project_id=_PID, chapter_number=1
            )
    assert ei.value.code == "bible_not_confirmed"
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_on_progress_called_after_each_step_success() -> None:
    """progress 在每段成功后推（含复用段）——表达「第 N 段已完成」，polisher 跑完才推。"""
    run = _FakeRun(
        steps={"context": {"status": "succeeded", "output": "缓存任务书"}}
    )
    seen: list[str] = []

    async def _progress(step_name: str) -> None:
        seen.append(step_name)

    stack, _ = _patch_pipeline(run=run)
    with stack:
        await pipeline.run_chapter_pipeline(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            on_progress=_progress,
        )
    # 四段都推（context 复用即已成功、也推；其余三段跑完各推）。
    assert seen == ["context", "drafter", "reviewer", "polisher"]


@pytest.mark.asyncio
async def test_on_progress_failure_does_not_interrupt_pipeline() -> None:
    """on_progress 异常（如 Redis 断）不中断生成——旁路容错（patch 修复）。"""
    run = _FakeRun()

    async def _broken_progress(step_name: str) -> None:
        raise RuntimeError("Redis 连接断开")

    stack, mocks = _patch_pipeline(run=run)
    with stack:
        final = await pipeline.run_chapter_pipeline(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            on_progress=_broken_progress,
        )
    # progress 抛错被吞，四段仍跑完、返回终稿。
    assert final == "终稿"
    mocks["polisher"].assert_awaited_once()
