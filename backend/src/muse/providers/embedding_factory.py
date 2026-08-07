"""EmbeddingProvider 工厂（Story 5.5，AR18，类比 providers/factory.py）。

**与 LLM 工厂 get_provider_for_user 的关键差异**：
- **无 session/user_id 入参**（受控决策 1）：V1 embedding 只走托管单路径，不按用户 BYOK
  分叉、不查 byok_key 表、只读 settings.embedding_*。若未来开放 BYOK embedding，再扩展
  工厂签名（同 LLM 工厂演进路径）。
- **V1 不做用量记账**（受控决策 2）：无 MeteredProvider 包裹——embedding 走托管归 Muse 账、
  成本远低于正文生成、额度护栏（1.8）计量单位是 LLM tokens。后续若要计量，在此包裹
  MeteredEmbeddingProvider（见下方注释）。

无 key 降级（AC4）：settings.embedding_api_key 为空 → 返 NullEmbeddingProvider，投影侧
据 embed() 返 [] 统一 skip；非空 → 返 DashScopeEmbeddingProvider（阿里）。
"""

from muse.core.settings import get_settings
from muse.providers.embedding_base import EmbeddingProvider
from muse.providers.embedding_null import NullEmbeddingProvider


def get_embedding_provider() -> EmbeddingProvider:
    """按托管配置返回 EmbeddingProvider（AC2/AC4/AC5）。

    - embedding_api_key 为空 → NullEmbeddingProvider（AC4 降级，投影 skip）。
    - embedding_api_key 非空 → DashScopeEmbeddingProvider（阿里国内 endpoint，NFR8）。

    V1 不包裹记账（受控决策 2）：后续若要计量 embedding 用量，在此处用
    MeteredEmbeddingProvider 包裹返回值（同 LLM 工厂 MeteredProvider 埋点位置）。
    """
    settings = get_settings()
    if not settings.embedding_api_key:
        return NullEmbeddingProvider()
    # 延迟 import：DashScope 实现 import openai，只在真要构造托管实现时才加载
    # （与 base 文件禁 import openai 的隔离一致）。
    from muse.providers.embedding_dashscope import DashScopeEmbeddingProvider

    return DashScopeEmbeddingProvider(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
    )
