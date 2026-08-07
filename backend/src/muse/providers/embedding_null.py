"""NullEmbeddingProvider：无 embedding 配置时的降级实现（Story 5.5，AC4，AR18）。

当未配置托管 embedding（settings.embedding_api_key 为空）时，工厂返回本实现——
`embed` 恒返 `[]`，让投影侧据 `[]` 统一 skip 写入，业务层无需到处判
`if provider is None`。投影/定稿**不阻断**：embedding 段跳过、只记 warning，
RAG（5.6）退回纯 tsvector 关键词召回（召回质量下降但可用）。
"""

from muse.models.embedding import EMBEDDING_DIM
from muse.providers.embedding_base import EmbeddingProvider


class NullEmbeddingProvider(EmbeddingProvider):
    """空实现：embed 恒返 []（投影侧据此 skip），dimensions 返 1024（与建表列一致）。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 恒返空——投影侧 `if not vectors: return` 统一 skip 写入（AC4 降级）。
        return []

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIM
