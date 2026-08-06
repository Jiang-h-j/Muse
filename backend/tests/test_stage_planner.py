"""Story 4.3 Task 1 验证：阶段规划生成 service（离线，mock session/provider/repo）。

覆盖 plan_first_stage 关键路径（不打真实 LLM、不碰 DB）：
- 正常：读 confirmed bible → LLM 出阶段目标 + 章骨架 → 落库返回 StagePlan
- 防御解析：含/缺章节、markdown 装饰、乱序章号、孤立简介行的样本行为
- 空产：无阶段目标 / 无有效章 → generate_failed 502
- 无 confirmed 行 → bible_not_confirmed 400
- 租户越权 → 404
- AC7：check_quota 在 provider.chat 之前（顺序断言）、走 get_provider_for_user（不自建 provider）

范式仿 test_orchestration_steps.py：ExitStack patch 依赖，_FakeSessionCtx 哑 session。
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.core.errors import ErrorEnvelope
from muse.orchestration import stage_planner
from muse.providers.base import ChatResult

_UID = uuid.uuid4()
_PID = uuid.uuid4()


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-pro",
    )


class _FakeSessionCtx:
    async def __aenter__(self) -> object:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _confirmed_bible(**overrides: object) -> MagicMock:
    """造一个 confirmed story_bible mock：12 字段用 getattr 取值。"""
    b = MagicMock()
    defaults = {
        "genre": "修仙",
        "core_appeal": "小人物逆袭的爽感",
        "protagonist": "林凡，想变强，怕失去在意的人",
        "main_conflict": "与宗门大能对抗",
        "world_rules": "灵气复苏，分境界",
        "overall_tone": "热血",
        "opening_hook": "废物觉醒传承",
        "power_system": "练气-筑基-金丹",
        "golden_finger": None,
        "romance_line": None,
        "faction_landscape": None,
        "style_profile": "人称：第三人称\n语气：冷峻克制",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(b, k, v)
    return b


def _patch_planner(
    *,
    owned_project: object = "__present__",
    bible: object = None,
    provider: object = None,
) -> ExitStack:
    """patch plan_first_stage 的公共依赖：session_maker、project_repo、story_bible_repo、
    usage_service.check_quota、get_provider_for_user、stage_plan_repo.upsert_stage_plan。

    upsert 默认回一个「回填传入 goal/chapters 的」StagePlan mock（不碰 DB）。
    """
    stack = ExitStack()
    owned = MagicMock() if owned_project == "__present__" else owned_project
    stack.enter_context(
        patch.object(stage_planner, "async_session_maker", lambda: _FakeSessionCtx())
    )
    stack.enter_context(
        patch.object(
            stage_planner.project_repo,
            "get_owned_project",
            AsyncMock(return_value=owned),
        )
    )
    stack.enter_context(
        patch.object(
            stage_planner.story_bible_repo,
            "get_confirmed_by_project",
            AsyncMock(return_value=bible),
        )
    )
    stack.enter_context(
        patch.object(
            stage_planner.usage_service, "check_quota", AsyncMock(return_value={})
        )
    )
    stack.enter_context(
        patch.object(
            stage_planner, "get_provider_for_user", AsyncMock(return_value=provider)
        )
    )

    async def _fake_upsert(session, *, user_id, project_id, goal, chapters, stage_number=1):
        plan = MagicMock()
        plan.goal = goal
        plan.chapters = chapters
        plan.stage_number = stage_number
        return plan

    stack.enter_context(
        patch.object(stage_planner.stage_plan_repo, "upsert_stage_plan", _fake_upsert)
    )
    return stack


# ========== 防御解析（纯函数，无需 patch） ==========


def test_parse_plan_response_normal() -> None:
    content = (
        "阶段目标：让林凡从废物觉醒，站稳宗门外门。\n"
        "第1章标题：废物觉醒\n"
        "第1章简介：林凡被退婚，意外觉醒上古传承。\n"
        "第2章标题：外门试炼\n"
        "第2章简介：初入宗门，遭同门排挤。\n"
    )
    goal, chapters = stage_planner._parse_plan_response(content)
    assert "废物觉醒" in goal
    assert len(chapters) == 2
    assert chapters[0] == {"title": "废物觉醒", "brief": "林凡被退婚，意外觉醒上古传承。"}
    assert chapters[1]["title"] == "外门试炼"


def test_parse_plan_response_strips_markdown_decor() -> None:
    """LLM 违背 prompt 加了 markdown 装饰/编号——仍能命中标签（防御加固）。"""
    content = (
        "**阶段目标**：站稳外门。\n"
        "- 第1章标题：废物觉醒\n"
        "  第1章简介：觉醒传承。\n"
    )
    goal, chapters = stage_planner._parse_plan_response(content)
    assert goal == "站稳外门。"
    assert len(chapters) == 1
    assert chapters[0]["title"] == "废物觉醒"


def test_parse_plan_response_sorts_and_drops_titleless() -> None:
    """乱序章号按章号升序；只有简介无标题的孤立章丢弃。"""
    content = (
        "阶段目标：目标。\n"
        "第3章标题：第三章\n"
        "第1章标题：第一章\n"
        "第1章简介：一。\n"
        "第2章简介：只有简介没标题，应被丢弃。\n"
    )
    goal, chapters = stage_planner._parse_plan_response(content)
    titles = [c["title"] for c in chapters]
    assert titles == ["第一章", "第三章"]  # 按章号升序、第2章无标题被丢
    assert chapters[0]["brief"] == "一。"
    assert chapters[1]["brief"] == ""  # 第三章无简介 → 空串


def test_parse_plan_response_empty_content() -> None:
    goal, chapters = stage_planner._parse_plan_response("模型完全跑偏的胡言乱语")
    assert goal == ""
    assert chapters == []


# ========== plan_first_stage 正常路径 ==========


@pytest.mark.asyncio
async def test_plan_first_stage_produces_plan() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result(
            "阶段目标：站稳外门。\n"
            "第1章标题：废物觉醒\n第1章简介：觉醒传承。\n"
            "第2章标题：外门试炼\n第2章简介：遭排挤。\n"
        )
    )
    with _patch_planner(bible=_confirmed_bible(), provider=provider):
        plan = await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    assert plan.goal == "站稳外门。"
    assert len(plan.chapters) == 2
    assert plan.chapters[0]["title"] == "废物觉醒"
    # 用思考档 pro（model 档决策）。
    _, kwargs = provider.chat.call_args
    assert "pro" in kwargs["model"]


@pytest.mark.asyncio
async def test_plan_first_stage_injects_setting_and_style() -> None:
    """confirmed 设定字段 + style_profile 都进入 LLM prompt（AC2 基于真实设定生成）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")
    )
    with _patch_planner(bible=_confirmed_bible(), provider=provider):
        await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "修仙" in user_msg  # genre
    assert "林凡" in user_msg  # protagonist
    assert "冷峻克制" in user_msg  # style_profile


