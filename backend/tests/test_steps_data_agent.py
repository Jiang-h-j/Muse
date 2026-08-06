"""Story 5.2 Task 6 验证：data-agent step（离线，mock session/provider/repo）。

覆盖：
- 正常路径：mock provider 返回合法 JSON → run_data_agent 解析为 dict 并返回。
- 容错路径：provider 返回带 markdown fence 的 JSON → 剥 fence 后正常解析。
- 空产：provider 返回空字符串 → 抛 `_projection_failed` 502。
- JSON 解析失败：provider 返回非 JSON → 抛 `_projection_failed` 502。
- 必填字段缺失：provider 返回 JSON 但缺 `what_happened` → 抛 `_projection_failed` 502。
- 类型归一：provider 返回 JSON 但 `new_threads` 是 str 而非 list → 强制归一为 []；
  五要素是 None → 强制归一为 ""。
- 模型档：用 settings.deepseek_model_fast（快档 flash），非思考档 pro。
- 租户守卫：get_owned_project None → 抛 404 二义合一。

照 test_orchestration_steps.py 范式：`_patch_step` mock session_maker / project_repo /
story_bible_repo / usage_service / get_provider_for_user。
"""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.core.errors import ErrorEnvelope
from muse.orchestration import steps
from muse.providers.base import ChatResult

_UID = "11111111-1111-1111-1111-111111111111"
_PID = "22222222-2222-2222-2222-222222222222"


class _FakeSessionCtx:
    """同步方法的 async 上下文管理器 mock（照 test_orchestration_steps._FakeSessionCtx）。"""

    async def __aenter__(self) -> "_FakeSessionCtx":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _confirmed_bible(**overrides: object) -> MagicMock:
    """造一个 confirmed story_bible mock（与 test_orchestration_steps 同款）。"""
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


def _patch_data_agent_step(
    *,
    owned_project: object = "__present__",
    bible: object = None,
    provider: object = None,
    recent_chapter_cards: object = None,
) -> ExitStack:
    """patch data-agent step 的公共依赖（照 test_orchestration_steps._patch_step 范式）。

    data-agent 只调 project_repo / story_bible_repo / chapter_card_repo / usage_service /
    get_provider_for_user——不调 chapter_repo（无「前序章节正文」概念，拿的是 polisher 段
    产物 chapter_text 入参）。**A7 patch**：data-agent 需读前序 chapter_card 作上下文
    锚点，故 mock chapter_card_repo.list_recent_chapter_cards。
    """
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
            steps.chapter_card_repo,
            "list_recent_chapter_cards",
            AsyncMock(return_value=recent_chapter_cards or []),
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


def _fake_chat_result(content: str) -> ChatResult:
    """造一个 ChatResult（照 test_orchestration_steps._fake_chat_result 范式——5 个必填字段）。"""
    return ChatResult(
        content=content,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        model="deepseek-v4-flash",
    )


