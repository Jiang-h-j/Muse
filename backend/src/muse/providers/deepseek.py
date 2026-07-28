"""DeepSeekProvider：LLMProvider 的 DeepSeek 默认实现（Story 2.1，AR12/焦点一）。

**本模块是全项目唯一允许 import openai 的地方**（陷阱①，Enforcement architecture.md:341/356）。
DeepSeek 走 OpenAI SDK 兼容接口，仅切 base_url 指向 https://api.deepseek.com（spike P1 实测确认）。

全栈 async（陷阱④）：用 AsyncOpenAI 而非 OpenAI（spike 用同步仅为快速验证联通）；绝不在 async
路径跑同步阻塞调用，否则卡事件循环拖垮并发。

记账（AC5）不在本类内做——本类只如实返回 usage，由工厂层（factory.py）包裹调用后统一 record_usage，
保证「记账埋点统一在 Provider 层」的同时不让每个 Provider 子类各写一遍记账（换模型不改记账逻辑）。
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.providers.base import (
    ChatResult,
    LLMProvider,
    Message,
    StreamChunk,
    StreamEvent,
    StreamUsage,
)

# 本地 token 估算系数（spike P1）：CJK 汉字 ≈ 0.6 token/字、其余 ≈ 0.3 token/字。
# **仅供调用前粗估、不作扣费准据**（实测偏差 +23.5%，扣费一律用 API usage）。
_CJK_TOKEN_RATIO = 0.6
_OTHER_TOKEN_RATIO = 0.3
# CJK 统一表意文字区间（与 spike 一致）：用于粗估中英文混排的 token 体量。
_CJK_START = "一"
_CJK_END = "鿿"

# DeepSeek 双档单价，单位 = 元 / 1M token（便于对照官方定价页），(input, output)。
# **占位值，dev 填于 2026-07-27**：deepseek-v4-pro / deepseek-v4-flash 为 architecture.md:196
# 定的档位名，真实单价以 DeepSeek 官方定价为准——上线前须核对并更新本常量（改此处即可、
# 不动业务逻辑）。cost 全程 Decimal（陷阱②：钱不用浮点，字面量用 Decimal("...") 不用 float）。
_PRICE_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "deepseek-v4-pro": (Decimal("4"), Decimal("16")),
    "deepseek-v4-flash": (Decimal("1"), Decimal("2")),
}
_ONE_MILLION = Decimal("1000000")


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """按 DeepSeek 单价算本次调用成本（元），**全程 Decimal 不转 float**（陷阱②）。

    cost = (input 单价 × prompt_tokens + output 单价 × completion_tokens) / 1M。
    未知模型名兜底 0 成本（防御性）——本 story 只用自有 settings 的两档名、恒命中，
    未知名意味着配置漂移，落库 0 成本便于事后审计发现（不静默虚计费）。
    """
    input_price, output_price = _PRICE_PER_MILLION_TOKENS.get(
        model, (Decimal("0"), Decimal("0"))
    )
    return (input_price * prompt_tokens + output_price * completion_tokens) / _ONE_MILLION


class DeepSeekProvider(LLMProvider):
    """DeepSeek 实现：构造时注入 api_key/base_url（托管传 settings.deepseek_api_key，

    BYOK 传 byok_service.get_decrypted_key_for_user 的明文——明文只在内存传入，绝不 log/落库/
    出边界，延续 1.7 安全红线）。default_model 缺省用思考档（起草/审查为主场景）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        default_model: str | None = None,
        fast_model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        # 默认档 = 思考档（deepseek-v4-pro）；调用方可按需在 chat/stream 传 model 覆盖为快档。
        self._default_model = default_model or settings.deepseek_model_thinking
        self._fast_model = fast_model or settings.deepseek_model_fast

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """非流式对话（AC1）：取 content + reasoning_content（双档均可能有）+ API usage 三分量。"""
        used_model = model or self._default_model
        resp = await self._client.chat.completions.create(
            model=used_model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            max_tokens=max_tokens,
            stream=False,
        )
        choice = resp.choices[0] if resp.choices else None
        if choice is None:
            # 内容过滤/异常态下 OpenAI/DeepSeek 可能返回空 choices——与 stream 的
            # `if not chunk.choices` 防御一致，抛结构化错误而非裸 IndexError。
            raise ErrorEnvelope(
                code="generate_failed",
                message="模型未返回有效内容，请稍后重试。",
                detail={"reason": "empty_choices"},
                http_status=502,
            )
        msg = choice.message
        usage = resp.usage
        # usage 理论上非空；防御性兜底为 0，避免记账拿到 None 报错（真实缺失会在契约测试暴露）。
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0
        return ChatResult(
            content=(msg.content or "").strip(),
            # reasoning_content 是 DeepSeek 思考档字段（类 o1），双档均可能返（spike P1），
            # 缺失取空串。
            reasoning=(getattr(msg, "reasoning_content", "") or "").strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=used_model,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话（AC2）：逐 chunk 产 StreamChunk（区分 content/reasoning），末尾产 StreamUsage。

        stream_options={"include_usage": True} 请求服务端在末 chunk 附总 usage（DeepSeek/OpenAI
        兼容）。若服务端未回 usage（末 chunk 无 usage），用 count_tokens 兜底估算并标
        estimated=True，记账口径差异见 Completion Notes。

        生命周期硬化（Story 2.3 Task 4，闭合 2.1 defer①）：用 `async with` 包裹 AsyncStream——
        消费方提前断开（SSE 客户端断连 → generator aclose → GeneratorExit）或中途异常时，
        `__aexit__` 保证底层 httpx 流响应被 close、连接归还池，不泄漏。与工厂层
        MeteredProvider.stream 的 try/finally 兜底记账配套：底层释放连接 + 上层兜底记账，
        早断路径既不漏连接也不漏账。
        """
        used_model = model or self._default_model
        api_usage = None
        # 兜底估算用：累计已产出的正文/思考文本，末尾无 API usage 时据此本地粗估。
        content_acc: list[str] = []
        prompt_text = "".join(m.get("content", "") for m in messages)
        async with await self._client.chat.completions.create(
            model=used_model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        ) as stream:
            async for chunk in stream:
                # include_usage 的末 chunk 通常 choices 为空、仅带 usage。
                if chunk.usage is not None:
                    api_usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                reasoning_delta = getattr(delta, "reasoning_content", None)
                if reasoning_delta:
                    yield StreamChunk(delta=reasoning_delta, kind="reasoning")
                if delta.content:
                    content_acc.append(delta.content)
                    yield StreamChunk(delta=delta.content, kind="content")
        # 流末回传总 usage（AC5 流式记账用）：优先 API 回报，缺失则本地兜底估算并标记。
        if api_usage is not None:
            yield StreamUsage(
                prompt_tokens=api_usage.prompt_tokens,
                completion_tokens=api_usage.completion_tokens,
                total_tokens=api_usage.total_tokens,
                model=used_model,
            )
        else:
            prompt_est = self.count_tokens(prompt_text)
            completion_est = self.count_tokens("".join(content_acc))
            yield StreamUsage(
                prompt_tokens=prompt_est,
                completion_tokens=completion_est,
                total_tokens=prompt_est + completion_est,
                model=used_model,
                estimated=True,
            )

    def count_tokens(self, text: str) -> int:
        """本地粗估 token 数（AC1，spike P1 系数）。**粗估、偏差约 +23.5%、不作扣费准据**——

        无官方离线 tokenizer 的 V1 近似：CJK×0.6 + 其余×0.3。扣费/触顶一律用 API 回报 usage。
        """
        cjk = sum(1 for ch in text if _CJK_START <= ch <= _CJK_END)
        other = len(text) - cjk
        return round(cjk * _CJK_TOKEN_RATIO + other * _OTHER_TOKEN_RATIO)