@pytest.mark.asyncio
async def test_plan_first_stage_no_style_uses_default() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")
    )
    with _patch_planner(bible=_confirmed_bible(style_profile=None), provider=provider):
        await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "未锚定文风" in user_msg


# ========== 空产 / 错误路径 ==========


@pytest.mark.asyncio
async def test_plan_first_stage_no_goal_raises_502() -> None:
    """有章但无阶段目标 → 空产 502。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("第1章标题：t\n第1章简介：b\n")
    )
    with _patch_planner(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    assert ei.value.code == "generate_failed"
    assert ei.value.http_status == 502


@pytest.mark.asyncio
async def test_plan_first_stage_no_chapters_raises_502() -> None:
    """有目标但无有效章 → 空产 502。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("阶段目标：只有目标。\n"))
    with _patch_planner(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    assert ei.value.code == "generate_failed"


@pytest.mark.asyncio
async def test_plan_first_stage_not_confirmed_raises_400() -> None:
    with _patch_planner(bible=None):  # 无 confirmed 行
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    assert ei.value.code == "bible_not_confirmed"
    assert ei.value.http_status == 400


@pytest.mark.asyncio
async def test_plan_first_stage_tenant_guard_404() -> None:
    with _patch_planner(owned_project=None):
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    assert ei.value.http_status == 404


# ========== AC7：记账正确性 ==========


@pytest.mark.asyncio
async def test_plan_first_stage_checks_quota_before_provider() -> None:
    """AC7：check_quota 须在 provider.chat 之前（顺序是核心约束，非仅是否调用）。"""
    call_order: list[str] = []

    async def _quota(session, uid):
        call_order.append("quota")

    async def _chat(messages, **kw):
        call_order.append("chat")
        return _fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")

    provider = MagicMock()
    provider.chat = _chat
    get_provider_mock = AsyncMock(return_value=provider)

    stack = _patch_planner(bible=_confirmed_bible(), provider=provider)
    # 覆盖 check_quota / get_provider 为记录顺序的版本。
    stack.enter_context(
        patch.object(stage_planner.usage_service, "check_quota", _quota)
    )
    stack.enter_context(
        patch.object(stage_planner, "get_provider_for_user", get_provider_mock)
    )
    with stack:
        await stage_planner.plan_first_stage(user_id=_UID, project_id=_PID)
    # 严格断言顺序：quota 在 chat 之前。
    assert call_order.index("quota") < call_order.index("chat")
    # AC7：走 get_provider_for_user（不自建 DeepSeekProvider）。
    get_provider_mock.assert_awaited_once()


# ========== Story 4.7：plan_next_stage（下一阶段规划） ==========


def _fake_prev_stage(stage_number: int = 1, goal: str = "站稳外门。") -> MagicMock:
    prev = MagicMock()
    prev.stage_number = stage_number
    prev.goal = goal
    prev.chapters = [{"title": "t", "brief": "b"}]
    return prev


def _patch_next_planner(
    *,
    bible: object = None,
    provider: object = None,
    prev_stage: object = "__present__",
) -> ExitStack:
    """patch plan_next_stage 依赖：复用 _patch_planner 的公共 patch + 追加 get_latest_stage。"""
    stack = _patch_planner(bible=bible, provider=provider)
    prev = _fake_prev_stage() if prev_stage == "__present__" else prev_stage
    stack.enter_context(
        patch.object(
            stage_planner.stage_plan_repo,
            "get_latest_stage",
            AsyncMock(return_value=prev),
        )
    )
    return stack


@pytest.mark.asyncio
async def test_plan_next_stage_produces_plan_with_incremented_stage_number() -> None:
    """下一阶段规划：upsert stage_number = 上一阶段 + 1（不写死首阶段）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result(
            "阶段目标：进入内门争锋。\n第1章标题：内门试炼\n第1章简介：踏入内门。\n"
        )
    )
    with _patch_next_planner(
        bible=_confirmed_bible(), provider=provider, prev_stage=_fake_prev_stage(2)
    ):
        plan = await stage_planner.plan_next_stage(
            user_id=_UID, project_id=_PID, direction="让主角开始怀疑同伴"
        )
    assert plan.goal == "进入内门争锋。"
    assert plan.stage_number == 3  # 上一阶段 2 + 1


@pytest.mark.asyncio
async def test_plan_next_stage_injects_prev_goal_and_direction() -> None:
    """上一阶段目标 + 读者方向 direction 都进入 LLM prompt。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")
    )
    with _patch_next_planner(
        bible=_confirmed_bible(),
        provider=provider,
        prev_stage=_fake_prev_stage(1, goal="站稳外门。"),
    ):
        await stage_planner.plan_next_stage(
            user_id=_UID, project_id=_PID, direction="节奏慢下来铺一段感情"
        )
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "站稳外门。" in user_msg  # 上一阶段目标
    assert "节奏慢下来铺一段感情" in user_msg  # 读者方向


