"""Story 3.3 验证：探索整理为 12 字段故事设定候选卡（AC 全覆盖）。

本 story 把 2.5/2.7 打通的 settle 管道 skeleton 的占位凝练替换为真实 LLM 12 字段凝练，
**emit-only**（候选卡经 SSE result 返回、不写 story_bible，持久化归 3.4/3.5）。

- 解析/组装单元（离线）：_parse_settle_response 防御性解析、genre 驱动特化、空产判定。
- 编排单元（离线，mock get_provider_for_user + check_quota + repos，不打真实 LLM，CI 必过）：
  - guided happy：读引导答案 → 凝练 → 12 字段候选卡；⑫=预置 style_profile。
  - free happy：读对话 + 有效线索 → 凝练；空串 preset 槽不算材料。
  - genre 驱动特化（AC4）：修仙 → power_system 有值、其余特化 None。
  - 特化留空不阻塞（AC3）：主干填、特化全空 → 正常出卡。
  - ⑫ style_profile 消费（AC2）：story_bible 有值 → ⑫=该值；无行/None → ⑫ None。
  - 护栏 429：check_quota 触顶 → 不调 provider。
  - 空态 400 settle_empty：无会话 / guided 无答案 / free 无消息且无有效线索
    → 不过护栏、不调 provider。
  - 空产 502 generate_failed：主干全空 → 抛错。
  - 租户 404：get_owned_project None → 404，先于一切。
  - prompt 契约：system 含 genre 判定 + 固定字段格式 + 去 AI 味；user 携材料。
- worker 端到端（@requires_db @requires_redis）：settle_exploration 调服务 → SSE result 携真实
  12 字段 profile（mock 服务，验证 worker 编排 + payload 形态，不打真实 LLM）。
"""

import json
import uuid
from collections.abc import Callable
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis

from muse.core import sse
from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.providers.base import ChatResult
from muse.services import story_settle_agent
from muse.tasks import worker as worker_mod
from tests.conftest import requires_db, requires_redis

# ---- 共享 fixture/helper ----


def _project(mode: str = "guided") -> MagicMock:
    p = MagicMock()
    p.mode = mode
    return p


def _fake_chat_result(content: str) -> ChatResult:
    return ChatResult(
        content=content,
        prompt_tokens=10,
        completion_tokens=10,
        total_tokens=20,
        model="deepseek-v4-flash",
    )


def _guided_answer(question: str, answer: str) -> MagicMock:
    m = MagicMock()
    m.question = question
    m.answer = answer
    return m


def _free_message(role: str, content: str) -> MagicMock:
    m = MagicMock()
    m.role = role
    m.content = content
    return m


def _clue(label: str, value: str) -> MagicMock:
    m = MagicMock()
    m.label = label
    m.value = value
    return m


def _session(mode: str = "guided") -> MagicMock:
    s = MagicMock()
    s.mode = mode
    s.id = uuid.uuid4()
    return s


class _FakeSessionCtx:
    """可 async with 的哑 session（repo/provider 均 mock，session 本身不被真正使用）。"""

    async def __aenter__(self) -> "object":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _fake_session_maker() -> Callable[[], object]:
    return lambda: _FakeSessionCtx()


# 模型「理想」凝练输出：修仙题材，主干 7 全填 + power_system（特化激活），其余特化行省略。
_GOOD_LLM_OUTPUT = (
    "题材：修仙\n"
    "核心吸引力：小人物逆袭登顶的爽感\n"
    "主角：林凡，想变强证明自己，但骨子里怕失去在意的人\n"
    "主要冲突：与压制他的宗门大能对抗；反派同样求长生却不择手段\n"
    "关键世界规则：灵气复苏的现代都市，修炼分境界\n"
    "整体气质：热血\n"
    "开篇钩子：废物觉醒神秘传承\n"
    "力量体系：练气-筑基-金丹-元婴"
)


