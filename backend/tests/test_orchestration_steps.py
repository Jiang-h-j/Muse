"""Story 4.2 Task 3 验证：四段 step service（离线，mock session/provider/repo）。

覆盖每段的关键路径（不打真实 LLM、不碰 DB）：
- context-agent：读 confirmed bible 组装写作任务书（含设定/文风锚点/词表约束/本章想法）；
  无 confirmed 行 → bible_not_confirmed 400；租户守卫 404
- drafter：调 provider 思考档出初稿；空产 → generate_failed 502；check_quota 前置
- reviewer：调 provider 快档出审查意见；空产返回空串（非致命）
- polisher：词表自查 + 调 provider 出终稿；空产 → 502

范式仿 test_story_settle.py：ExitStack patch 依赖，_FakeSessionCtx 哑 session。
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.core.errors import ErrorEnvelope
from muse.orchestration import steps
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


def _patch_step(
    *,
    owned_project: object = "__present__",
    bible: object = None,
    provider: object = None,
    recent_chapters: object = None,
) -> ExitStack:
    """patch 一段 step 的公共依赖：session_maker、project_repo、story_bible_repo、
    chapter_repo.list_recent_chapters、usage_service.check_quota、get_provider_for_user。
    返回已进入的 ExitStack。"""
    stack = ExitStack()
    owned = MagicMock() if owned_project == "__present__" else owned_project
    stack.enter_context(
        patch.object(steps, "async_session_maker", lambda: _FakeSessionCtx())
    )
    stack.enter_context(
        patch.object(
            steps.project_repo,
            "get_owned_project",
            AsyncMock(return_value=owned),
        )
    )
    stack.enter_context(
        patch.object(
            steps.story_bible_repo,
            "get_confirmed_by_project",
            AsyncMock(return_value=bible),
        )
    )
    stack.enter_context(
        patch.object(
            steps.chapter_repo,
            "list_recent_chapters",
            AsyncMock(return_value=recent_chapters or []),
        )
    )
    stack.enter_context(
        patch.object(steps.usage_service, "check_quota", AsyncMock(return_value={}))
    )
    stack.enter_context(
        patch.object(
            steps, "get_provider_for_user", AsyncMock(return_value=provider)
        )
    )
    return stack


# ========== context-agent ==========


@pytest.mark.asyncio
async def test_context_agent_builds_brief() -> None:
    bible = _confirmed_bible()
    with _patch_step(bible=bible):
        brief = await steps.run_context_agent(
            user_id=_UID, project_id=_PID, chapter_number=1, chapter_idea="想看雨夜重逢"
        )
    # 设定字段、文风锚点、词表约束、本章想法都进了写作任务书。
    assert "修仙" in brief
    assert "林凡" in brief
    assert "冷峻克制" in brief  # style_profile
    assert "想看雨夜重逢" in brief  # chapter_idea
    assert "去 AI 味约束" in brief  # 词表约束段
    assert "第 1 章" in brief


@pytest.mark.asyncio
async def test_context_agent_injects_recent_chapter() -> None:
    """AC4：最近前序章节正文注入写作任务书「前情提要」段。"""
    prev = MagicMock()
    prev.chapter_number = 1
    prev.text = "林凡在雨夜觉醒了传承。"
    with _patch_step(bible=_confirmed_bible(), recent_chapters=[prev]):
        brief = await steps.run_context_agent(
            user_id=_UID, project_id=_PID, chapter_number=2, chapter_idea=None
        )
    assert "前情提要" in brief
    assert "林凡在雨夜觉醒了传承。" in brief
    assert "第 1 章正文" in brief


@pytest.mark.asyncio
async def test_context_agent_first_chapter_no_recent() -> None:
    """第一章无前序 → 前情提要块为空提示，不报错。"""
    with _patch_step(bible=_confirmed_bible(), recent_chapters=[]):
        brief = await steps.run_context_agent(
            user_id=_UID, project_id=_PID, chapter_number=1, chapter_idea=None
        )
    assert "这是第一章" in brief


@pytest.mark.asyncio
async def test_context_agent_no_idea_uses_placeholder() -> None:
    with _patch_step(bible=_confirmed_bible()):
        brief = await steps.run_context_agent(
            user_id=_UID, project_id=_PID, chapter_number=2, chapter_idea=None
        )
    assert "读者未补充" in brief


@pytest.mark.asyncio
async def test_context_agent_no_style_profile_uses_default() -> None:
    with _patch_step(bible=_confirmed_bible(style_profile=None)):
        brief = await steps.run_context_agent(
            user_id=_UID, project_id=_PID, chapter_number=1
        )
    assert "未锚定文风" in brief


@pytest.mark.asyncio
async def test_context_agent_not_confirmed_raises_400() -> None:
    with _patch_step(bible=None):  # 无 confirmed 行
        with pytest.raises(ErrorEnvelope) as ei:
            await steps.run_context_agent(
                user_id=_UID, project_id=_PID, chapter_number=1
            )
    assert ei.value.code == "bible_not_confirmed"
    assert ei.value.http_status == 400


@pytest.mark.asyncio
async def test_context_agent_tenant_guard_404() -> None:
    with _patch_step(owned_project=None):
        with pytest.raises(ErrorEnvelope) as ei:
            await steps.run_context_agent(
                user_id=_UID, project_id=_PID, chapter_number=1
            )
    assert ei.value.http_status == 404


# ========== drafter ==========


@pytest.mark.asyncio
async def test_drafter_produces_draft() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("这是初稿正文，雨落下来。"))
    with _patch_step(provider=provider):
        draft = await steps.run_drafter(
            user_id=_UID, project_id=_PID, writing_brief="写第一章"
        )
    assert "初稿正文" in draft
    # 用思考档（drafter 决策）。
    _, kwargs = provider.chat.call_args
    assert kwargs["model"].endswith("pro") or "pro" in kwargs["model"]


@pytest.mark.asyncio
async def test_drafter_empty_raises_502() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("   "))
    with _patch_step(provider=provider):
        with pytest.raises(ErrorEnvelope) as ei:
            await steps.run_drafter(
                user_id=_UID, project_id=_PID, writing_brief="写第一章"
            )
    assert ei.value.code == "generate_failed"
    assert ei.value.http_status == 502


@pytest.mark.asyncio
async def test_drafter_checks_quota_before_provider() -> None:
    """AC7：check_quota 须在 provider.chat 之前（顺序是核心约束，非仅是否调用）。"""
    call_order: list[str] = []

    async def _quota(session, uid):
        call_order.append("quota")

    async def _chat(messages, **kw):
        call_order.append("chat")
        return _fake_chat_result("初稿")

    provider = MagicMock()
    provider.chat = _chat
    stack = ExitStack()
    stack.enter_context(
        patch.object(steps, "async_session_maker", lambda: _FakeSessionCtx())
    )
    stack.enter_context(
        patch.object(
            steps.project_repo, "get_owned_project", AsyncMock(return_value=MagicMock())
        )
    )
    stack.enter_context(patch.object(steps.usage_service, "check_quota", _quota))
    stack.enter_context(
        patch.object(steps, "get_provider_for_user", AsyncMock(return_value=provider))
    )
    with stack:
        await steps.run_drafter(user_id=_UID, project_id=_PID, writing_brief="x")
    # 严格断言顺序：quota 在 chat 之前（防误改成「先调 provider 再查 quota」而不挂红）。
    assert call_order.index("quota") < call_order.index("chat")


# ========== reviewer ==========


@pytest.mark.asyncio
async def test_reviewer_produces_notes() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("设定一致性：无问题。"))
    with _patch_step(provider=provider):
        notes = await steps.run_reviewer(
            user_id=_UID, project_id=_PID, writing_brief="写第一章", draft="初稿"
        )
    assert "设定一致性" in notes
    _, kwargs = provider.chat.call_args
    assert "pro" in kwargs["model"]  # reviewer 用思考档（architecture.md:196 审查用 pro）


@pytest.mark.asyncio
async def test_reviewer_empty_returns_empty_not_fatal() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("  "))
    with _patch_step(provider=provider):
        notes = await steps.run_reviewer(
            user_id=_UID, project_id=_PID, writing_brief="x", draft="初稿"
        )
    assert notes == ""  # 空审查非致命


# ========== polisher ==========


@pytest.mark.asyncio
async def test_polisher_produces_final() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("这是润色后的终稿。"))
    with _patch_step(provider=provider):
        final = await steps.run_polisher(
            user_id=_UID,
            project_id=_PID,
            draft="他内心深处涌起一种莫名的悸动。",  # 含黑名单词，触发词表自查
            review_notes="文风偏 AI 味",
        )
    assert "终稿" in final
    _, kwargs = provider.chat.call_args
    assert "pro" in kwargs["model"]  # polisher 用思考档


@pytest.mark.asyncio
async def test_polisher_empty_raises_502() -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(""))
    with _patch_step(provider=provider):
        with pytest.raises(ErrorEnvelope) as ei:
            await steps.run_polisher(
                user_id=_UID, project_id=_PID, draft="初稿", review_notes=""
            )
    assert ei.value.code == "generate_failed"


@pytest.mark.asyncio
async def test_polisher_feeds_lexicon_hits_and_style_profile_to_prompt() -> None:
    """词表自查命中的黑名单词 + style_profile 文风锚点都进入 polisher user 消息（AC4 叠加）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("终稿"))
    bible = _confirmed_bible()  # 带 style_profile="人称：第三人称\n语气：冷峻克制"
    with _patch_step(provider=provider, bible=bible):
        await steps.run_polisher(
            user_id=_UID,
            project_id=_PID,
            draft="他内心深处涌起一种莫名的悸动，泪流满面。",
            review_notes="",
        )
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "内心深处" in user_msg  # 命中的黑名单词被喂给 polisher
    assert "冷峻克制" in user_msg  # style_profile 文风锚点注入（AC4）


@pytest.mark.asyncio
async def test_polisher_no_style_profile_uses_default() -> None:
    """confirmed bible 的 style_profile 为空时，polisher 用默认文风段（不阻塞）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("终稿"))
    with _patch_step(provider=provider, bible=_confirmed_bible(style_profile=None)):
        await steps.run_polisher(
            user_id=_UID, project_id=_PID, draft="初稿", review_notes=""
        )
    args, _ = provider.chat.call_args
    user_msg = args[0][-1]["content"]
    assert "未锚定文风" in user_msg
