"""Provider 工厂 + 用量记账包裹（Story 2.1，AC5/AC6/AC7）。

**本模块是兑现 Story 1.8 跨 epic 依赖的闭合点**：1.8 交付了空转的 record_usage/check_quota
（无调用方），本 story 让它们首次接进真实 LLM 调用链路。

两职责：
1. get_provider_for_user：按账户 BYOK 绑定态决定走 BYOK 还是托管，构造对应 Provider（AC6），
   未实现的 provider（claude/custom）抛 provider_not_supported（AC7，不静默失败）。
2. MeteredProvider：**provider-agnostic 记账包裹**——任意 LLMProvider 调用完拿到 usage 后统一
   调 record_usage（AR14/Enforcement architecture.md:356 记账埋点在 Provider 层）。记账逻辑与
   具体模型解耦：换模型（新增 Provider 子类）无需重写记账，只要子类如实返回 usage（AC5）。

护栏（check_quota，AC6）不在工厂内做——由生成入口在「构造 provider 前」显式调用（触顶抛 429
不进生成）。本 story 无真实生成入口，由示范任务/集成测试演示「check_quota → provider →
record_usage」完整串联（见 tasks/worker.py demo_generate）。
"""

import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from muse.core.errors import ErrorEnvelope
from muse.core.settings import get_settings
from muse.providers.base import (
    ChatResult,
    LLMProvider,
    Message,
    StreamEvent,
    StreamUsage,
)
from muse.providers.deepseek import DeepSeekProvider, compute_cost
from muse.services import byok_service, usage_service

# 成本函数签名：(model, prompt_tokens, completion_tokens) -> Decimal（陷阱② 全程 Decimal）。
CostFn = Callable[[str, int, int], Decimal]


class MeteredProvider(LLMProvider):
    """包裹任意 LLMProvider：chat/stream 完成拿到 usage 后统一 record_usage（AC5）。

    provider-agnostic——记账逻辑不依赖具体模型，换模型不用重写（工厂为不同 Provider 传对应
    cost_fn 即可）。billing_path 由工厂按 BYOK 绑定态决定（hosted/byok）传入。cost 用 cost_fn
    算得 Decimal（陷阱②），total_tokens 用 provider 返回的 **API usage**（非本地估算，spike P1）。

    session 归属（陷阱⑦）：本包裹持有的 session 由调用方（如 ARQ worker）提供并管理生命周期；
    record_usage 内部 commit（1.8 已实现）。worker 内用 worker 自己的 async session，勿跨用 web
    请求 session。
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        session: AsyncSession,
        user_id: uuid.UUID,
        billing_path: str,
        cost_fn: CostFn,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self._inner = inner
        self._session = session
        self._user_id = user_id
        self._billing_path = billing_path
        self._cost_fn = cost_fn
        self._project_id = project_id

    async def _record(
        self, *, prompt_tokens: int, completion_tokens: int, total_tokens: int, model: str
    ) -> None:
        """统一记账：cost 用 cost_fn 算 Decimal，total_tokens 用 API usage（AC5）。"""
        cost = self._cost_fn(model, prompt_tokens, completion_tokens)
        await usage_service.record_usage(
            self._session,
            user_id=self._user_id,
            billing_path=self._billing_path,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            project_id=self._project_id,
            model_name=model,
        )

    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        result = await self._inner.chat(messages, model=model, max_tokens=max_tokens)
        await self._record(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            model=result.model,
        )
        return result

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        # 透传所有事件；正常路径末尾 StreamUsage 到达即精确记账（流式 usage 在流末，AC5）。
        # 但消费方提前断开（generator aclose → GeneratorExit）或内层流在产出 StreamUsage 前抛异常
        # （如 OpenAI 中途 5xx）时，若只在 StreamUsage 分支记账则已消耗 token 永不落库——托管收入
        # 漏计、用户可早断白嫖。故用 try/finally：拿到 StreamUsage 即精确记账并置 recorded；未拿到
        # （早断/异常）则在 finally 用已累计输出本地估算兜底记一次，两条路径互斥不双记。
        recorded = False
        output_acc: list[str] = []
        prompt_text = "".join(m.get("content", "") for m in messages)
        try:
            async for event in self._inner.stream(
                messages, model=model, max_tokens=max_tokens
            ):
                if isinstance(event, StreamUsage):
                    await self._record(
                        prompt_tokens=event.prompt_tokens,
                        completion_tokens=event.completion_tokens,
                        total_tokens=event.total_tokens,
                        model=event.model,
                    )
                    recorded = True
                else:
                    # StreamChunk（content/reasoning 均计入产出）：累计供兜底估算。
                    output_acc.append(event.delta)
                yield event
        finally:
            if not recorded:
                # 兜底：流未正常产出 StreamUsage（早断/中途异常）。本地估算偏差已知
                # （spike P1 约 +23.5%），仅作「不丢账」安全网、非精确扣费；model 未知时
                # cost 归 0（compute_cost 兜底），但 token 必落库避免漏计。
                prompt_est = self._inner.count_tokens(prompt_text)
                completion_est = self._inner.count_tokens("".join(output_acc))
                await self._record(
                    prompt_tokens=prompt_est,
                    completion_tokens=completion_est,
                    total_tokens=prompt_est + completion_est,
                    model=model or "",
                )

    def count_tokens(self, text: str) -> int:
        # 本地粗估直接透传（不涉及记账，扣费一律用 API usage）。
        return self._inner.count_tokens(text)


async def get_provider_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
) -> LLMProvider:
    """按账户 BYOK 绑定态返回带记账的 Provider（AC5/AC6/AC7）。

    - 未绑定 BYOK → 托管 DeepSeekProvider(settings.deepseek_api_key)，billing_path="hosted"。
    - 已绑定 deepseek → 用 get_decrypted_key_for_user 取明文构造 DeepSeekProvider，
      billing_path="byok"。
    - 已绑定 claude/custom → 抛 provider_not_supported（AC7，ClaudeProvider 留盲测 4.1）。

    判「走 BYOK 还是托管」用 get_binding_status（存在性、不解密，陷阱③）；只有确定走 BYOK
    deepseek、真要构造客户端时才 get_decrypted_key_for_user 取明文（明文只在内存、绝不 log/
    落库/出边界，1.7 红线）。
    """
    settings = get_settings()
    status = await byok_service.get_binding_status(session, user_id)

    if not status["bound"]:
        # 未绑定：托管路径，用 Muse 自有 Key。
        inner: LLMProvider = DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        billing_path = "hosted"
    else:
        provider_name = status["provider"]
        if provider_name != "deepseek":
            # claude/custom 已能绑定（1.7 枚举含三值）但本 story 只实现 DeepSeek——诚实占位、不静默
            # 失败、不误当 DeepSeek 调用（AC7/定档②）。ClaudeProvider 归盲测 Story 4.1。
            raise ErrorEnvelope(
                code="provider_not_supported",
                message="该模型提供方尚未支持，敬请期待。",
                detail={"provider": provider_name},
                http_status=400,
            )
        # 已绑定 deepseek：此刻才解密取明文（陷阱③：确定要构造客户端才解密）。
        plaintext_key = await byok_service.get_decrypted_key_for_user(session, user_id)
        inner = DeepSeekProvider(
            api_key=plaintext_key or "",
            base_url=settings.deepseek_base_url,
        )
        billing_path = "byok"

    return MeteredProvider(
        inner,
        session=session,
        user_id=user_id,
        billing_path=billing_path,
        cost_fn=compute_cost,
        project_id=project_id,
    )