def _orchestration(
    *,
    mode: str = "guided",
    provider: object,
    session: object = "__default__",
    guided_answers: list | None = None,
    free_messages: list | None = None,
    clues: list | None = None,
    bible: object = None,
    check_quota: object = None,
    get_provider: object = "__default__",
    get_owned_project: object = "__default__",
) -> ExitStack:
    """进入 settle_into_profile 依赖的一组 patch，返回已进入的 ExitStack（with 内自动退出）。

    provider/repos/quota/session_maker 全 mock，离线可跑（不打真实 LLM、不碰 DB）。
    """
    sess = _session(mode) if session == "__default__" else session
    owned = _project(mode) if get_owned_project == "__default__" else get_owned_project
    provider_mock = (
        AsyncMock(return_value=provider) if get_provider == "__default__" else get_provider
    )
    stack = ExitStack()
    for target, attr, val in [
        (story_settle_agent.project_repo, "get_owned_project", AsyncMock(return_value=owned)),
        (
            story_settle_agent.exploration_repo,
            "get_session_by_project",
            AsyncMock(return_value=sess),
        ),
        (
            story_settle_agent.exploration_repo,
            "list_guided_answers_by_session",
            AsyncMock(return_value=guided_answers or []),
        ),
        (
            story_settle_agent.exploration_repo,
            "list_free_messages_by_session",
            AsyncMock(return_value=free_messages or []),
        ),
        (
            story_settle_agent.story_clue_repo,
            "list_clues_by_session",
            AsyncMock(return_value=clues or []),
        ),
        (
            story_settle_agent.story_bible_repo,
            "get_by_project",
            AsyncMock(return_value=bible),
        ),
        (
            story_settle_agent.usage_service,
            "check_quota",
            check_quota if check_quota is not None else AsyncMock(),
        ),
        (story_settle_agent, "get_provider_for_user", provider_mock),
        (story_settle_agent, "async_session_maker", _fake_session_maker()),
    ]:
        stack.enter_context(patch.object(target, attr, new=val))
    return stack


# ========== 离线：_parse_settle_response 解析 + 组装 ==========


def test_parse_extracts_known_fields_and_skips_garbage() -> None:
    messy = (
        "好的以下是设定\n"  # 无分隔符旁白，忽略
        "题材：都市\n"
        "核心吸引力：\n"  # 空值忽略
        "未知字段：应忽略\n"
        "主角：张三\n"
    )
    parsed = story_settle_agent._parse_settle_response(messy)
    assert parsed["genre"] == "都市"
    assert parsed["protagonist"] == "张三"
    assert "core_appeal" not in parsed  # 空值不计
    assert all(k in {kk for kk, _ in story_settle_agent._LLM_FIELDS} for k in parsed)


def test_parse_tolerates_markdown_and_numbering_prefixes() -> None:
    # code review 加固：LLM 违背 prompt 加 markdown/编号装饰仍须命中标签，不误判空产。
    decorated = (
        "**题材**：都市\n"  # markdown 加粗
        "1. 核心吸引力：职场爽感\n"  # 阿拉伯编号
        "- 主角：李明\n"  # 列表符
        "*关键世界规则*：现代都市\n"  # 星号包裹
        "② 开篇钩子：被裁员那天\n"  # 圈号前缀
    )
    parsed = story_settle_agent._parse_settle_response(decorated)
    assert parsed["genre"] == "都市"
    assert parsed["core_appeal"] == "职场爽感"
    assert parsed["protagonist"] == "李明"
    assert parsed["world_rules"] == "现代都市"
    assert parsed["opening_hook"] == "被裁员那天"


def test_parse_genre_driven_specialization() -> None:
    # 修仙输出只含 power_system，其余特化不在输出 → 只解析出 power_system。
    parsed = story_settle_agent._parse_settle_response(_GOOD_LLM_OUTPUT)
    assert parsed["power_system"] == "练气-筑基-金丹-元婴"
    assert "golden_finger" not in parsed
    assert "romance_line" not in parsed
    assert "faction_landscape" not in parsed


def test_parse_empty_when_no_backbone() -> None:
    parsed = story_settle_agent._parse_settle_response("完全不符合格式的一段话")
    assert not any(k in parsed for k, _ in story_settle_agent._BACKBONE_FIELDS)


def test_format_guided_material_skips_empty_answers() -> None:
    out = story_settle_agent._format_guided_material(
        [_guided_answer("你想写什么？", "修仙"), _guided_answer("主角？", "")]
    )
    assert "修仙" in out
    assert out.count("答：") == 1  # 空答案被跳过


def test_format_free_material_filters_blank_clue_slots() -> None:
    # 空串 preset 槽不算有效材料（AC5 空态判据）；非空线索 + 对话都进材料。
    out = story_settle_agent._format_free_material(
        [_free_message("user", "我想写个修仙故事"), _free_message("agent", "")],
        [_clue("最初的念头", ""), _clue("主角", "林凡")],
    )
    assert "我想写个修仙故事" in out
    assert "林凡" in out
    assert "最初的念头" not in out  # 空串槽被过滤


