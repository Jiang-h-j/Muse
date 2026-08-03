"""Story 2.8 验证（2026-08-03 合并重构后）：自由探索——设定导航、候选回复与 7 项完成度门禁。

本文件聚焦离线可跑单元（不打真实 LLM、不碰 DB，CI 必过）：
- `free_explorer_agent._parse_chat_response`：合并调用的解析——聊天正文/分隔符切分、
  已清楚→filled、还缺→不产生 dict 项、追问项提取、候选回复提取、畸形/未知标签忽略、
  分隔符缺失时整段视为聊天正文。
- `guidance_agent._merge_field_updates`/`_still_missing`：AC2 单调性核心——已 filled/
  skipped 的项不被打回 missing。
- `guidance_agent.apply_chat_judgement`：把已解析的判定结果合并进 `guidance_state`
  （不再调用 LLM）——单调性、追问字段 fallback、全部完成时 ready_to_settle 置真、
  候选回复随判定写入。
- `guidance_agent._parse_question_with_suggestions`：开场问题/跳过下一问的「问题正文 +
  候选回复」解析，分隔符缺失时问题正文兜底、候选回复返回空列表。
- `guidance_agent._parse_skip_summary`：取「结论：」后文本、留空返回 None（不杜撰）。
- `start_guidance`/`skip_current_field` 编排单元（mock get_provider_for_user +
  check_quota + repos）：护栏 429 各自的降级/报错取舍、已 skipped 项不被重新打开、
  空产兜底、开场问题/下一问落库为真实 agent 聊天消息。

端点集成测试（含 401/404/409/422 与真实 DB 落库）见 `test_exploration_guidance.py`。
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from muse.core.errors import ErrorEnvelope
from muse.providers.base import ChatResult
from muse.services import free_explorer_agent, guidance_agent, story_settle_agent

# ---------- 共享 fixture/helper ----------


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


def _project(mode: str = "free") -> MagicMock:
    p = MagicMock()
    p.mode = mode
    return p


def _session_row(guidance_state: dict | None) -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    s.guidance_state = guidance_state
    return s


def _initial_state() -> dict:
    return {
        "fields": {key: "missing" for key, _ in story_settle_agent._BACKBONE_FIELDS},
        "current_field": None,
        "current_suggestions": [],
        "ready_to_settle": False,
    }


def _orchestration(
    *,
    provider: object,
    session_row: object,
    check_quota: object = None,
    get_owned_project: object = "__default__",
) -> ExitStack:
    """进入 guidance_agent 依赖的一组 patch，返回已进入的 ExitStack（with 内自动退出）。

    provider/repos/quota 全 mock，离线可跑；`session` 参数传入调用方自己构造的假 session
    对象（各函数只用它做占位透传给 repo/provider mock，不真正建连接）。
    """
    owned = _project() if get_owned_project == "__default__" else get_owned_project
    stack = ExitStack()
    for target, attr, val in [
        (
            guidance_agent.project_repo,
            "get_owned_project",
            AsyncMock(return_value=owned),
        ),
        (
            guidance_agent.exploration_repo,
            "get_session_by_project",
            AsyncMock(return_value=session_row),
        ),
        (
            guidance_agent.exploration_repo,
            "list_free_messages_by_session",
            AsyncMock(return_value=[]),
        ),
        (
            guidance_agent.exploration_repo,
            "append_free_message",
            AsyncMock(),
        ),
        (
            guidance_agent.story_clue_repo,
            "list_clues_by_session",
            AsyncMock(return_value=[]),
        ),
        (
            guidance_agent.exploration_repo,
            "update_guidance_state",
            AsyncMock(),
        ),
        (
            guidance_agent.usage_service,
            "check_quota",
            check_quota or AsyncMock(),
        ),
        (
            guidance_agent,
            "get_provider_for_user",
            AsyncMock(return_value=provider),
        ),
        (
            guidance_agent.exploration_repo,
            "has_free_user_message",
            AsyncMock(return_value=False),
        ),
    ]:
        stack.enter_context(patch.object(target, attr, val))
    return stack


class _FakeSession:
    """哑 session：本模块编排函数只需要它能被传给 mock 掉的 repo/provider，不做真实 IO。"""

    async def commit(self) -> None:
        return None


def _judgement_patches(state: dict, update_mock: object = None) -> ExitStack:
    """`apply_chat_judgement` 依赖的 patch（不调用 LLM，纯合并 + 落库）。

    `_generate_fallback_suggestions` 默认 mock 为返回空列表——绝大多数测试不关心候选
    兜底逻辑（那归专门的 fallback 测试覆盖），只验证合并/落库行为本身。需要测 fallback
    的用例自行覆盖此 patch。
    """
    stack = ExitStack()
    stack.enter_context(
        patch.object(
            guidance_agent.exploration_repo,
            "get_session_by_project",
            AsyncMock(return_value=_session_row(state)),
        )
    )
    stack.enter_context(
        patch.object(
            guidance_agent.project_repo, "get_owned_project", AsyncMock(return_value=_project())
        )
    )
    stack.enter_context(
        patch.object(
            guidance_agent.exploration_repo,
            "update_guidance_state",
            update_mock or AsyncMock(),
        )
    )
    stack.enter_context(
        patch.object(
            guidance_agent,
            "_generate_fallback_suggestions",
            AsyncMock(return_value=[]),
        )
    )
    return stack


# ---------- 解析单元：free_explorer_agent._parse_chat_response（合并重构核心） ----------


def test_parse_chat_response_splits_chat_text_and_judgement_block() -> None:
    content = (
        "这故事最抓人的地方是什么？\n"
        "###GUIDANCE###\n"
        "题材：已清楚\n"
        "核心吸引力：还缺\n"
        "主角：已清楚\n"
        "主要冲突：还缺\n"
        "关键世界规则：还缺\n"
        "整体气质：还缺\n"
        "开篇钩子：还缺\n"
        "追问项：核心吸引力\n"
        "候选：他从小就想证明自己。\n"
        "候选：他被卷入了一场不属于他的战争。"
    )
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response(content)
    )
    assert chat_text == "这故事最抓人的地方是什么？"
    assert updates == {"genre": "filled", "protagonist": "filled"}
    assert question_field == "core_appeal"
    assert suggestions == ["他从小就想证明自己。", "他被卷入了一场不属于他的战争。"]


def test_parse_chat_response_missing_separator_treats_whole_as_chat_text() -> None:
    # 分隔符缺失（模型偏离格式）→ 整段视为聊天正文，其余三项返回空，不因单次解析失败
    # 误判倒退（保守写入精神）。
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response("完全没有分隔符的一段自由回复")
    )
    assert chat_text == "完全没有分隔符的一段自由回复"
    assert updates == {}
    assert question_field is None
    assert suggestions == []


def test_parse_chat_response_ignores_unknown_labels_and_malformed_lines() -> None:
    # 容错解析（2026-08-03 修复）：分隔符之后的「未知字段：已清楚」「没有冒号的一行」
    # 不是主干标签/候选/追问项，归入聊天正文（可能是模型在结构化块里夹了非结构化内容）；
    # 只有主干标签行（如「题材：已清楚」）被识别为结构化行并剔除。
    content = "聊天正文\n###GUIDANCE###\n未知字段：已清楚\n没有冒号的一行\n题材：已清楚\n"
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response(content)
    )
    assert chat_text == "聊天正文\n未知字段：已清楚\n没有冒号的一行"
    assert updates == {"genre": "filled"}
    assert question_field is None
    assert suggestions == []


def test_parse_chat_response_unknown_question_field_label_returns_none() -> None:
    content = "聊天正文\n###GUIDANCE###\n追问项：不存在的字段\n候选：某个回答"
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response(content)
    )
    assert chat_text == "聊天正文"
    assert question_field is None
    assert suggestions == ["某个回答"]


def test_parse_chat_response_tolerates_punctuation_and_modifier_variants() -> None:
    # 模型输出「已清楚。」「已清楚，但还可以更细」等带标点/修饰语的变体，不因严格 ==
    # 匹配失败而被误判为未清楚。
    content = (
        "聊天正文\n###GUIDANCE###\n"
        "题材：已清楚。\n核心吸引力：已清楚，但还可以更细\n主角：还缺"
    )
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response(content)
    )
    assert updates == {"genre": "filled", "core_appeal": "filled"}


def test_parse_chat_response_no_question_field_when_all_clear() -> None:
    block = "\n".join(f"{label}：已清楚" for _, label in story_settle_agent._BACKBONE_FIELDS)
    content = f"聊天正文\n###GUIDANCE###\n{block}"
    chat_text, updates, question_field, suggestions = (
        free_explorer_agent._parse_chat_response(content)
    )
    assert len(updates) == 7
    assert question_field is None
    assert suggestions == []


def test_parse_chat_response_caps_suggestions_at_four() -> None:
    content = (
        "聊天正文\n###GUIDANCE###\n"
        "候选：一\n候选：二\n候选：三\n候选：四\n候选：五（应被截断）"
    )
    _, _, _, suggestions = free_explorer_agent._parse_chat_response(content)
    assert suggestions == ["一", "二", "三", "四"]


# ---------- 合并单元：guidance_agent._merge_field_updates / _still_missing ----------


def test_merge_field_updates_promotes_missing_only() -> None:
    state = _initial_state()
    fields = guidance_agent._merge_field_updates(state, {"genre": "filled"})
    assert fields["genre"] == "filled"
    assert fields["protagonist"] == "missing"


def test_merge_field_updates_does_not_demote_skipped_or_filled() -> None:
    state = _initial_state()
    state["fields"]["genre"] = "skipped"
    state["fields"]["core_appeal"] = "filled"
    fields = guidance_agent._merge_field_updates(
        state, {"genre": "filled", "core_appeal": "filled", "protagonist": "filled"}
    )
    assert fields["genre"] == "skipped"  # 未被打回/改写
    assert fields["core_appeal"] == "filled"  # 未被重复覆盖
    assert fields["protagonist"] == "filled"  # 仍 missing 的项正常更新


def test_still_missing_preserves_backbone_order() -> None:
    state = _initial_state()
    state["fields"]["genre"] = "filled"
    state["fields"]["protagonist"] = "skipped"
    missing = guidance_agent._still_missing(state["fields"])
    assert missing == [
        "core_appeal",
        "main_conflict",
        "world_rules",
        "overall_tone",
        "opening_hook",
    ]


# ---------- 编排单元：apply_chat_judgement（不调用 LLM，纯合并 + 落库） ----------


async def test_apply_chat_judgement_no_session_returns_initial_state() -> None:
    with _orchestration(provider=AsyncMock(), session_row=None):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={},
            question_field=None,
            suggestions=[],
            chat_text="",
        )
    assert result == _initial_state()


async def test_apply_chat_judgement_no_missing_fields_short_circuits() -> None:
    state = _initial_state()
    for key, _ in story_settle_agent._BACKBONE_FIELDS:
        state["fields"][key] = "filled"
    state["ready_to_settle"] = True
    update_mock = AsyncMock()
    with _judgement_patches(state, update_mock):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={},
            question_field=None,
            suggestions=[],
            chat_text="",
        )
    update_mock.assert_not_awaited()
    assert result == state


async def test_apply_chat_judgement_promotes_missing_and_sets_current_field() -> None:
    state = _initial_state()
    with _judgement_patches(state):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={"genre": "filled"},
            question_field="protagonist",
            suggestions=["候选A", "候选B"],
            chat_text="主角是个什么样的人？",
        )
    assert result["fields"]["genre"] == "filled"
    # question_field 标注 protagonist，且仍在 still_missing 里——直接采纳。
    assert result["current_field"] == "protagonist"
    assert result["current_suggestions"] == ["候选A", "候选B"]
    assert result["ready_to_settle"] is False


async def test_apply_chat_judgement_falls_back_to_first_missing_when_field_unmatched() -> None:
    state = _initial_state()
    with _judgement_patches(state):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={"genre": "filled"},
            question_field=None,  # 未标注或标注了已 filled 的字段
            suggestions=[],
            chat_text="这故事最抓人的地方是什么？",
        )
    assert result["current_field"] == "core_appeal"  # still_missing 固定顺序第一项


async def test_apply_chat_judgement_ready_to_settle_when_no_missing_left() -> None:
    state = _initial_state()
    for key, _ in story_settle_agent._BACKBONE_FIELDS[:-1]:
        state["fields"][key] = "filled"
    last_key = story_settle_agent._BACKBONE_FIELDS[-1][0]
    with _judgement_patches(state):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={last_key: "filled"},
            question_field=None,
            suggestions=[],
            chat_text="",
        )
    assert all(v != "missing" for v in result["fields"].values())
    assert result["current_field"] is None
    assert result["current_suggestions"] == []
    assert result["ready_to_settle"] is True


async def test_apply_chat_judgement_skipped_field_not_reopened() -> None:
    # AC2 硬约束：已 skipped 的项即便本轮 field_updates 里带同 key 的 filled，也不被
    # 打回/改写（_merge_field_updates 只作用于仍 missing 的项）。
    state = _initial_state()
    state["fields"]["genre"] = "skipped"
    with _judgement_patches(state):
        result = await guidance_agent.apply_chat_judgement(
            _FakeSession(),
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            field_updates={"genre": "filled"},
            question_field=None,
            suggestions=[],
            chat_text="",
        )
    assert result["fields"]["genre"] == "skipped"


async def test_apply_chat_judgement_fallback_when_suggestions_empty() -> None:
    # 兜底（2026-08-03）：合并调用漏掉候选时，apply_chat_judgement 应单独补一次候选生成，
    # 把兜底结果写入 current_suggestions，避免前端展示「暂时没想到合适的思路」。
    # 候选以 chat_text 为锚点（而非 current_field 标签）——断言 chat_text 被透传给兜底。
    state = _initial_state()
    fallback_mock = AsyncMock(return_value=["兜底候选一", "兜底候选二"])
    with _judgement_patches(state):
        # 覆盖默认的空列表 fallback mock，注入有内容的兜底候选。
        with patch.object(
            guidance_agent, "_generate_fallback_suggestions", fallback_mock
        ):
            result = await guidance_agent.apply_chat_judgement(
                _FakeSession(),
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                field_updates={"genre": "filled"},
                question_field="protagonist",
                suggestions=[],  # 合并调用漏掉了候选
                chat_text="主角是个什么样的人？",
            )
    fallback_mock.assert_awaited_once()
    # 兜底必须拿到 Agent 刚问的这句话作为锚点，而非依赖字段标签。
    _, kwargs = fallback_mock.call_args
    assert kwargs["chat_text"] == "主角是个什么样的人？"
    assert result["current_suggestions"] == ["兜底候选一", "兜底候选二"]


async def test_apply_chat_judgement_no_fallback_when_suggestions_present() -> None:
    # 合并调用正常返回候选时，不应触发兜底调用（省成本）。
    state = _initial_state()
    fallback_mock = AsyncMock(return_value=["不该被用的兜底"])
    with _judgement_patches(state):
        with patch.object(
            guidance_agent, "_generate_fallback_suggestions", fallback_mock
        ):
            result = await guidance_agent.apply_chat_judgement(
                _FakeSession(),
                user_id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                field_updates={"genre": "filled"},
                question_field="protagonist",
                suggestions=["正常候选"],  # 合并调用已返回候选
                chat_text="主角是个什么样的人？",
            )
    fallback_mock.assert_not_awaited()
    assert result["current_suggestions"] == ["正常候选"]


# ---------- 解析单元：guidance_agent._parse_question_with_suggestions ----------


def test_parse_question_with_suggestions_splits_correctly() -> None:
    content = (
        "这故事最抓人的地方是什么？\n"
        "###SUGGESTIONS###\n候选：一个孤独的侦探\n候选：一个失忆的杀手"
    )
    question, suggestions = guidance_agent._parse_question_with_suggestions(content)
    assert question == "这故事最抓人的地方是什么？"
    assert suggestions == ["一个孤独的侦探", "一个失忆的杀手"]


def test_parse_question_with_suggestions_missing_separator_returns_empty_suggestions() -> None:
    question, suggestions = guidance_agent._parse_question_with_suggestions(
        "只有问题正文，没有分隔符"
    )
    assert question == "只有问题正文，没有分隔符"
    assert suggestions == []


def test_parse_question_with_suggestions_caps_at_four() -> None:
    content = "问题\n###SUGGESTIONS###\n候选：一\n候选：二\n候选：三\n候选：四\n候选：五"
    _, suggestions = guidance_agent._parse_question_with_suggestions(content)
    assert suggestions == ["一", "二", "三", "四"]


# ---------- 解析单元：_parse_skip_summary ----------


def test_parse_skip_summary_extracts_conclusion() -> None:
    assert guidance_agent._parse_skip_summary("结论：一个雨夜收到陌生来信的人") == (
        "一个雨夜收到陌生来信的人"
    )


def test_parse_skip_summary_blank_conclusion_returns_none() -> None:
    assert guidance_agent._parse_skip_summary("结论：") is None


def test_parse_skip_summary_missing_line_returns_none() -> None:
    assert guidance_agent._parse_skip_summary("完全不符合格式的一段话") is None


# ---------- 编排单元：start_guidance ----------


async def test_start_guidance_generates_opening_question_and_persists_as_message() -> None:
    state = _initial_state()
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result(
            "这故事最抓人的地方是什么？\n###SUGGESTIONS###\n候选：主角想要复仇\n候选：主角想要救赎"
        )
    )
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)) as _stack:
        with patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.start_guidance(
                user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="story_idea"
            )
    assert result["current_field"] == "core_appeal"  # story_idea → core_appeal 映射
    assert result["current_suggestions"] == ["主角想要复仇", "主角想要救赎"]
    # 开场问题落库为真实 agent 聊天消息（2026-08-03 合并重构新增）。
    append_mock.assert_awaited_once()
    _, kwargs = append_mock.call_args
    assert kwargs["role"] == "agent"
    assert kwargs["content"] == "这故事最抓人的地方是什么？"


async def test_start_guidance_already_started_is_idempotent() -> None:
    # 幂等防护：会话已有对话 → 直接返回当前态，不重新生成开场问题、不调 provider、不落库。
    state = _initial_state()
    state["current_field"] = "protagonist"
    state["current_suggestions"] = ["已经生成过的候选"]
    provider = AsyncMock()
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        with patch.object(
            guidance_agent.exploration_repo,
            "has_free_user_message",
            AsyncMock(return_value=True),
        ), patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.start_guidance(
                user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="protagonist"
            )
    provider.chat.assert_not_awaited()
    append_mock.assert_not_awaited()
    assert result == state


async def test_start_guidance_field_already_skipped_is_idempotent() -> None:
    # 零消息状态下该 entry 映射的字段已被跳过，再次调用同一 entry 不应重新打开该字段——
    # 单调性防护，不调 provider、不落库。
    state = _initial_state()
    state["fields"]["core_appeal"] = "skipped"
    provider = AsyncMock()
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        with patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.start_guidance(
                user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="story_idea"
            )
    provider.chat.assert_not_awaited()
    append_mock.assert_not_awaited()
    assert result == state
    assert result["fields"]["core_appeal"] == "skipped"  # 未被重新打开为 current_field


async def test_start_guidance_generation_falls_back_to_default_question() -> None:
    # 空产（模型偏离格式，问题正文为空）→ 兜底默认问题，仍正常落库 + 完成流程。
    state = _initial_state()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(""))
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        with patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.start_guidance(
                user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="protagonist"
            )
    assert result["current_field"] == "protagonist"
    append_mock.assert_awaited_once()
    _, kwargs = append_mock.call_args
    assert "主角" in kwargs["content"]


# ---------- 编排单元：skip_current_field ----------


async def test_skip_current_field_no_current_field_raises_400() -> None:
    state = _initial_state()
    try:
        with _orchestration(provider=AsyncMock(), session_row=_session_row(state)):
            await guidance_agent.skip_current_field(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    except ErrorEnvelope as exc:
        assert exc.code == "no_current_question"
    else:
        raise AssertionError("expected ErrorEnvelope")


async def test_skip_current_field_marks_skipped_even_when_quota_exceeded() -> None:
    # 状态转移优先生效：护栏 429 只影响「下一问生成」与「谨慎归纳」这两步，跳过动作本身
    # 仍生效。
    state = _initial_state()
    state["current_field"] = "genre"
    provider = AsyncMock()
    quota_fail = AsyncMock(
        side_effect=ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    )
    with _orchestration(
        provider=provider, session_row=_session_row(state), check_quota=quota_fail
    ):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    provider.chat.assert_not_awaited()


async def test_skip_current_field_summarizes_into_matching_clue() -> None:
    state = _initial_state()
    state["current_field"] = "genre"
    # still_missing 只剩 genre 时，跳过后无下一项可推进，直接进入谨慎归纳；构造 6 项已
    # filled，只剩 genre 待跳过，隔离「推进下一问」与「归纳」两条分支，聚焦本用例断言归纳。
    for key, _ in story_settle_agent._BACKBONE_FIELDS:
        if key != "genre":
            state["fields"][key] = "filled"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("结论：都市悬疑"))
    clue = MagicMock()
    clue.clue_key = "genre"
    with (
        _orchestration(provider=provider, session_row=_session_row(state)),
        patch.object(
            guidance_agent.story_clue_repo,
            "list_clues_by_session",
            AsyncMock(return_value=[clue]),
        ) as list_clues,
        patch.object(
            guidance_agent.story_clue_repo, "update_clue_value", AsyncMock(return_value=True)
        ) as update_value,
    ):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    assert result["ready_to_settle"] is True  # genre 是最后一项
    list_clues.assert_awaited()
    update_value.assert_awaited_once()
    _, kwargs = update_value.call_args
    assert kwargs["clue"] is clue
    assert kwargs["value"] == "都市悬疑"


async def test_skip_current_field_no_summary_skips_clue_write_silently() -> None:
    state = _initial_state()
    state["current_field"] = "genre"
    for key, _ in story_settle_agent._BACKBONE_FIELDS:
        if key != "genre":
            state["fields"][key] = "filled"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("结论："))
    with (
        _orchestration(provider=provider, session_row=_session_row(state)),
        patch.object(
            guidance_agent.story_clue_repo, "update_clue_value", AsyncMock()
        ) as update_value,
    ):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    update_value.assert_not_awaited()


async def test_skip_current_field_advances_to_ready_when_last_field() -> None:
    state = _initial_state()
    for key, _ in story_settle_agent._BACKBONE_FIELDS[:-1]:
        state["fields"][key] = "filled"
    last_key = story_settle_agent._BACKBONE_FIELDS[-1][0]
    state["current_field"] = last_key
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("结论："))
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"][last_key] == "skipped"
    assert result["ready_to_settle"] is True


async def test_skip_current_field_immediately_advances_and_persists_next_question() -> None:
    # 跳过后若还有 missing 项，应立即生成下一问 + 候选回复，落库为真实 agent 聊天消息，
    # 而非清空为空白态等下一轮对话触发。用 side_effect 区分「下一问生成」与「谨慎归纳」
    # 两次不同的 provider.chat 调用返回值。
    state = _initial_state()
    state["current_field"] = "genre"
    provider = AsyncMock()
    provider.chat = AsyncMock(
        side_effect=[
            _fake_chat_result(
                "核心吸引力是什么打动人的地方？\n###SUGGESTIONS###\n候选：读者想看主角复仇"
            ),  # 下一问生成
            _fake_chat_result("结论："),  # 谨慎归纳（无材料可归纳）
        ]
    )
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        with patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.skip_current_field(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    assert result["fields"]["genre"] == "skipped"
    # 立即推进：still_missing 固定顺序第一项（core_appeal）成为新的 current_field，
    # 问题文本 + 候选回复来自生成结果，而非清空为 None 等下一轮对话触发。
    assert result["current_field"] == "core_appeal"
    assert result["current_suggestions"] == ["读者想看主角复仇"]
    assert result["ready_to_settle"] is False
    assert provider.chat.await_count == 2
    # 下一问落库为真实 agent 聊天消息（2026-08-03 合并重构新增）。
    append_mock.assert_awaited_once()
    _, kwargs = append_mock.call_args
    assert kwargs["role"] == "agent"
    assert kwargs["content"] == "核心吸引力是什么打动人的地方？"


async def test_skip_current_field_generation_failure_keeps_blank_state() -> None:
    # 下一问生成为空产（模型偏离格式）时，保留步骤 3 已提交的空白态（current_field=None），
    # 不影响已生效的 skipped 状态转移，也不落库消息、不报错。
    state = _initial_state()
    state["current_field"] = "genre"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(""))
    append_mock = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        with patch.object(guidance_agent.exploration_repo, "append_free_message", append_mock):
            result = await guidance_agent.skip_current_field(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    assert result["fields"]["genre"] == "skipped"
    assert result["current_field"] is None
    assert result["ready_to_settle"] is False
    append_mock.assert_not_awaited()


async def test_skip_current_field_next_question_quota_exceeded_keeps_blank_state() -> None:
    # 下一问生成这一步护栏 429 时，静默保留空白态（不影响已生效的 skipped 状态转移）；
    # 归纳步骤同样 429 —— provider.chat 全程不应被调用。
    state = _initial_state()
    state["current_field"] = "genre"
    provider = AsyncMock()
    quota_fail = AsyncMock(
        side_effect=ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    )
    with _orchestration(
        provider=provider, session_row=_session_row(state), check_quota=quota_fail
    ):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    assert result["current_field"] is None
    provider.chat.assert_not_awaited()
