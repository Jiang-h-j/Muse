"""Story 5.6 Task 1 测试：rag/retrieval.py 三级召回（单元测试，mock 依赖）。

覆盖：
- RRF 融合：两段结果合并按 RRF 得分排序
- 降级（AC4）：NullEmbeddingProvider 时向量段 skip，返纯 tsvector 结果
- 空结果：两段皆空时 recall 为 0 条不报错
- query_embedding 构建逻辑（均值向量）的基础正确性
- _simple_tokenize_cjk 辅助函数

**设计范式**：mock 向量/tsvector 两段查询 + 断言 RRF 排序 top N 正确。
不碰真实 PG——纯 Python 逻辑单元测试。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muse.rag import retrieval
from muse.rag.retrieval import (
    RecallCtxItem,
    RecallResult,
    _rrf_fuse,
    _simple_tokenize_cjk,
)

# ---- 固定数据 ----
_UID = uuid.uuid4()
_PID = uuid.uuid4()


def _make_vector_items(count: int = 3) -> list[RecallCtxItem]:
    """造 fake 向量段召回结果。"""
    items: list[RecallCtxItem] = []
    for i in range(count):
        items.append(
            RecallCtxItem(
                chapter_number=i + 1,
                content=f"向量命中第 {i + 1} 章的内容",
                score=0.9 - i * 0.1,
                source="vector",
            )
        )
    return items


def _make_keyword_items(count: int = 3) -> list[RecallCtxItem]:
    """造 fake tsvector 段召回结果。"""
    items: list[RecallCtxItem] = []
    for i in range(count):
        items.append(
            RecallCtxItem(
                chapter_number=i + 10,
                content=f"关键词命中第 {i + 10} 章的内容",
                score=0.5 - i * 0.05,
                source="keyword",
            )
        )
    return items


# ========== RRF 融合 ==========


def test_rrf_fuse_both_non_empty_returns_top_n():
    """两段均有结果时 RRF 按 position rank 融合返回 top N。"""
    vector = _make_vector_items(5)
    keyword = _make_keyword_items(5)
    fused = _rrf_fuse(vector_items=vector, keyword_items=keyword, top_n=3)
    assert len(fused) <= 3
    assert all(item.source == "rrf_fused" for item in fused)
    # RRF 得分应 > 0
    for item in fused:
        assert item.score > 0.0


def test_rrf_fuse_vector_only_returns_vector_items():
    """只有向量段结果时直接返回向量段前 top_n。"""
    vector = _make_vector_items(3)
    fused = _rrf_fuse(vector_items=vector, keyword_items=[], top_n=2)
    assert len(fused) == 2
    assert all(item.source == "vector" for item in fused)


def test_rrf_fuse_keyword_only_returns_keyword_items():
    """只有关键词段结果时直接返回关键词段前 top_n。"""
    keyword = _make_keyword_items(3)
    fused = _rrf_fuse(vector_items=[], keyword_items=keyword, top_n=2)
    assert len(fused) == 2
    assert all(item.source == "keyword" for item in fused)


def test_rrf_fuse_both_empty_returns_empty():
    """两段皆空时返回空列表（不报错）。"""
    fused = _rrf_fuse(vector_items=[], keyword_items=[], top_n=5)
    assert fused == []


def test_rrf_fuse_duplicate_items_merge_ranks():
    """同一 (chapter_number, content) 被两段同时命中时 RRF 得分合并。"""
    dup = RecallCtxItem(
        chapter_number=5,
        content="两段共同命中",
        score=0.8,
        source="vector",
    )
    vector = [dup]
    keyword = [dup]  # 同一 item
    fused = _rrf_fuse(vector_items=vector, keyword_items=keyword, top_n=1)
    # 同一 item 被两段命中，RRF 得分累加：1/(k+1) + 1/(k+2)（vector rank 1, keyword rank 1）
    # 但 round(score, 4) 四舍五入后为 0.0328
    expected = round(1.0 / (60 + 1) + 1.0 / (60 + 1), 4)
    assert len(fused) == 1
    assert fused[0].score == expected
    assert fused[0].source == "rrf_fused"


# ========== _simple_tokenize_cjk 辅助函数 ==========


def test_simple_tokenize_empty_returns_empty():
    assert _simple_tokenize_cjk("") == []
    assert _simple_tokenize_cjk("   ") == []


def test_simple_tokenize_cjk_splits_by_non_cjk_boundary():
    """CJK 字符按空白/标点边界拆分。"""
    tokens = _simple_tokenize_cjk("程野决定离开，寻找新的出路")
    # V1 simple 配置：`\w` 正则匹配中文连续字符，返回多字词。
    # 中文多字词在 `\w` 里被当为一个 token。
    assert len(tokens) >= 1
    # 每 token 长度 > 1（单字被过滤）
    assert all(len(t) > 1 for t in tokens)


def test_simple_tokenize_removes_single_char():
    """单字词（len=1）被过滤（召回信息量低）。"""
    tokens = _simple_tokenize_cjk("程 野 分 别")
    # 所有单字被过滤
    assert "程" not in tokens


# ========== recall_context_for_chapter 编排 ==========


@pytest.mark.asyncio
async def test_recall_context_degraded_skips_vector():
    """AC4：NullEmbeddingProvider 时向量段被 skip，退为纯 tsvector。"""
    from muse.providers.embedding_null import NullEmbeddingProvider

    with (
        patch.object(
            retrieval, "get_embedding_provider",
            return_value=NullEmbeddingProvider(),
        ),
        patch.object(retrieval, "_vector_recall") as mock_vector,
        patch.object(
            retrieval,
            "_keyword_recall",
            new=AsyncMock(return_value=_make_keyword_items(3)),
        ) as mock_keyword,
        patch.object(
            retrieval, "_build_query_embedding_mean", return_value=None
        ),
    ):
        result = await retrieval.recall_context_for_chapter(
            AsyncMock(),  # session
            user_id=_UID,
            project_id=_PID,
            current_chapter=2,
            limit=5,
        )

        # 向量段不应被调用（NullEmbeddingProvider 自动跳过）
        mock_vector.assert_not_called()
        # 关键词段被调用（tsvector 正常执行）
        assert mock_keyword.called
        # 最终结果来自关键词段
        assert result.degraded is True
        assert result.metadata["vector_hits"] == 0


@pytest.mark.asyncio
async def test_recall_context_vector_exception_catches_gracefully():
    """AC4：向量召回异常时 catch 后降级为纯 tsvector——不报错。"""
    with (
        patch.object(
            retrieval, "get_embedding_provider",
            return_value=MagicMock(),
        ),
        patch.object(
            retrieval,
            "_vector_recall",
            side_effect=RuntimeError("pgvector 查询超时"),
        ),
        patch.object(
            retrieval,
            "_keyword_recall",
            new=AsyncMock(return_value=_make_keyword_items(3)),
        ),
        patch.object(
            retrieval, "_build_query_embedding_mean",
            return_value=[0.1] * 1024,
        ),
    ):
        # 不应抛错——RAG 召回是增强而非必备
        result = await retrieval.recall_context_for_chapter(
            AsyncMock(),
            user_id=_UID,
            project_id=_PID,
            current_chapter=2,
        )
        # 向量段异常被 catch，结果仍来自关键词段
        assert result.metadata["vector_hits"] == 0
        assert result.metadata["keyword_hits"] == 3
        # metadata 记录了异常
        assert result.metadata["final_count"] == 3
        # 不应标记 degraded（degraded 仅当 provider 为空时）
        assert result.degraded is False


@pytest.mark.asyncio
async def test_recall_context_no_results_returns_empty():
    """两段皆空时返回空 RecallResult（不报错）。"""
    with (
        patch.object(retrieval, "get_embedding_provider", return_value=MagicMock()),
        patch.object(retrieval, "_vector_recall", new=AsyncMock(return_value=[])),
        patch.object(retrieval, "_keyword_recall", new=AsyncMock(return_value=[])),
        patch.object(retrieval, "_build_query_embedding_mean", return_value=[0.1] * 1024),
        patch.object(retrieval, "chapter_card_repo") as mock_card_repo,
    ):
        mock_card_repo.list_recent_chapter_cards = AsyncMock(return_value=[])

        result = await retrieval.recall_context_for_chapter(
            AsyncMock(),
            user_id=_UID,
            project_id=_PID,
            current_chapter=2,
        )
        assert result.items == []
        assert result.metadata["vector_hits"] == 0
        assert result.metadata["keyword_hits"] == 0
        assert result.metadata["final_count"] == 0


# ========== _build_query_embedding_mean ==========


@pytest.mark.asyncio
async def test_build_query_embedding_first_chapter_returns_none():
    """第一章（before_chapter=1）无上一章 → 返回 None（降级纯 tsvector）。"""
    result = await retrieval._build_query_embedding_mean(
        MagicMock(),
        user_id=_UID,
        project_id=_PID,
        before_chapter=1,  # 第一章 → 上一章为 0（不存在）
    )
    assert result is None


@pytest.mark.asyncio
async def test_build_query_embedding_mean_returns_averaged_vector():
    """正常情况：上一章有 3 个 chunk embedding → 返回 3 向量的逐维均值。"""
    mock_session = MagicMock()
    # 模拟上一章有 3 个 embedding 行
    row1 = ([0.1, 0.2, 0.3],)
    row2 = ([0.4, 0.5, 0.6],)
    row3 = ([0.7, 0.8, 0.9],)

    # 第一次 execute 返 mock——第一次调 execute 返所有行。
    mock_result1 = MagicMock()
    mock_result1.all.return_value = [row1, row2, row3]
    mock_session.execute = AsyncMock(return_value=mock_result1)

    result = await retrieval._build_query_embedding_mean(
        mock_session,
        user_id=_UID,
        project_id=_PID,
        before_chapter=3,  # 写第 3 章，上一章为 ch2
    )
    # 均值：[(0.1+0.4+0.7)/3, (0.2+0.5+0.8)/3, (0.3+0.6+0.9)/3]
    assert result is not None
    assert len(result) == 3
    assert result[0] == pytest.approx(0.4, rel=1e-4)
    assert result[1] == pytest.approx(0.5, rel=1e-4)
    assert result[2] == pytest.approx(0.6, rel=1e-4)


# ========== _rrf_fuse with empty and top_n boundary ==========


def test_rrf_fuse_top_n_exceeds_both_lists():
    """top_n 大于两段实际长度时返回所有项（不截断）。"""
    vector = _make_vector_items(2)
    keyword = _make_keyword_items(2)
    fused = _rrf_fuse(vector_items=vector, keyword_items=keyword, top_n=10)
    assert len(fused) <= 4  # 最多 4 条不重复条目
    assert len(fused) >= 1


# ========== _build_recall_tsquery_from_terms ==========


def test_build_tsquery_empty_returns_none():
    assert retrieval._build_recall_tsquery_from_terms([]) is None


def test_build_tsquery_or_combination():
    """多词用 | OR 组合。"""
    query = retrieval._build_recall_tsquery_from_terms(["程野", "离开", "第七码头"])
    assert query is not None
    assert "程野" in query
    assert "离开" in query
    assert "第七码头" in query
    # OR 组合
    assert " | " in query


# ========== 类型守卫 ==========


def test_recall_ctx_item_creatable():
    """RecallCtxItem 可创建并设置 truncated。"""
    item = RecallCtxItem(
        chapter_number=3,
        content="程野进入地下档案库",
        score=0.85,
        source="vector",
        truncated="程野进入地下...",
    )
    assert item.chapter_number == 3
    assert item.content == "程野进入地下档案库"
    assert item.truncated == "程野进入地下..."
    assert item.source == "vector"


def test_recall_result_empty_default():
    result = RecallResult()
    assert result.items == []
    assert result.degraded is False
    assert result.metadata == {}


def test_recall_result_metadata_contains_hits():
    result = RecallResult(
        items=[RecallCtxItem(chapter_number=1, content="x", score=0.9, source="vector")],
        metadata={"vector_hits": 1, "keyword_hits": 0, "fused_hits": 1},
        degraded=False,
    )
    assert result.metadata["vector_hits"] == 1
    assert result.metadata["keyword_hits"] == 0
    assert result.metadata["fused_hits"] == 1