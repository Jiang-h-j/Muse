"""LLMProvider 抽象接口（Story 2.1，AR12/焦点一）。

业务层**只依赖本抽象**，绝不直接 import/调用 openai SDK——「换模型 = 换实现、不改业务层」
是整个焦点一的立身之本（Enforcement architecture.md:341/356，code review 卡 Provider 直调）。
openai 只允许出现在 providers/deepseek.py，本文件**禁止 import openai**（陷阱①）。

返回类型用 @dataclass 而非 Pydantic：Provider 内部结构无需 camelCase 边界（那是 schema 层的事），
dataclass 更轻。tokens/成本记账在 Provider 层统一做（见 factory），故 ChatResult 携带 usage 三分量
供记账用；SSE 边界的 camelCase 由 core/sse.py 负责。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

# LLM 对话消息：OpenAI 兼容格式 {"role": "user"/"system"/"assistant", "content": "..."}。
# Provider 抽象层只约定这一最小形状，具体 SDK 映射在实现层（deepseek.py）完成。
Message = dict[str, str]


@dataclass
class ChatResult:
    """一次非流式 chat 的完整结果（AC1）。

    reasoning：思考过程（DeepSeek 双档 pro/flash 均可能返 reasoning_content，spike P1 实测），
    默认空串——不假设只有 pro 档有（陷阱见 AC2）。usage 三分量用于 Provider 层记账（AC5），
    **记账一律用 API 回报的 total_tokens**，不用本地 count_tokens 预估（spike P1 偏差 +23.5%）。
    """

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    reasoning: str = ""


@dataclass
class StreamChunk:
    """流式增量的单个片段（AC2）。

    kind 区分正文（content）与思考（reasoning）——供前端「思考中」展示或丢弃（spike P1 设计输入）。
    双档均可能产 reasoning 片段，消费方据 kind 分流，不假设只有 pro 有。
    """

    delta: str
    kind: Literal["content", "reasoning"]


@dataclass
class StreamUsage:
    """流结束时回传的总 usage（AC5 流式记账用）。

    流式 usage 通常在末 chunk（DeepSeek/OpenAI 兼容需 stream_options={"include_usage": True}）；
    若服务端不回则由实现层用 count_tokens 兜底估算并在 Completion Notes 记明口径。作为 stream()
    产出序列的**最后一个元素**（与 StreamChunk 区分类型），供工厂层收尾记账。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    # 兜底估算标记：True 表示 usage 非 API 回报而是本地 count_tokens 估算（记账需知悉口径）。
    estimated: bool = False


# stream() 的产出既有增量片段、也有末尾一个总 usage——用联合类型区分，消费方 isinstance 分流。
StreamEvent = StreamChunk | StreamUsage


@dataclass
class LLMError:
    """Provider 调用失败的结构化载荷（供工厂/worker 转 error 事件或 ErrorEnvelope）。

    与 core/errors.ErrorEnvelope 的 code/message 对齐，便于长时任务 error 事件复用同一契约。
    本 story 未强制所有 Provider 抛此类型，保留作扩展点。
    """

    code: str
    message: str
    detail: dict[str, object] = field(default_factory=dict)


class LLMProvider(ABC):
    """可换模型的 LLM 接入抽象：chat（非流式）/ stream（流式）/ count_tokens（本地粗估）。

    业务层依赖本抽象、由工厂（providers/factory.py）按 BYOK/托管注入具体实现。新增模型
    （如盲测 Story 4.1 的 Claude）只需新增子类实现，业务层零改动。
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """一次非流式对话，返回完整结果含 usage（AC1）。model=None 时用实现层默认档。"""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话，异步产出 StreamChunk×N + 末尾一个 StreamUsage（AC2）。

        实现为 async generator（`async def ... yield`）；调用方
        `async for ev in provider.stream(...)`，据 isinstance 区分增量片段与末尾 usage。
        可被 SSE 端点逐块推送。
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """本地粗估 token 数（AC1）。**仅供调用前粗略提示，不作扣费/触顶准数**——

        无官方离线 tokenizer，估算有偏差（spike P1 实测 +23.5%）。扣费一律用 API 回报的
        usage.total_tokens（见 ChatResult/StreamUsage），本方法只用于生成前的粗略体量提示。
        """
        ...
