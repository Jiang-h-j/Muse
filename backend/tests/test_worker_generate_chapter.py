"""Story 4.2 Task 5 验证：generate_chapter ARQ 任务（离线，mock pipeline + sse.publish_event）。

覆盖：
- happy：调编排器 → 逐段 progress（经 on_progress 回调）→ 末 result（终稿 camelCase）
- ErrorEnvelope（如 bible_not_confirmed 400）→ 透传 code/message 到 error、无 result、重抛
- 泛化异常 → 固定 generate_failed 文案、不外泄细节、重抛
- 任务已注册进 WorkerSettings.functions

mock sse.publish_event 记录事件序列，mock pipeline.run_chapter_pipeline（用 on_progress
回调驱动 progress）——无需 Redis/DB，纯离线。
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from muse.core import sse
from muse.core.errors import ErrorEnvelope
from muse.tasks import worker as worker_mod

_TID = uuid.uuid4().hex
_UID = str(uuid.uuid4())
_PID = str(uuid.uuid4())


def _capture_events() -> tuple[list[tuple[str, dict]], AsyncMock]:
    """返回 (事件列表, mock publish_event)——把每次 publish 的 (event, data) 记进列表。"""
    events: list[tuple[str, dict]] = []

    async def _pub(redis, task_id, event, data):
        events.append((event, data))

    return events, AsyncMock(side_effect=_pub)


@pytest.mark.asyncio
async def test_generate_chapter_happy_progress_then_result() -> None:
    events, pub_mock = _capture_events()

    async def _fake_pipeline(*, on_progress, **kw):
        # 模拟四段依次推进度（复用编排器真实的 on_progress 契约）。
        for name in ("context", "drafter", "reviewer", "polisher"):
            await on_progress(name)
        return "润色后的终稿正文。"

    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.pipeline,
            "run_chapter_pipeline",
            AsyncMock(side_effect=_fake_pipeline),
        ),
    ):
        payload = await worker_mod.generate_chapter(
            {"pub_redis": object()}, _TID, _UID, _PID, 1, "想看雨夜"
        )

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "progress", "progress", "result"]
    # progress 携 step/stepName/percent；末段 100%。
    last_progress = [d for e, d in events if e == "progress"][-1]
    assert last_progress["stepName"] == "polisher"
    assert last_progress["percent"] == 100
    # result 携终稿（camelCase）。
    result = [d for e, d in events if e == "result"][0]
    assert result["taskId"] == _TID
    assert result["status"] == "chapter_ready"
    assert result["chapterNumber"] == 1
    assert result["chapterText"] == "润色后的终稿正文。"
    assert payload["chapterText"] == "润色后的终稿正文。"


@pytest.mark.asyncio
async def test_generate_chapter_error_envelope_passthrough() -> None:
    events, pub_mock = _capture_events()
    err = ErrorEnvelope(
        code="bible_not_confirmed", message="请先确认故事设定", http_status=400
    )
    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.pipeline,
            "run_chapter_pipeline",
            AsyncMock(side_effect=err),
        ),
    ):
        with pytest.raises(ErrorEnvelope):
            await worker_mod.generate_chapter(
                {"pub_redis": object()}, _TID, _UID, _PID, 1
            )
    # 只推 error，透传 code/message，无 result。
    assert [e for e, _ in events] == ["error"]
    err_data = events[0][1]
    assert err_data["code"] == "bible_not_confirmed"
    assert err_data["message"] == "请先确认故事设定"


@pytest.mark.asyncio
async def test_generate_chapter_generic_error_generalized() -> None:
    events, pub_mock = _capture_events()
    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.pipeline,
            "run_chapter_pipeline",
            AsyncMock(side_effect=RuntimeError("DB 连接串泄露风险 xxx")),
        ),
    ):
        with pytest.raises(RuntimeError):
            await worker_mod.generate_chapter(
                {"pub_redis": object()}, _TID, _UID, _PID, 1
            )
    assert [e for e, _ in events] == ["error"]
    err_data = events[0][1]
    assert err_data["code"] == "generate_failed"
    # 固定泛化文案，不外泄内部细节。
    assert "DB 连接串" not in err_data["message"]
    assert err_data["message"] == "生成失败，请稍后重试。"


def test_generate_chapter_registered_in_worker_settings() -> None:
    assert worker_mod.generate_chapter in worker_mod.WorkerSettings.functions