def test_format_free_material_empty_when_only_blank_slots() -> None:
    # 只有自动建的空 preset 槽、没真聊过 → 材料为空（不会漏过空态门禁白烧 LLM）。
    out = story_settle_agent._format_free_material(
        [], [_clue("最初的念头", ""), _clue("主角", "")]
    )
    assert out.strip() == ""


# ========== 离线：settle_into_profile 编排单元 ==========


async def test_settle_guided_happy_builds_card() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_GOOD_LLM_OUTPUT))
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("你想写什么故事？", "一个修仙逆袭的故事")],
        bible=None,
    ):
        card = await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert card["genre"] == "修仙"
    assert card["power_system"] == "练气-筑基-金丹-元婴"
    assert card["golden_finger"] is None  # 特化未激活
    assert card["style_profile"] is None  # 无 story_bible 行
    # 主干 7 恒有键
    for key, _ in story_settle_agent._BACKBONE_FIELDS:
        assert key in card


async def test_settle_free_happy_reads_messages_and_clues() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    captured: dict[str, object] = {}

    async def _capture_chat(messages, **kwargs):
        captured["messages"] = messages
        return _fake_chat_result(_GOOD_LLM_OUTPUT)

    provider = MagicMock()
    provider.chat = _capture_chat
    with _orchestration(
        mode="free",
        provider=provider,
        session=_session("free"),
        free_messages=[_free_message("user", "我想写修仙")],
        clues=[_clue("主角", "林凡")],
        bible=None,
    ):
        card = await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert card["genre"] == "修仙"
    # user 材料含对话 + 线索
    user_msg = captured["messages"][1]["content"]
    assert "我想写修仙" in user_msg
    assert "林凡" in user_msg


async def test_settle_consumes_existing_style_profile() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(_GOOD_LLM_OUTPUT))
    bible = MagicMock()
    bible.style_profile = "人称：第三人称限知\n语气：冷峻"
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("题材？", "修仙")],
        bible=bible,
    ):
        card = await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    # ⑫ 读既有 style_profile（不重抽、不覆盖）
    assert card["style_profile"] == "人称：第三人称限知\n语气：冷峻"


async def test_settle_specialized_empty_not_blocking() -> None:
    # 主干填、特化全空（都市题材无特化行）→ 正常出卡（AC3）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    urban = (
        "题材：都市\n核心吸引力：职场爽文\n主角：李明，想升职\n主要冲突：与上司斗\n"
        "关键世界规则：现代都市\n整体气质：轻松\n开篇钩子：被裁员那天"
    )
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result(urban))
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("题材？", "都市")],
        bible=None,
    ):
        card = await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert card["genre"] == "都市"
    for key in ("power_system", "golden_finger", "romance_line", "faction_landscape"):
        assert card[key] is None


async def test_settle_quota_exceeded_blocks_before_provider() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    quota_err = ErrorEnvelope(code="quota_exceeded", message="额度已用完", http_status=429)
    provider = AsyncMock()
    provider.chat = AsyncMock()
    get_provider = AsyncMock(return_value=provider)
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("题材？", "修仙")],
        check_quota=AsyncMock(side_effect=quota_err),
        get_provider=get_provider,
    ):
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert exc.value.code == "quota_exceeded"
    get_provider.assert_not_awaited()  # 护栏在前
    provider.chat.assert_not_awaited()


async def test_settle_empty_material_blocks_before_quota_and_provider() -> None:
    # guided 无答案 → 材料空 → 400 settle_empty，不过护栏、不调 provider（AC3/AC5 空态短路）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock()
    check_quota = AsyncMock()
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[],
        check_quota=check_quota,
    ):
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert exc.value.code == "settle_empty"
    assert exc.value.http_status == 400
    check_quota.assert_not_awaited()
    provider.chat.assert_not_awaited()


async def test_settle_no_session_blocks_400() -> None:
    # 连探索会话都没建 → 材料空 → 400 settle_empty（不 500）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock()
    with _orchestration(mode="guided", provider=provider, session=None):
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert exc.value.code == "settle_empty"


async def test_settle_empty_produce_raises_generate_failed() -> None:
    # 模型完全跑偏（主干一个都没解析到）→ 502 generate_failed（材料非空、过了护栏）。
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=_fake_chat_result("一堆没有任何标签的胡言乱语"))
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("题材？", "修仙")],
    ):
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert exc.value.code == "generate_failed"
    assert exc.value.http_status == 502


