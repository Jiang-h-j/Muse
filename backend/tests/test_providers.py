"""Story 2.1 验证：LLMProvider 抽象 + DeepSeek 实现 + 工厂分派 + Provider 层记账（全 AC 覆盖）。

- 离线单元（不需 DB/Redis/真实 API，CI 必过）：
  - DeepSeekProvider.chat 解析 content/reasoning/usage（reasoning_content 存在与缺失两种，AC1）
  - DeepSeekProvider.stream 增量 kind 区分 content/reasoning + 流末 StreamUsage（AC2）
  - count_tokens 本地估算系数（粗估非扣费准据，AC1）
  - 工厂分派：托管 / BYOK deepseek / claude+custom 抛 provider_not_supported（AC6/AC7）
  - MeteredProvider 记账串联：API usage 的 total_tokens、正确 billing_path、Decimal cost（AC5）
- 可选真实契约（@requires_deepseek，CI 默认 skip）：真打一次 DeepSeek chat 验联通 + usage 非空。
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.core.errors import ErrorEnvelope
from muse.providers import factory
from muse.providers.base import ChatResult, StreamChunk, StreamUsage
from muse.providers.deepseek import DeepSeekProvider, compute_cost
from muse.providers.factory import MeteredProvider, get_provider_for_user
from tests.conftest import requires_deepseek

_DUMMY_KEY = "sk-test-dummy-key"
_DUMMY_BASE = "https://api.deepseek.com"


# ========== 离线：DeepSeekProvider.chat 解析（mock AsyncOpenAI，不打真实 API，AC1）==========


def _fake_chat_response(
    content: str, *, reasoning: str | None, prompt: int, completion: int, total: int
) -> MagicMock:
    """构造 mock 的 openai chat 非流式响应（choices[0].message + usage）。"""
    message = MagicMock()
    message.content = content
    # reasoning=None 模拟「该响应无 reasoning_content 字段」——用 spec 限制属性，getattr 兜底空串。
    if reasoning is None:
        del message.reasoning_content
    else:
        message.reasoning_content = reasoning
    usage = MagicMock()
    usage.prompt_tokens = prompt
    usage.completion_tokens = completion
    usage.total_tokens = total
    resp = MagicMock()
    resp.choices = [MagicMock(message=message)]
    resp.usage = usage
    return resp


async def test_chat_parses_content_reasoning_usage() -> None:
    # AC1：chat 返回结构含 content + reasoning + usage 三分量（reasoning_content 存在）。
    resp = _fake_chat_response(
        "  修仙世界的开场。  ", reasoning="  先想画面感。  ", prompt=17, completion=40, total=57
    )
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=resp)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        result = await provider.chat([{"role": "user", "content": "写个开场"}])

    assert isinstance(result, ChatResult)
    assert result.content == "修仙世界的开场。"  # strip 生效
    assert result.reasoning == "先想画面感。"
    assert result.prompt_tokens == 17
    assert result.completion_tokens == 40
    assert result.total_tokens == 57
    assert result.model == "deepseek-v4-pro"  # 默认思考档


async def test_chat_without_reasoning_content_returns_empty_reasoning() -> None:
    # AC1：响应无 reasoning_content 字段时 reasoning 取空串（不假设一定有，getattr 兜底）。
    resp = _fake_chat_response("正文", reasoning=None, prompt=5, completion=3, total=8)
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=resp)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        result = await provider.chat([{"role": "user", "content": "hi"}])
    assert result.reasoning == ""
    assert result.content == "正文"


async def test_chat_uses_explicit_model_override() -> None:
    # AC1：显式传 model（快档）覆盖默认思考档，结果 model 字段随之变。
    resp = _fake_chat_response("x", reasoning=None, prompt=1, completion=1, total=2)
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        create = AsyncMock(return_value=resp)
        mock_cls.return_value.chat.completions.create = create
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        result = await provider.chat(
            [{"role": "user", "content": "hi"}], model="deepseek-v4-flash"
        )
    assert result.model == "deepseek-v4-flash"
    # 传入 create 的 model 参数确为快档。
    assert create.await_args.kwargs["model"] == "deepseek-v4-flash"


# ========== 离线：DeepSeekProvider.stream 增量区分（AC2）==========


def _stream_chunk(
    *, content: str | None = None, reasoning: str | None = None, usage: MagicMock | None = None
) -> MagicMock:
    """构造 mock 流式 chunk：delta.content / delta.reasoning_content + 可选末尾 usage。"""
    delta = MagicMock()
    delta.content = content
    if reasoning is None:
        del delta.reasoning_content
    else:
        delta.reasoning_content = reasoning
    chunk = MagicMock()
    chunk.usage = usage
    # usage-only 末 chunk：choices 为空。
    chunk.choices = [] if (content is None and reasoning is None) else [MagicMock(delta=delta)]
    return chunk


class _FakeAsyncStream:
    """模拟 openai.AsyncStream：支持 async context manager + async 迭代 + close()。

    Story 2.3 Task 4 把 DeepSeekProvider.stream() 改为 `async with await create(...) as stream:`
    后，mock 必须模拟真实 AsyncStream 的协议：`__aenter__`/`__aexit__`（async with）+ `__aiter__`
    （async for）+ `close()`（__aexit__ 内调，释放连接）。旧的纯 async generator（`_aiter`）只有
    `aclose`、无 `__aenter__`/`close`，在新写法下必 AttributeError——故重构为本 fake（Task 4 ⚠️）。
    closed 标志供测试断言早断/正常收尾时连接被释放。
    """

    def __init__(self, chunks: list[MagicMock]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aenter__(self) -> "_FakeAsyncStream":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        await self.close()
        return False

    async def __aiter__(self):
        for item in self._chunks:
            yield item

    async def close(self) -> None:
        self.closed = True


def _fake_create(chunks: list[MagicMock]) -> AsyncMock:
    """构造 mock 的 `create`：await 后返回一个 _FakeAsyncStream（模拟 AsyncStream）。"""
    return AsyncMock(return_value=_FakeAsyncStream(chunks))


async def test_stream_distinguishes_reasoning_and_content_then_usage() -> None:
    # AC2：流式增量 kind 正确区分 reasoning vs content；流末产 StreamUsage（API usage）。
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 20
    usage.total_tokens = 30
    chunks = [
        _stream_chunk(reasoning="思考中"),
        _stream_chunk(content="正文一"),
        _stream_chunk(content="正文二"),
        _stream_chunk(usage=usage),  # 末 chunk：仅 usage、choices 空
    ]
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = _fake_create(chunks)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        events = [ev async for ev in provider.stream([{"role": "user", "content": "写"}])]

    chunks_out = [e for e in events if isinstance(e, StreamChunk)]
    usages_out = [e for e in events if isinstance(e, StreamUsage)]
    assert [(c.kind, c.delta) for c in chunks_out] == [
        ("reasoning", "思考中"),
        ("content", "正文一"),
        ("content", "正文二"),
    ]
    assert len(usages_out) == 1
    assert usages_out[0].total_tokens == 30
    assert usages_out[0].estimated is False  # API 回报，非本地兜底


async def test_stream_falls_back_to_local_estimate_when_no_api_usage() -> None:
    # AC2/AC5：服务端末 chunk 未回 usage 时，流末用 count_tokens 兜底估算并标 estimated=True。
    chunks = [_stream_chunk(content="正文")]  # 无 usage chunk
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = _fake_create(chunks)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        events = [ev async for ev in provider.stream([{"role": "user", "content": "写"}])]
    usages = [e for e in events if isinstance(e, StreamUsage)]
    assert len(usages) == 1
    assert usages[0].estimated is True  # 兜底估算口径


async def test_stream_closes_underlying_stream_on_full_consume() -> None:
    # Story 2.3 Task 4：正常消费完 → async with 的 __aexit__ 释放底层连接（close 被调）。
    usage = MagicMock()
    usage.prompt_tokens, usage.completion_tokens, usage.total_tokens = 1, 2, 3
    fake_stream = _FakeAsyncStream([_stream_chunk(content="正文"), _stream_chunk(usage=usage)])
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=fake_stream)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        _ = [ev async for ev in provider.stream([{"role": "user", "content": "写"}])]
    assert fake_stream.closed is True  # 连接已释放，不泄漏


async def test_stream_closes_underlying_stream_on_early_break() -> None:
    # Story 2.3 Task 4/陷阱⑦：消费方早断（只取一块就 break）→ generator aclose →
    # async with __aexit__ 仍执行 → 底层流被 close，连接不泄漏（闭合 2.1 defer①）。
    fake_stream = _FakeAsyncStream(
        [_stream_chunk(content="一"), _stream_chunk(content="二"), _stream_chunk(content="三")]
    )
    with patch("muse.providers.deepseek.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=fake_stream)
        provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        agen = provider.stream([{"role": "user", "content": "写"}])
        async for _ev in agen:
            break  # 早断：只取第一块就停
        await agen.aclose()  # 模拟 SSE 客户端断连触发的 generator 关闭
    assert fake_stream.closed is True  # 早断路径也释放连接


# ========== 离线：count_tokens 本地估算（粗估非扣费准据，AC1）==========


def test_count_tokens_local_estimate_coefficients() -> None:
    # CJK×0.6 + 其余×0.3（spike P1 系数）。粗估、不作扣费准据（扣费用 API usage）。
    provider = DeepSeekProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
    # 4 个 CJK：4*0.6 = 2.4 → round = 2
    assert provider.count_tokens("修仙世界") == round(4 * 0.6)
    # 10 个非 CJK：10*0.3 = 3.0 → 3
    assert provider.count_tokens("abcdefghij") == round(10 * 0.3)
    # 混排：2 CJK + 3 非 CJK = 1.2 + 0.9 = 2.1 → 2
    assert provider.count_tokens("修仙abc") == round(2 * 0.6 + 3 * 0.3)


# ========== 离线：compute_cost 全程 Decimal（陷阱②，AC5）==========


def test_compute_cost_is_decimal() -> None:
    # cost 全程 Decimal 不转 float（钱不用浮点）。pro 档 input 4/1M + output 16/1M。
    cost = compute_cost("deepseek-v4-pro", 1_000_000, 1_000_000)
    assert isinstance(cost, Decimal)
    assert cost == Decimal("20")
    # 未知模型兜底 0（配置漂移时不静默虚计费，便于审计发现）。
    assert compute_cost("unknown-model", 100, 100) == Decimal("0")


# ========== 离线：工厂分派（mock byok_service，AC6/AC7）==========


def _binding(bound: bool, provider: str | None = None) -> dict[str, object]:
    return {"bound": bound, "provider": provider, "masked_key": None}


async def test_factory_unbound_user_gets_hosted_provider() -> None:
    # AC6：未绑定 BYOK → 托管 DeepSeekProvider（billing_path="hosted"）。
    uid = uuid.uuid4()
    with patch.object(
        factory.byok_service,
        "get_binding_status",
        new=AsyncMock(return_value=_binding(False)),
    ):
        provider = await get_provider_for_user(AsyncMock(), uid)
    assert isinstance(provider, MeteredProvider)
    assert provider._billing_path == "hosted"
    assert isinstance(provider._inner, DeepSeekProvider)


async def test_factory_byok_deepseek_gets_byok_provider() -> None:
    # AC6：已绑定 deepseek → 解密取明文构造 DeepSeekProvider（billing_path="byok"）。
    uid = uuid.uuid4()
    with (
        patch.object(
            factory.byok_service,
            "get_binding_status",
            new=AsyncMock(return_value=_binding(True, "deepseek")),
        ),
        patch.object(
            factory.byok_service,
            "get_decrypted_key_for_user",
            new=AsyncMock(return_value="sk-user-byok-key"),
        ) as get_key,
    ):
        provider = await get_provider_for_user(AsyncMock(), uid)
    assert isinstance(provider, MeteredProvider)
    assert provider._billing_path == "byok"
    get_key.assert_awaited_once()  # 确定走 BYOK 才解密（陷阱③）


@pytest.mark.parametrize("bad_provider", ["claude", "custom"])
async def test_factory_unsupported_provider_raises(bad_provider: str) -> None:
    # AC7：claude/custom 绑定 → 抛 provider_not_supported（不静默失败、不误当 DeepSeek）。
    uid = uuid.uuid4()
    with (
        patch.object(
            factory.byok_service,
            "get_binding_status",
            new=AsyncMock(return_value=_binding(True, bad_provider)),
        ),
        patch.object(
            factory.byok_service, "get_decrypted_key_for_user", new=AsyncMock()
        ) as get_key,
        pytest.raises(ErrorEnvelope) as exc_info,
    ):
        await get_provider_for_user(AsyncMock(), uid)
    assert exc_info.value.code == "provider_not_supported"
    assert exc_info.value.http_status == 400
    # 不支持的 provider 不该解密取 key（未确定要构造客户端）。
    get_key.assert_not_awaited()


# ========== 离线：MeteredProvider 记账串联（API usage/billing_path/Decimal cost，AC5）==========


async def test_metered_chat_records_usage_with_api_tokens_and_decimal_cost() -> None:
    # AC5：chat 完成 → record_usage 被以 API usage 的 total_tokens、正确 billing_path、
    # Decimal cost 调用。
    uid = uuid.uuid4()
    inner = MagicMock()
    inner.chat = AsyncMock(
        return_value=ChatResult(
            content="正文",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="deepseek-v4-pro",
        )
    )
    with patch.object(
        factory.usage_service, "record_usage", new=AsyncMock()
    ) as record:
        metered = MeteredProvider(
            inner,
            session=AsyncMock(),
            user_id=uid,
            billing_path="hosted",
            cost_fn=compute_cost,
        )
        result = await metered.chat([{"role": "user", "content": "写"}])

    assert result.total_tokens == 150
    record.assert_awaited_once()
    kwargs = record.await_args.kwargs
    assert kwargs["user_id"] == uid
    assert kwargs["billing_path"] == "hosted"
    # total_tokens 用 API 回报值（非本地估算，spike P1）。
    assert kwargs["total_tokens"] == 150
    assert kwargs["prompt_tokens"] == 100
    assert kwargs["completion_tokens"] == 50
    # cost 是 Decimal（陷阱②）：pro 档 (4*100 + 16*50)/1M。
    assert isinstance(kwargs["cost"], Decimal)
    assert kwargs["cost"] == compute_cost("deepseek-v4-pro", 100, 50)
    assert kwargs["model_name"] == "deepseek-v4-pro"


async def test_metered_stream_records_usage_on_stream_usage_event() -> None:
    # AC5：流式在末尾 StreamUsage 到达时记账；透传所有事件给消费方。
    uid = uuid.uuid4()

    async def _inner_stream(*args, **kwargs):
        yield StreamChunk(delta="正文", kind="content")
        yield StreamUsage(
            prompt_tokens=10, completion_tokens=20, total_tokens=30, model="deepseek-v4-flash"
        )

    inner = MagicMock()
    inner.stream = _inner_stream
    with patch.object(
        factory.usage_service, "record_usage", new=AsyncMock()
    ) as record:
        metered = MeteredProvider(
            inner,
            session=AsyncMock(),
            user_id=uid,
            billing_path="byok",
            cost_fn=compute_cost,
        )
        events = [ev async for ev in metered.stream([{"role": "user", "content": "写"}])]

    # 事件透传：1 个 content chunk + 1 个 usage。
    assert sum(isinstance(e, StreamChunk) for e in events) == 1
    assert sum(isinstance(e, StreamUsage) for e in events) == 1
    record.assert_awaited_once()
    kwargs = record.await_args.kwargs
    assert kwargs["billing_path"] == "byok"
    assert kwargs["total_tokens"] == 30
    assert isinstance(kwargs["cost"], Decimal)


# ========== 可选真实契约（@requires_deepseek，CI 默认 skip，AC1）==========


@requires_deepseek
async def test_real_deepseek_chat_contract() -> None:
    # 真打一次 DeepSeek chat（快档）：验联通 + usage 非空。CI 默认 skip（无 key），本地可跑。
    # max_tokens 给足 512：flash 是**推理模型**，reasoning_content 先吃 token 预算——预算过小
    # （实测 100）会让思考占满、content 返空（非 bug，是推理档特性，见 Completion Notes）。
    from muse.core.settings import get_settings

    settings = get_settings()
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    result = await provider.chat(
        [{"role": "user", "content": "用一句话描述修仙世界开场。"}],
        model=settings.deepseek_model_fast,
        max_tokens=512,
    )
    assert result.content  # 非空正文
    assert result.total_tokens > 0  # usage 非空（记账源）
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens


@requires_deepseek
async def test_real_deepseek_stream_contract() -> None:
    # Story 2.3 Task 4（闭合 2.1 流式 defer②）：真打一次 DeepSeek stream，断言收到正文 delta +
    # 末尾 StreamUsage 非空且 estimated=False——坐实 stream_options={"include_usage": True} 在真实
    # API 生效（2.1 只离线 mock 验过两分支）。max_tokens 给足 512 避免推理档挤空正文（陷阱⑥）。
    from muse.core.settings import get_settings

    settings = get_settings()
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    events = [
        ev
        async for ev in provider.stream(
            [{"role": "user", "content": "用一句话描述修仙世界开场。"}],
            model=settings.deepseek_model_fast,
            max_tokens=512,
        )
    ]
    content = "".join(
        e.delta for e in events if isinstance(e, StreamChunk) and e.kind == "content"
    )
    usages = [e for e in events if isinstance(e, StreamUsage)]
    assert content  # 收到非空正文 delta
    assert len(usages) == 1  # 末尾恰一个 StreamUsage
    assert usages[0].total_tokens > 0  # 真实 usage 非空（记账源）
    assert usages[0].estimated is False  # 服务端确回 usage（include_usage 真实生效）
