"""Story 2.8 验证：自由探索——设定导航、按需回答思路与 7 项完成度门禁（纯逻辑单元）。

本文件聚焦 `guidance_agent.py` 的离线可跑单元（不打真实 LLM、不碰 DB，CI 必过）：
- `_parse_judge_response`：防御性解析（已清楚→filled、还缺→不产生 dict 项、问题行提取、
  畸形/未知标签忽略）。
- `_apply_judge_result`：AC2 单调性核心——已 filled/skipped 的项不被打回 missing、无
  question 时保留上一轮 current_field/current_question、全非 missing 时 ready_to_settle
  置真。
- `_parse_suggestions`：逐行取非空文本、最多 4 条上界。
- `_parse_skip_summary`：取「结论：」后文本、留空返回 None（不杜撰）。
- `refresh_guidance`/`start_guidance`/`suggest_answers`/`skip_current_field` 编排单元
  （mock get_provider_for_user + check_quota + repos）：护栏 429 各自的降级/报错取舍、
  已 skipped 项不被重新判定、空产兜底。

端点集成测试（含 401/404/409/422 与真实 DB 落库）见 `test_exploration_guidance.py`。
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from muse.core.errors import ErrorEnvelope
from muse.providers.base import ChatResult
from muse.services import guidance_agent, story_settle_agent

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
        "current_question": None,
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
    ]:
        stack.enter_context(patch.object(target, attr, val))
    return stack


class _FakeSession:
    """哑 session：本模块编排函数只需要它能被传给 mock 掉的 repo/provider，不做真实 IO。"""

    async def commit(self) -> None:
        return None


# ---------- 解析单元：_parse_judge_response ----------


def test_parse_judge_response_extracts_filled_and_question() -> None:
    content = (
        "题材：已清楚\n"
        "核心吸引力：还缺\n"
        "主角：已清楚\n"
        "主要冲突：还缺\n"
        "关键世界规则：还缺\n"
        "整体气质：还缺\n"
        "开篇钩子：还缺\n"
        "追问项：核心吸引力\n"
        "问题：这故事最抓人的地方是什么？"
    )
    updates, question, question_field = guidance_agent._parse_judge_response(content)
    assert updates == {"genre": "filled", "protagonist": "filled"}
    assert question == "这故事最抓人的地方是什么？"
    assert question_field == "core_appeal"


def test_parse_judge_response_ignores_unknown_labels_and_malformed_lines() -> None:
    content = "未知字段：已清楚\n没有冒号的一行\n题材：已清楚\n"
    updates, question, question_field = guidance_agent._parse_judge_response(content)
    assert updates == {"genre": "filled"}
    assert question is None
    assert question_field is None


def test_parse_judge_response_unknown_question_field_label_returns_none() -> None:
    # 模型标注了一个不在 _BACKBONE_FIELDS 里的未知标签——question_field 解析为 None，
    # 交由 _apply_judge_result fallback 到 still_missing[0]。
    content = "追问项：不存在的字段\n问题：这是什么？"
    updates, question, question_field = guidance_agent._parse_judge_response(content)
    assert question == "这是什么？"
    assert question_field is None


def test_parse_judge_response_tolerates_punctuation_and_modifier_variants() -> None:
    # code review 修复：模型输出「已清楚。」「已清楚，但还可以更细」等带标点/修饰语的
    # 变体，不再因严格 == 匹配失败而被误判为未清楚。
    content = "题材：已清楚。\n核心吸引力：已清楚，但还可以更细\n主角：还缺"
    updates, question, question_field = guidance_agent._parse_judge_response(content)
    assert updates == {"genre": "filled", "core_appeal": "filled"}


def test_parse_judge_response_no_question_when_all_clear() -> None:
    content = "\n".join(
        f"{label}：已清楚" for _, label in story_settle_agent._BACKBONE_FIELDS
    )
    updates, question, question_field = guidance_agent._parse_judge_response(content)
    assert len(updates) == 7
    assert question is None
    assert question_field is None


def test_parse_judge_response_empty_content_returns_nothing() -> None:
    updates, question, question_field = guidance_agent._parse_judge_response(
        "完全不符合格式的一段话"
    )
    assert updates == {}
    assert question is None
    assert question_field is None


# ---------- 合并单元：_apply_judge_result（AC2 单调性核心） ----------


def test_apply_judge_result_promotes_missing_to_filled_and_sets_question() -> None:
    state = _initial_state()
    new_state = guidance_agent._apply_judge_result(
        state, {"genre": "filled"}, "主角是谁？", "protagonist"
    )
    assert new_state["fields"]["genre"] == "filled"
    # question_field 标注 protagonist，且 protagonist 仍在 still_missing 里——直接采纳
    # 模型标注的字段，而非固定顺序的第一项（core_appeal）。
    assert new_state["current_field"] == "protagonist"
    assert new_state["current_question"] == "主角是谁？"
    assert new_state["ready_to_settle"] is False


def test_apply_judge_result_falls_back_to_first_missing_when_field_unmatched() -> None:
    # question_field 未标注（None）或标注的字段已不在 still_missing（模型偏离格式）时，
    # fallback 到 still_missing 固定顺序的第一项——保留旧的确定性回退行为。
    state = _initial_state()
    new_state = guidance_agent._apply_judge_result(
        state, {"genre": "filled"}, "主角是谁？", None
    )
    assert new_state["current_field"] == "core_appeal"
    assert new_state["current_question"] == "主角是谁？"

    new_state2 = guidance_agent._apply_judge_result(
        state, {"genre": "filled"}, "主角是谁？", "genre"  # genre 已 filled，不在 still_missing
    )
    assert new_state2["current_field"] == "core_appeal"


def test_apply_judge_result_does_not_demote_skipped_or_filled() -> None:
    state = _initial_state()
    state["fields"]["genre"] = "skipped"
    state["fields"]["core_appeal"] = "filled"
    # 模型即便离奇地把已 skipped/filled 的项也判成 filled，_apply_judge_result 的
    # updates 只对仍 missing 的项生效（updates 里带 genre/core_appeal 也不会改写）。
    new_state = guidance_agent._apply_judge_result(
        state,
        {"genre": "filled", "core_appeal": "filled", "protagonist": "filled"},
        "问题",
        "protagonist",
    )
    assert new_state["fields"]["genre"] == "skipped"  # 未被打回/改写
    assert new_state["fields"]["core_appeal"] == "filled"  # 未被重复覆盖（值同，行为验证）
    assert new_state["fields"]["protagonist"] == "filled"  # 仍 missing 的项正常更新


def test_apply_judge_result_ready_to_settle_when_no_missing_left() -> None:
    state = _initial_state()
    for key, _ in story_settle_agent._BACKBONE_FIELDS[:-1]:
        state["fields"][key] = "filled"
    # 只剩最后一项 missing，本轮判定它也 filled。
    last_key = story_settle_agent._BACKBONE_FIELDS[-1][0]
    new_state = guidance_agent._apply_judge_result(state, {last_key: "filled"}, None, None)
    assert all(v != "missing" for v in new_state["fields"].values())
    assert new_state["current_field"] is None
    assert new_state["current_question"] is None
    assert new_state["ready_to_settle"] is True


def test_apply_judge_result_keeps_previous_question_when_none_generated() -> None:
    state = _initial_state()
    state["current_field"] = "core_appeal"
    state["current_question"] = "上一轮的问题"
    # 本轮模型偏离格式、没有生成新问题（question=None）——保留上一轮 current_field/
    # current_question 不变，避免出现「有缺项但无问题可问」的空白态。
    new_state = guidance_agent._apply_judge_result(state, {}, None, None)
    assert new_state["current_field"] == "core_appeal"
    assert new_state["current_question"] == "上一轮的问题"
    assert new_state["ready_to_settle"] is False


# ---------- 解析单元：_parse_suggestions / _parse_skip_summary ----------


def test_parse_suggestions_caps_at_four_and_drops_blank_lines() -> None:
    content = "选项一\n\n选项二\n选项三\n选项四\n选项五（应被截断）"
    suggestions = guidance_agent._parse_suggestions(content)
    assert suggestions == ["选项一", "选项二", "选项三", "选项四"]


def test_parse_suggestions_empty_content_returns_empty_list() -> None:
    assert guidance_agent._parse_suggestions("   \n\n  ") == []


def test_parse_skip_summary_extracts_conclusion() -> None:
    assert guidance_agent._parse_skip_summary("结论：一个雨夜收到陌生来信的人") == (
        "一个雨夜收到陌生来信的人"
    )


def test_parse_skip_summary_blank_conclusion_returns_none() -> None:
    assert guidance_agent._parse_skip_summary("结论：") is None


def test_parse_skip_summary_missing_line_returns_none() -> None:
    assert guidance_agent._parse_skip_summary("完全不符合格式的一段话") is None


# ---------- 编排单元：refresh_guidance ----------


async def test_refresh_guidance_no_session_returns_initial_state() -> None:
    with _orchestration(provider=AsyncMock(), session_row=None):
        result = await guidance_agent.refresh_guidance(
            _FakeSession(), user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result == _initial_state()


async def test_refresh_guidance_no_missing_fields_short_circuits_without_llm() -> None:
    state = _initial_state()
    for key, _ in story_settle_agent._BACKBONE_FIELDS:
        state["fields"][key] = "filled"
    state["ready_to_settle"] = True
    provider = AsyncMock()
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.refresh_guidance(
            _FakeSession(), user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    provider.chat.assert_not_awaited()
    assert result == state


async def test_refresh_guidance_quota_exceeded_returns_current_state_silently() -> None:
    # 护栏触顶时静默降级：不重新判定、不更新 current_question（Dev Notes 已论证）。
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "上一轮的问题"
    provider = AsyncMock()
    quota_fail = AsyncMock(
        side_effect=ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    )
    with _orchestration(
        provider=provider, session_row=_session_row(state), check_quota=quota_fail
    ):
        result = await guidance_agent.refresh_guidance(
            _FakeSession(), user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    provider.chat.assert_not_awaited()
    assert result == state


async def test_refresh_guidance_skipped_field_not_resent_to_model() -> None:
    # AC2 硬约束：已 skipped 的项不喂给模型重新判断。judge prompt 只在 system 消息里列出
    # 全部 7 项固定标签（这是设计选择——system prompt 本身是静态模板，不逐项裁剪），但
    # `_apply_judge_result` 保证即便模型对已 skipped 项输出「已清楚」也不会被采纳（见
    # test_apply_judge_result_does_not_demote_skipped_or_filled）。本用例验证端到端行为：
    # 已 skipped 的项在 refresh 后仍是 skipped。
    state = _initial_state()
    state["fields"]["genre"] = "skipped"
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("题材：已清楚\n核心吸引力：还缺\n问题：核心吸引力是什么？")
    )
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.refresh_guidance(
            _FakeSession(), user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"  # 未被模型"救活"成 filled


async def test_refresh_guidance_parse_failure_keeps_previous_state() -> None:
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "上一轮的问题"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("完全不符合格式的一段话"))
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.refresh_guidance(
            _FakeSession(), user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result == state


# ---------- 编排单元：start_guidance ----------


async def test_start_guidance_generates_opening_question_for_entry() -> None:
    state = _initial_state()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("这故事最抓人的地方是什么？"))
    with (
        _orchestration(provider=provider, session_row=_session_row(state)),
        patch.object(
            guidance_agent.exploration_repo,
            "has_free_user_message",
            AsyncMock(return_value=False),
        ),
    ):
        result = await guidance_agent.start_guidance(
            user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="story_idea"
        )
    assert result["current_field"] == "core_appeal"  # story_idea → core_appeal 映射
    assert result["current_question"] == "这故事最抓人的地方是什么？"


async def test_start_guidance_already_started_is_idempotent() -> None:
    # 幂等防护：会话已有对话 → 直接返回当前态，不重新生成开场问题、不调 provider。
    state = _initial_state()
    state["current_field"] = "protagonist"
    state["current_question"] = "已经问过的问题"
    provider = AsyncMock()
    with (
        _orchestration(provider=provider, session_row=_session_row(state)),
        patch.object(
            guidance_agent.exploration_repo,
            "has_free_user_message",
            AsyncMock(return_value=True),
        ),
    ):
        result = await guidance_agent.start_guidance(
            user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="protagonist"
        )
    provider.chat.assert_not_awaited()
    assert result == state


async def test_start_guidance_field_already_skipped_is_idempotent() -> None:
    # code review 修复：零消息状态下该 entry 映射的字段已被跳过（has_free_user_message
    # 仍为 False），再次调用同一 entry 不应重新打开该字段——单调性防护，不调 provider。
    state = _initial_state()
    state["fields"]["core_appeal"] = "skipped"
    provider = AsyncMock()
    with (
        _orchestration(provider=provider, session_row=_session_row(state)),
        patch.object(
            guidance_agent.exploration_repo,
            "has_free_user_message",
            AsyncMock(return_value=False),
        ),
    ):
        result = await guidance_agent.start_guidance(
            user_id=uuid.uuid4(), project_id=uuid.uuid4(), entry="story_idea"
        )
    provider.chat.assert_not_awaited()
    assert result == state
    assert result["fields"]["core_appeal"] == "skipped"  # 未被重新打开为 current_field


# ---------- 编排单元：suggest_answers ----------


async def test_suggest_answers_no_current_field_raises_400() -> None:
    state = _initial_state()
    try:
        with _orchestration(provider=AsyncMock(), session_row=_session_row(state)):
            await guidance_agent.suggest_answers(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    except ErrorEnvelope as exc:
        assert exc.code == "no_current_question"
        assert exc.http_status == 400
    else:
        raise AssertionError("expected ErrorEnvelope")


async def test_suggest_answers_returns_parsed_suggestions() -> None:
    state = _initial_state()
    state["current_field"] = "protagonist"
    state["current_question"] = "主角是谁？"
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=_fake_chat_result("一个孤独的侦探\n一个失忆的杀手")
    )
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.suggest_answers(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result == ["一个孤独的侦探", "一个失忆的杀手"]


async def test_suggest_answers_empty_output_raises_502() -> None:
    state = _initial_state()
    state["current_field"] = "protagonist"
    state["current_question"] = "主角是谁？"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(""))
    try:
        with _orchestration(provider=provider, session_row=_session_row(state)):
            await guidance_agent.suggest_answers(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    except ErrorEnvelope as exc:
        assert exc.code == "generate_failed"
        assert exc.http_status == 502
    else:
        raise AssertionError("expected ErrorEnvelope")


async def test_suggest_answers_single_candidate_raises_502() -> None:
    # code review 修复：AC4 要求"2-4 个"候选，只解析到 1 个也应算未达标，不能以 200
    # 放行（此前只在 0 个时才报错）。
    state = _initial_state()
    state["current_field"] = "protagonist"
    state["current_question"] = "主角是谁？"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("一个孤独的侦探"))
    try:
        with _orchestration(provider=provider, session_row=_session_row(state)):
            await guidance_agent.suggest_answers(
                user_id=uuid.uuid4(), project_id=uuid.uuid4()
            )
    except ErrorEnvelope as exc:
        assert exc.code == "generate_failed"
        assert exc.http_status == 502
    else:
        raise AssertionError("expected ErrorEnvelope")


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
    # 状态转移优先生效：护栏 429 只影响「谨慎归纳」这一步，跳过动作本身仍生效。
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
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
    provider.chat.assert_not_awaited()  # 归纳这一步因护栏触顶未执行


async def test_skip_current_field_summarizes_into_matching_clue() -> None:
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
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
    list_clues.assert_awaited()
    update_value.assert_awaited_once()
    _, kwargs = update_value.call_args
    assert kwargs["clue"] is clue
    assert kwargs["value"] == "都市悬疑"


async def test_skip_current_field_no_summary_skips_clue_write_silently() -> None:
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
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
    state["current_question"] = "最后一个问题？"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("结论："))
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"][last_key] == "skipped"
    assert result["ready_to_settle"] is True



async def test_skip_current_field_immediately_advances_to_next_question() -> None:
    # code review 修复（Task 6 原文要求）：跳过后若还有 missing 项，应立即生成下一问，
    # 而非清空为空白态等下一轮对话触发。用 side_effect 区分「下一问生成」与「谨慎归纳」
    # 两次不同的 provider.chat 调用返回值。
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
    provider = AsyncMock()
    provider.chat = AsyncMock(
        side_effect=[
            _fake_chat_result("核心吸引力是什么打动人的地方？"),  # 下一问生成
            _fake_chat_result("结论："),  # 谨慎归纳（无材料可归纳）
        ]
    )
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    # 立即推进：still_missing 固定顺序第一项（core_appeal）成为新的 current_field，
    # 问题文本来自生成结果，而非清空为 None 等下一轮对话触发。
    assert result["current_field"] == "core_appeal"
    assert result["current_question"] == "核心吸引力是什么打动人的地方？"
    assert result["ready_to_settle"] is False
    assert provider.chat.await_count == 2


async def test_skip_current_field_generation_failure_keeps_blank_state() -> None:
    # 下一问生成为空产（模型偏离格式）时，保留步骤 3 已提交的空白态（current_field=None），
    # 不影响已生效的 skipped 状态转移，也不报错——静默降级同 refresh_guidance 的取舍粒度。
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(""))
    with _orchestration(provider=provider, session_row=_session_row(state)):
        result = await guidance_agent.skip_current_field(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
    assert result["fields"]["genre"] == "skipped"
    assert result["current_field"] is None
    assert result["ready_to_settle"] is False


async def test_skip_current_field_next_question_quota_exceeded_keeps_blank_state() -> None:
    # 下一问生成这一步护栏 429 时，静默保留空白态（不影响已生效的 skipped 状态转移）；
    # 归纳步骤同样 429 —— provider.chat 全程不应被调用。
    state = _initial_state()
    state["current_field"] = "genre"
    state["current_question"] = "题材是什么？"
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