async def test_settle_tenant_guard_404_before_all() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    provider = AsyncMock()
    provider.chat = AsyncMock()
    check_quota = AsyncMock()
    with _orchestration(
        mode="guided",
        provider=provider,
        get_owned_project=None,
        check_quota=check_quota,
    ):
        with pytest.raises(ErrorEnvelope) as exc:
            await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    assert exc.value.http_status == 404
    check_quota.assert_not_awaited()
    provider.chat.assert_not_awaited()


async def test_settle_prompt_contract() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    captured: dict[str, object] = {}

    async def _capture_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return _fake_chat_result(_GOOD_LLM_OUTPUT)

    provider = MagicMock()
    provider.chat = _capture_chat
    with _orchestration(
        mode="guided",
        provider=provider,
        guided_answers=[_guided_answer("题材？", "修仙")],
    ):
        await story_settle_agent.settle_into_profile(user_id=uid, project_id=pid)
    system = captured["messages"][0]["content"]
    assert captured["messages"][0]["role"] == "system"
    assert "题材" in system  # genre 判定
    assert "标签：内容" in system  # 固定格式契约
    assert "AI" in system or "书面腔" in system  # 去 AI 味要求
    # 快档 + 足量 max_tokens
    assert captured["kwargs"]["max_tokens"] == story_settle_agent._MAX_TOKENS


# ========== worker 端到端（settle_exploration 调服务 → SSE result）==========


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


async def _subscribe(redis: Redis, channel: str):
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=5.0)
    return pubsub


async def _drain(pubsub) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    saw_terminal = False
    while True:
        timeout = 1.0 if saw_terminal else 5.0
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if msg is None:
            break
        payload = json.loads(msg["data"])
        events.append((payload["event"], payload["data"]))
        if payload["event"] in (sse.EVENT_RESULT, sse.EVENT_ERROR):
            saw_terminal = True
    return events


@requires_db
@requires_redis
async def test_worker_settle_publishes_real_profile() -> None:
    # settle_exploration 调（mock 的）凝练服务 → progress×3 + result 携真实 12 字段 profile。
    task_id = uuid.uuid4().hex
    fake_card = {
        "genre": "修仙",
        "core_appeal": "逆袭爽感",
        "protagonist": "林凡",
        "main_conflict": "对抗宗门",
        "world_rules": "灵气复苏",
        "overall_tone": "热血",
        "opening_hook": "废物觉醒",
        "power_system": "练气-筑基",
        "golden_finger": None,
        "romance_line": None,
        "faction_landscape": None,
        "style_profile": None,
    }
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        with patch.object(
            worker_mod.story_settle_agent,
            "settle_into_profile",
            new=AsyncMock(return_value=fake_card),
        ):
            await worker_mod.settle_exploration(
                {"pub_redis": pub}, task_id, str(uuid.uuid4()), str(uuid.uuid4())
            )
        events = await _drain(pubsub)
    finally:
        await pubsub.unsubscribe(sse.task_channel(task_id))
        await pubsub.aclose()
        await sub.aclose()
        await pub.delete(sse.task_snapshot_key(task_id))
        await pub.aclose()

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "progress", "result"]
    result_data = [d for e, d in events if e == "result"][0]
    assert result_data["taskId"] == task_id
    assert result_data["status"] == "settle_ready"
    # profile 为 camelCase 12 字段
    profile = result_data["profile"]
    assert profile["genre"] == "修仙"
    assert profile["powerSystem"] == "练气-筑基"
    assert profile["goldenFinger"] is None
    assert profile["styleProfile"] is None


@requires_db
@requires_redis
async def test_worker_settle_error_publishes_error() -> None:
    # 服务抛 ErrorEnvelope（空态 400）→ worker 透传 code/message 到 SSE error、无 result。
    task_id = uuid.uuid4().hex
    pub = _redis()
    sub = _redis()
    pubsub = await _subscribe(sub, sse.task_channel(task_id))
    try:
        with patch.object(
            worker_mod.story_settle_agent,
            "settle_into_profile",
            new=AsyncMock(side_effect=story_settle_agent._settle_empty()),
        ):
            with pytest.raises(ErrorEnvelope):
                await worker_mod.settle_exploration(
                    {"pub_redis": pub}, task_id, str(uuid.uuid4()), str(uuid.uuid4())
                )
        events = await _drain(pubsub)
    finally:
        await pubsub.unsubscribe(sse.task_channel(task_id))
        await pubsub.aclose()
        await sub.aclose()
        await pub.delete(sse.task_snapshot_key(task_id))
        await pub.aclose()

    kinds = [e for e, _ in events]
    assert kinds == ["progress", "progress", "error"]
    error_data = [d for e, d in events if e == "error"][0]
    assert error_data["code"] == "settle_empty"
