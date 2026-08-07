"""Story 5.5 Task 4.2 验证：EmbeddingProvider 抽象 + 阿里实现 + Null + 工厂（离线，mock API）。

覆盖：
- NullEmbeddingProvider.embed 恒返 []；dimensions=1024。
- DashScopeEmbeddingProvider：mock AsyncOpenAI.embeddings.create 返乱序 data（.index 打乱）
  → 断言按 index 排序回原顺序（陷阱⑤）；空 texts 不打 API 直接返 []。
- get_embedding_provider 在 embedding_api_key 空/非空两态返正确类型（AC4）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

from muse.providers import embedding_factory
from muse.providers.embedding_dashscope import DashScopeEmbeddingProvider
from muse.providers.embedding_null import NullEmbeddingProvider

_DUMMY_KEY = "sk-embed-dummy"
_DUMMY_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# ---------- NullEmbeddingProvider ----------


async def test_null_provider_embed_returns_empty() -> None:
    provider = NullEmbeddingProvider()
    assert await provider.embed(["任意文本", "另一段"]) == []
    assert await provider.embed([]) == []
    assert provider.dimensions == 1024


# ---------- DashScopeEmbeddingProvider ----------


def _fake_embeddings_response(vectors_by_index: dict[int, list[float]]) -> MagicMock:
    """构造 mock 的 openai embeddings 响应：resp.data 每项带 .index + .embedding。"""
    data = []
    for idx, vec in vectors_by_index.items():
        item = MagicMock()
        item.index = idx
        item.embedding = vec
        data.append(item)
    resp = MagicMock()
    resp.data = data
    return resp


async def test_dashscope_sorts_by_index() -> None:
    # 陷阱⑤：API 返回 data 乱序（index 1 在前、0 在后）→ 结果须按 index 排序回原顺序。
    resp = _fake_embeddings_response({1: [0.2] * 1024, 0: [0.1] * 1024})
    with patch("muse.providers.embedding_dashscope.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.embeddings.create = AsyncMock(return_value=resp)
        provider = DashScopeEmbeddingProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        result = await provider.embed(["chunk0", "chunk1"])

    assert len(result) == 2
    assert result[0] == [0.1] * 1024  # index 0 排在前
    assert result[1] == [0.2] * 1024  # index 1 排在后
    assert provider.dimensions == 1024


async def test_dashscope_empty_texts_no_api_call() -> None:
    # 空 texts 直接返 []，不打 API（不构造无谓请求）。
    with patch("muse.providers.embedding_dashscope.AsyncOpenAI") as mock_cls:
        create_mock = AsyncMock()
        mock_cls.return_value.embeddings.create = create_mock
        provider = DashScopeEmbeddingProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        result = await provider.embed([])

    assert result == []
    create_mock.assert_not_called()


async def test_dashscope_passes_dimensions_and_model() -> None:
    # 显式传 dimensions=1024（陷阱⑦）+ 缺省 model 取 settings.embedding_model。
    resp = _fake_embeddings_response({0: [0.5] * 1024})
    with patch("muse.providers.embedding_dashscope.AsyncOpenAI") as mock_cls:
        create_mock = AsyncMock(return_value=resp)
        mock_cls.return_value.embeddings.create = create_mock
        provider = DashScopeEmbeddingProvider(api_key=_DUMMY_KEY, base_url=_DUMMY_BASE)
        await provider.embed(["chunk0"])

    kwargs = create_mock.call_args.kwargs
    assert kwargs["dimensions"] == 1024
    assert kwargs["model"] == "text-embedding-v3"
    assert kwargs["input"] == ["chunk0"]


# ---------- get_embedding_provider 工厂（AC4） ----------


def test_factory_returns_null_when_key_empty() -> None:
    # embedding_api_key 为空 → NullEmbeddingProvider（AC4 降级）。
    settings = MagicMock()
    settings.embedding_api_key = ""
    with patch(
        "muse.providers.embedding_factory.get_settings", return_value=settings
    ):
        provider = embedding_factory.get_embedding_provider()
    assert isinstance(provider, NullEmbeddingProvider)


def test_factory_returns_dashscope_when_key_present() -> None:
    # embedding_api_key 非空 → DashScopeEmbeddingProvider（阿里托管路径）。
    settings = MagicMock()
    settings.embedding_api_key = _DUMMY_KEY
    settings.embedding_base_url = _DUMMY_BASE
    settings.embedding_model = "text-embedding-v3"
    with patch(
        "muse.providers.embedding_factory.get_settings", return_value=settings
    ), patch("muse.providers.embedding_dashscope.AsyncOpenAI"):
        provider = embedding_factory.get_embedding_provider()
    assert isinstance(provider, DashScopeEmbeddingProvider)
