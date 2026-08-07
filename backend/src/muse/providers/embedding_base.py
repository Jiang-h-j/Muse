"""EmbeddingProvider 抽象接口（Story 5.5，AR18，类比 providers/base.py 的 LLMProvider）。

业务层**只依赖本抽象**——「换 embedding 供应商 = 换实现、不改业务层」，与 LLMProvider
立身之本同构。本文件**禁止 import openai**（同 base.py 约束）：阿里实现走 OpenAI 兼容
SDK，要 import openai，故隔离在独立文件 embedding_dashscope.py（同 base.py / deepseek.py
分离先例）。

V1 只有两个实现：DashScopeEmbeddingProvider（阿里 text-embedding-v3）+ NullEmbeddingProvider
（无配置降级）。工厂 get_embedding_provider 按托管配置构造。
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """可换供应商的文本向量化抽象：批量 embed + 维度声明。

    业务层（embedding_projection_service）依赖本抽象、由工厂
    （embedding_factory.get_embedding_provider）按托管配置注入具体实现。新增供应商
    （如智谱）只需新增子类实现，业务层零改动。
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量列表（顺序与输入对齐，一一对应）。

        空 `texts` 应直接返 `[]`（不打外部 API）。返回列表长度须等于输入长度、顺序对齐
        （实现层负责按 API 回报的 index 排序回原顺序，防乱序错配，见陷阱⑤）。
        NullEmbeddingProvider 恒返 `[]`——投影侧据 `[]` skip 写入（AC4 降级）。
        """
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """产出向量的维度（供建表维度校验/文档）。V1 阿里 text-embedding-v3 = 1024。"""
        ...