@pytest.mark.asyncio
async def test_plan_next_stage_empty_direction_uses_default_hint() -> None:
    """空 direction（直接继续）→ prompt 用默认「按设定+上一阶段自然推进」提示。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")
    )
    with _patch_next_planner(bible=_confirmed_bible(), provider=provider):
        await stage_planner.plan_next_stage(
            user_id=_UID, project_id=_PID, direction=None
        )
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "直接继续" in user_msg


@pytest.mark.asyncio
async def test_plan_next_stage_no_prev_stage_raises_502() -> None:
    """无任何上一阶段（防御）→ 502（service 层已前置 no_stage_plan 400，此为独立 session 兜底）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("阶段目标：x。\n第1章标题：t\n第1章简介：b\n")
    )
    with _patch_next_planner(
        bible=_confirmed_bible(), provider=provider, prev_stage=None
    ):
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_next_stage(user_id=_UID, project_id=_PID)
    assert ei.value.code == "generate_failed"
    assert ei.value.http_status == 502


@pytest.mark.asyncio
async def test_plan_next_stage_empty_output_raises_502() -> None:
    """LLM 空产（无目标）→ 502。"""
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("第1章标题：t\n第1章简介：b\n")
    )
    with _patch_next_planner(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as ei:
            await stage_planner.plan_next_stage(user_id=_UID, project_id=_PID)
    assert ei.value.code == "generate_failed"
