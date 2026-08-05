"""Story 4.3 Task 3 验证：plan_first_stage ARQ 任务（离线，mock stage_planner + sse）。

覆盖：
- happy：调 stage_planner → progress×3 → 末 result（阶段规划 camelCase：goal + chapters）
- ErrorEnvelope（如 bible_not_confirmed 400）→ 透传 code/message 到 error、无 result、重抛
- 泛化异常 → 固定 generate_failed 文案、不外泄细节、重抛
- 任务已注册进 WorkerSettings.functions

mock sse.publish_event 记录事件序列，mock stage_planner.plan_first_stage——无需 Redis/DB。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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


def _fake_plan(goal: str, chapters: list[dict]) -> MagicMock:
    plan = MagicMock()
    plan.goal = goal
    plan.chapters = chapters
    plan.stage_number = 1
    return plan


@pytest.mark.asyncio
async def test_plan_first_stage_happy_progress_then_result() -> None:
    events, pub_mock = _capture_events()
    chapters = [
        {"title": "废物觉醒", "brief": "觉醒传承。"},
        {"title": "外门试炼", "brief": "遭排挤。"},
    ]
    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.stage_planner,
            "plan_first_stage",
            AsyncMock(return_value=_fake_plan("站稳外门。", chapters)),
        ),
    ):
        payload = await worker_mod.plan_first_stage(
            {"pub_redis": object()}, _TID, _UID, _PID
        )

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "progress", "result"]
    # 末段 progress 100%。
    last_progress = [d for e, d in events if e == "progress"][-1]
    assert last_progress["percent"] == 100
    # result 携阶段规划（camelCase）。
    result = [d for e, d in events if e == "result"][0]
    assert result["taskId"] == _TID
    assert result["status"] == "stage_plan_ready"
    assert result["stagePlan"]["goal"] == "站稳外门。"
    assert result["stagePlan"]["chapters"] == chapters
    assert payload["stagePlan"]["chapters"][0]["title"] == "废物觉醒"


@pytest.mark.asyncio
async def test_plan_first_stage_error_envelope_passthrough() -> None:
    events, pub_mock = _capture_events()
    err = ErrorEnvelope(
        code="bible_not_confirmed", message="请先确认故事设定", http_status=400
    )
    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.stage_planner,
            "plan_first_stage",
            AsyncMock(side_effect=err),
        ),
    ):
        with pytest.raises(ErrorEnvelope):
            await worker_mod.plan_first_stage(
                {"pub_redis": object()}, _TID, _UID, _PID
            )
    # service 调用前已推 step1/step2 progress，异常后推 error、无 result（终态只 error）。
    kinds = [e for e, _ in events]
    assert "result" not in kinds
    assert kinds[-1] == "error"
    err_data = events[-1][1]
    assert err_data["code"] == "bible_not_confirmed"
    assert err_data["message"] == "请先确认故事设定"


@pytest.mark.asyncio
async def test_plan_first_stage_generic_error_generalized() -> None:
    events, pub_mock = _capture_events()
    with (
        patch.object(sse, "publish_event", pub_mock),
        patch.object(
            worker_mod.stage_planner,
            "plan_first_stage",
            AsyncMock(side_effect=RuntimeError("DB 连接串泄露风险 xxx")),
        ),
    ):
        with pytest.raises(RuntimeError):
            await worker_mod.plan_first_stage(
                {"pub_redis": object()}, _TID, _UID, _PID
            )
    kinds = [e for e, _ in events]
    assert "result" not in kinds
    assert kinds[-1] == "error"
    err_data = events[-1][1]
    assert err_data["code"] == "generate_failed"
    # 固定泛化文案，不外泄内部细节。
    assert "DB 连接串" not in err_data["message"]
    assert err_data["message"] == "生成失败，请稍后重试。"


def test_plan_first_stage_registered_in_worker_settings() -> None:
    assert worker_mod.plan_first_stage in worker_mod.WorkerSettings.functions