def _valid_extracted_json() -> str:
    """合法的 data-agent JSON 产出。"""
    return json.dumps(
        {
            "what_happened": "程野进入地下档案库。",
            "character_changes": "程野决定行动。",
            "new_facts_clues": "未来邮戳。",
            "unresolved_hooks": "是谁寄信？",
            "end_state": "程野打开抽屉。",
            "protagonist_state": "心智动摇。",
            "world_rules_state": "灵气复苏。",
            "current_stage": "第七码头。",
            "new_threads": [{"content": "邮戳伏笔", "introduced_chapter_number": 1}],
            "resolved_threads": [],
            "touched_threads": [],
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_data_agent_returns_dict() -> None:
    """正常路径：mock provider 返回合法 JSON → 解析为 dict 返回。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_valid_extracted_json()))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        extracted = await steps.run_data_agent(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            chapter_text="程野进入地下档案库，发现本不存在的走廊。",
        )

    assert isinstance(extracted, dict)
    assert extracted["what_happened"] == "程野进入地下档案库。"
    assert extracted["protagonist_state"] == "心智动摇。"
    assert extracted["new_threads"] == [
        {"content": "邮戳伏笔", "introduced_chapter_number": 1}
    ]
    assert extracted["resolved_threads"] == []
    assert extracted["touched_threads"] == []


@pytest.mark.asyncio
async def test_data_agent_strips_markdown_fence() -> None:
    """容错路径：provider 返回带 ```json ... ``` 包装的 JSON → 剥 fence 后正常解析。"""
    fenced = f"```json\n{_valid_extracted_json()}\n```"
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(fenced))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        extracted = await steps.run_data_agent(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            chapter_text="正文。",
        )

    assert isinstance(extracted, dict)
    assert extracted["what_happened"] == "程野进入地下档案库。"


@pytest.mark.asyncio
async def test_data_agent_empty_raises_projection_failed() -> None:
    """空产：provider 返回空字符串/全空白 → 抛 projection_failed 502。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("   "))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as exc_info:
            await steps.run_data_agent(
                user_id=_UID,
                project_id=_PID,
                chapter_number=1,
                chapter_text="正文。",
            )
    assert exc_info.value.code == "projection_failed"
    assert exc_info.value.http_status == 502


@pytest.mark.asyncio
async def test_data_agent_invalid_json_raises_projection_failed() -> None:
    """JSON 解析失败：provider 返回非 JSON → 抛 projection_failed 502。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("这不是 JSON，是散文。"))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as exc_info:
            await steps.run_data_agent(
                user_id=_UID,
                project_id=_PID,
                chapter_number=1,
                chapter_text="正文。",
            )
    assert exc_info.value.code == "projection_failed"


@pytest.mark.asyncio
async def test_data_agent_missing_required_key_raises_projection_failed() -> None:
    """必填字段缺失：JSON 缺 `what_happened` → 抛 projection_failed 502。"""
    incomplete = json.dumps(
        {
            "character_changes": "程野决定行动。",
            "new_facts_clues": "未来邮戳。",
            "unresolved_hooks": "是谁寄信？",
            "end_state": "程野打开抽屉。",
            "protagonist_state": "心智动摇。",
            "world_rules_state": "灵气复苏。",
            "current_stage": "第七码头。",
            "new_threads": [],
            "resolved_threads": [],
            "touched_threads": [],
        },
        ensure_ascii=False,
    )
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(incomplete))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        with pytest.raises(ErrorEnvelope) as exc_info:
            await steps.run_data_agent(
                user_id=_UID,
                project_id=_PID,
                chapter_number=1,
                chapter_text="正文。",
            )
    assert exc_info.value.code == "projection_failed"


@pytest.mark.asyncio
async def test_data_agent_type_normalization() -> None:
    """类型归一：`new_threads` 是 str 而非 list → 强制归一为 []；五要素是 None → 强制 ""。"""
    weird = json.dumps(
        {
            "what_happened": None,  # 非 str → 归一为 ""
            "character_changes": "程野决定行动。",
            "new_facts_clues": "未来邮戳。",
            "unresolved_hooks": "是谁寄信？",
            "end_state": "程野打开抽屉。",
            "protagonist_state": "心智动摇。",
            "world_rules_state": "灵气复苏。",
            "current_stage": "第七码头。",
            "new_threads": "不是 list",  # 非 list → 归一为 []
            "resolved_threads": [],
            "touched_threads": [],
        },
        ensure_ascii=False,
    )
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(weird))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        extracted = await steps.run_data_agent(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            chapter_text="正文。",
        )

    assert extracted["what_happened"] == ""
    assert extracted["new_threads"] == []


@pytest.mark.asyncio
async def test_data_agent_uses_fast_model() -> None:
    """模型档：用 settings.deepseek_model_fast（快档 flash），非思考档 pro。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_valid_extracted_json()))

    with _patch_data_agent_step(bible=_confirmed_bible(), provider=provider):
        await steps.run_data_agent(
            user_id=_UID,
            project_id=_PID,
            chapter_number=1,
            chapter_text="正文。",
        )

    _, kwargs = provider.chat.call_args
    assert kwargs["model"] == "deepseek-v4-flash"  # settings.deepseek_model_fast 默认值
    assert kwargs["max_tokens"] == 2048  # _DATA_AGENT_MAX_TOKENS


@pytest.mark.asyncio
async def test_data_agent_tenant_guard_404() -> None:
    """租户守卫：get_owned_project None → 抛 404 二义合一（NFR3）。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_valid_extracted_json()))

    with _patch_data_agent_step(owned_project=None, provider=provider):
        with pytest.raises(ErrorEnvelope) as exc_info:
            await steps.run_data_agent(
                user_id=_UID,
                project_id=_PID,
                chapter_number=1,
                chapter_text="正文。",
            )
    # 错误码由 exploration_service._exploration_not_found 工厂决定（4.6 起
    # 改名 project_not_found——「不属于我」与「不存在」二义合一，不泄露存在性）。
    assert exc_info.value.http_status == 404


@pytest.mark.asyncio
async def test_data_agent_bible_not_confirmed_raises_400() -> None:
    """防御：confirmed 圣经缺失（极端：创作中被取消确认）→ 抛 bible_not_confirmed 400。"""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_valid_extracted_json()))

    with _patch_data_agent_step(bible=None, provider=provider):
        with pytest.raises(ErrorEnvelope) as exc_info:
            await steps.run_data_agent(
                user_id=_UID,
                project_id=_PID,
                chapter_number=1,
                chapter_text="正文。",
            )
    assert exc_info.value.code == "bible_not_confirmed"
    assert exc_info.value.http_status == 400
