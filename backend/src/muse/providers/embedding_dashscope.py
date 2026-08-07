"""DashScopeEmbeddingProvider：EmbeddingProvider 的阿里百炼实现（Story 5.5，AR18）。

**本模块允许 import openai**（同 deepseek.py 是全项目唯二允许直调 openai 的地方）：
阿里 DashScope 提供 OpenAI 兼容 endpoint，走 base_url 切换即可复用 AsyncOpenAI
（同 DeepSeek 走 base_url 切换先例）。

数据不出境（NFR8，AC5）：base_url 指向阿里国内 endpoint
（https://dashscope.aliyuncs.com/compatible-mode/v1），embedding（阿里）与 LLM
（DeepSeek）同区、部署国内云，满足数据合规。

维度锁死 1024（陷阱⑦）：text-embedding-v3 支持 dimensions 参数，显式传 1024 与建表
Vector(1024) 一致；若返回维度 ≠1024，pgvector 写入会报错。换维度须同步改建表迁移。
"""

from openai import AsyncOpenAI

from muse.models.embedding import EMBEDDING_DIM
from muse.providers.embedding_base import EmbeddingProvider


class DashScopeEmbeddingProvider(EmbeddingProvider):
    """阿里百炼 text-embedding-v3 实现（OpenAI 兼容接口，全栈 async）。

    构造注入 api_key/base_url（托管传 settings.embedding_*，V1 不开放 BYOK，见受控决策 1）。
    model 缺省用 settings.embedding_model；dimensions 固定 1024（与建表列对齐）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        model: str | None = None,
        dimensions: int = EMBEDDING_DIM,
    ) -> None:
        from muse.core.settings import get_settings

        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model or settings.embedding_model
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化：空输入直接返 []（不打 API）；否则调 API 并按 .index 排序回原顺序。

        陷阱⑤：OpenAI 兼容 embeddings.create 返回的 resp.data 理论按输入顺序，但契约带
        .index 字段——保险起见按 index 排序再取 embedding，防乱序导致 chunk 文本与向量
        错配（错配 = RAG 召回张冠李戴，隐蔽且致命）。
        """
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [item.embedding for item in ordered]

    @property
    def dimensions(self) -> int:
        return self._dimensions
