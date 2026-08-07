"""RAG 三级召回编排（Story 5.6，AC1/AC4，AR18）——向量 + tsvector 关键词 + RRF 融合 +
rerank 占位。

把写前上下文从「全量设定 + 最近定稿章节」升级为「story_bible + 最近 chapter_cards
+ 未回收 story_threads + 世界规则 + 主角状态 + RAG 召回的相关历史」。本模块是
Epic 5 RAG 链的收官（5.5 embed 写入 + 5.6 召回接回），辉映架构焦点四「三段闭环：
①写前 context-agent → ②写后 data-agent → ③RAG 召回回头增强」
（architecture.md:239-253）。

**不新建任何表**：消费 5.1 chapter_card/story_thread/story_state + 5.5 embedding。
**只建设召回逻辑** + 回改 `orchestration/steps.py context_agent` 注入点。

三级召回（AC1）：
1. 向量召回（pgvector HNSW 余弦距离）——查「语义上与上一章相似的 chunk」
2. tsvector 关键词召回（PG 原生 full-text search + `ts_rank` 近似 BM25，V1 无
   pg_search）——查「与当前章附近几章的关键词匹配的 chunk/card/thread」
3. RRF 融合（k=60 典型值）——按排名位置融合两段结果取 top N
4. V1 以 RRF 排序代替独立 rerank step（受控决策 1）——留注释标记 V2 可加
   交叉编码器/LLM rerank

降级场景（AC4）：
- 无 embedding key（get_embedding_provider 返回 NullEmbeddingProvider）
  → 阶段 1 向量召回 skip → 纯 tsvector + 纯直接注入（story_bible
  + chapter_cards + story_threads + story_state 结合的基础上下文）。
- 上一章无 embedding（如 key 后补）→ 退为纯 tsvector。

**受控决策**：
1. V1 无独立 rerank step（以 RRF 排序代替），理由见 Dev Notes 受控决策 1
2. V1 tsvector 用 `simple` 配置做中文近似，理由见 Dev Notes 受控决策 2
3. query_embedding 用上一章均值向量，理由见 Dev Notes 受控决策 3
4. RAG 召回不阻断写前上下文组装，理由见 Dev Notes 受控决策 4
5. RAG 召回结果上限受控截断防上下文暴涨，理由见 Dev Notes 受控决策 5
"""

import dataclasses
import logging
import uuid
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from muse.models.embedding import Embedding
from muse.providers.embedding_base import EmbeddingProvider
from muse.providers.embedding_factory import get_embedding_provider
from muse.repositories import chapter_card_repo

logger = logging.getLogger("muse")

# ---------------------------------------------------------------------------
# 受控决策：V1 常量
# ---------------------------------------------------------------------------

# RRF k 参数（典型值 60——recall 质量 vs 简单性折衷，不调参）。
_RRF_K = 60
# 每段召回 top N（向量段取 50 条、tsvector 取 30 条——给 RRF 足够候选池）。
_VECTOR_TOP_N = 50
_TSVECTOR_TOP_M = 30
# 关键词来源——取当前章号附近 N 章的五要素文本去重分词作搜索 query。
_KEYWORD_SOURCE_WINDOW = 5


@dataclass
class RecallCtxItem:
    """单条召回项（AC1：供 RRF 融合与排序）。"""

    chapter_number: int
    content: str
    score: float
    source: str  # "vector" | "keyword" | "rrf_fused"
    # 截断 200 字供上下文注入（防单条过长挤爆写作任务书）。
    truncated: str | None = None


@dataclass
class RecallResult:
    """三级召回结果（AC1）。"""

    items: list[RecallCtxItem] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # 降级标志（AC4）：vector 段被 skip 时为 True。
    degraded: bool = False


# ---------------------------------------------------------------------------
# 召回编排入口
# ---------------------------------------------------------------------------


async def recall_context_for_chapter(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    current_chapter: int,
    limit: int = 20,
) -> RecallResult:
    """三级召回——向量 + tsvector + RRF 融合 + rerank 占位（AC1）。

    **阶段 1—向量召回**：取上一章（chapter_number=current_chapter-1）的全部 chunk
    embedding 均值向量作查询向量，对 embedding 表做余弦距离查询取 top N。

    **阶段 2—tsvector 关键词召回**：取当前章附近 N 章的 chapter_card 五要素文本
    去重分词作搜索 query tsquery，对 chapter_card 五要素列 + story_thread.content
    （仅 status='open'）+ embedding.content 做全文检索。

    **阶段 3—RRF 融合**：对阶段 1 结果（rank_vector）和阶段 2 结果（rank_keyword）
    做 Reciprocal Rank Fusion，k 取 60。

    **阶段 4—rerank**：V1 用 RRF 排序取 top limit 直接返回（不做独立 rerank step，
    受控决策 1）。留注释标记 V2 可加交叉编码器/LLM rerank。

    结果上限 limit 防写前上下文暴涨；metadata 含每段命中数、是否降级。
    """
    # ---------- 判断降级 ----------
    provider = get_embedding_provider()
    degraded = _is_null_provider(provider)

    # ---------- 阶段 1：向量召回 ----------
    vector_items: list[RecallCtxItem] = []
    if not degraded:
        try:
            query_vec = await _build_query_embedding_mean(
                session,
                user_id=user_id,
                project_id=project_id,
                before_chapter=current_chapter,
            )
            if query_vec is not None:
                vector_items = await _vector_recall(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    query_embedding=query_vec,
                    exclude_chapter=current_chapter,
                    limit=_VECTOR_TOP_N,
                )
        except Exception:
            logger.warning(
                "向量召回异常（降级为纯 tsvector）：user=%s project=%s chapter=%s",
                user_id,
                project_id,
                current_chapter,
                exc_info=True,
            )
    # 无 embedding 或异常 → vector_items 保持 []。

    # ---------- 阶段 2：tsvector 关键词召回 ----------
    keyword_items: list[RecallCtxItem] = []
    try:
        keyword_items = await _keyword_recall(
            session,
            user_id=user_id,
            project_id=project_id,
            current_chapter=current_chapter,
            limit=_TSVECTOR_TOP_M,
        )
    except Exception:
        logger.warning(
            "tsvector 关键词召回异常（跳过）：user=%s project=%s chapter=%s",
            user_id,
            project_id,
            current_chapter,
            exc_info=True,
        )
    # tsvector 召回异常 → keyword_items 保持 [].

    # ---------- 阶段 3：RRF 融合 ----------
    fused = _rrf_fuse(
        vector_items=vector_items,
        keyword_items=keyword_items,
        k=_RRF_K,
        top_n=limit,
    )

    # ---------- 阶段 4：rerank（V1 用 RRF 排序代替独立 rerank） ----------
    # 受控决策 1：V1 以 RRF 排序后的 top N 作为最终结果。如需增强排序质量，
    # V2 可引入交叉编码器（cross-encoder）或 LLM rerank 步骤重新排序 fused 列表。
    final_items = fused

    return RecallResult(
        items=final_items,
        metadata={
            "vector_hits": len(vector_items),
            "keyword_hits": len(keyword_items),
            "fused_hits": len(fused),
            "degraded": degraded,
            "final_count": len(final_items),
        },
        degraded=degraded,
    )


# ---------------------------------------------------------------------------
# 阶段 1：向量召回
# ---------------------------------------------------------------------------


async def _build_query_embedding_mean(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    before_chapter: int,
) -> list[float] | None:
    """上一章（chapter_number=before_chapter-1）的全部 chunk embedding 均值向量。

    受控决策 3：以当前要写章节的上一章正文 chunk embedding 均值作查询向量——
    召回「语义上与上一章相似的历史章节」。长篇里「场景/设定切换」通常跨章发生，
    上一章的最新事实最能召回同类话题的历史段落。

    **降级**（AC4）：上一章无 embedding 行（如该章未跑投影或 embedding 段被跳过）
    → 返回 None，调用方降级为纯 tsvector。

    **均值向量陷阱**：pgvector `<=>` 余弦距离对均值向量仍有效——
    `cosine_similarity(mean_vec, target_vec)` 等价于均值向量与目标向量的余弦相似度
    （与每块独立做 `<=>` 再取平均不等价但近似，均值向量一次查询高效）。
    """
    if before_chapter <= 1:  # 第一章无上一章
        return None
    query_chapter = before_chapter - 1

    stmt = (
        select(Embedding.embedding)
        .where(
            Embedding.user_id == user_id,
            Embedding.project_id == project_id,
            Embedding.chapter_number == query_chapter,
        )
    )
    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        # 上一章无 embedding：取当前作品中 chapter_number 最接近 before_chapter
        # 且有 embedding 的上一章作为 query（防外推：上一章无 embedding 时别退
        # 回 "最远的一章"——取最接近 current_chapter 的那章）。
        stmt2 = (
            select(Embedding.chapter_number, Embedding.embedding)
            .where(
                Embedding.user_id == user_id,
                Embedding.project_id == project_id,
                Embedding.chapter_number < before_chapter,
            )
            .order_by(Embedding.chapter_number.desc())
            .limit(1)
        )
        result2 = await session.execute(stmt2)
        nearest = result2.first()
        if nearest is None:
            return None  # 全作品无任何 embedding 行 → 纯 tsvector
        vecs = await session.execute(
            select(Embedding.embedding).where(
                Embedding.user_id == user_id,
                Embedding.project_id == project_id,
                Embedding.chapter_number == nearest.chapter_number,
            )
        )
        rows = vecs.all()
    # 因为上一章表已确认有 embedding 行，故 rows 非空（若非空则取 vecs 重查）。

    vectors: list[list[float]] = [cast(list[float], r[0]) for r in rows]
    if not vectors:
        logger.warning(
            "上一章无 embedding 行（降级为纯 tsvector）：user=%s project=%s before=%s",
            user_id,
            project_id,
            before_chapter,
        )
        return None

    # 均值向量：逐维加总 / 行数。
    dim = len(vectors[0])
    count = len(vectors)
    mean = [0.0] * dim
    for vec in vectors:
        for i in range(dim):
            mean[i] += vec[i]
    for i in range(dim):
        mean[i] /= count
    return mean


async def _vector_recall(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    query_embedding: list[float],
    exclude_chapter: int | None,
    limit: int,
) -> list[RecallCtxItem]:
    """pgvector 余弦距离向量召回（AC1：阶段 1）。

    查 `select embedding.chapter_number, embedding.content,
    1 - (embedding.embedding <=> query_embedding) AS cosine_sim`
    对每章最新的 embedding chunk 做余弦距离查询，取 top N。

    余弦距离（`<=>`）返 0~1（距离越小越相似），`1 - <=>` 就是余弦相似度
    （越大越相似）——排序用 `cosine_sim DESC`。

    HNSW 索引 `ix_embedding_vector_hnsw` 带 `vector_cosine_ops` 自动加速
    此查询（5.5 建 HNSW 余弦索引）。
    """
    # `<=>` 是 pgvector 自定义 operator，SQLAlchemy 不原生支持。
    # 用 text() 内联 SQL——参数化绑定防注入。
    # 注意：`<=>` operator 在 SQLAlchemy 里未被解析，需用 text() 直写 SQL。
    # `1 - (a <=> b)` 等价于 cosine_similarity(a, b)，HNSW 索引自动加速。
    stmt = text(
        """
        SELECT e.chapter_number, e.content,
               1 - (e.embedding <=> :query_vec) AS similarity
        FROM embedding e
        WHERE e.user_id = :uid
          AND e.project_id = :pid
          AND e.chapter_number != :excl_ch
        ORDER BY similarity DESC
        LIMIT :lim
        """
    ).bindparams(
        uid=user_id,
        pid=project_id,
        query_vec=query_embedding,
        excl_ch=exclude_chapter if exclude_chapter is not None else -1,
        lim=limit,
    )
    result = await session.execute(stmt)
    items: list[RecallCtxItem] = []
    for row in result:
        ch_num = cast(int, row.chapter_number)
        content = cast(str, row.content)
        sim = cast(float, row.similarity)
        items.append(
            RecallCtxItem(
                chapter_number=ch_num,
                content=content,
                score=round(sim, 4),
                source="vector",
            )
        )
    return items


# ---------------------------------------------------------------------------
# 阶段 2：tsvector 关键词召回
# ---------------------------------------------------------------------------


def _build_recall_tsquery_from_terms(terms: list[str]) -> str | None:
    """把关键词列表转为 tsquery（用 `|` OR 组合，受控决策 2）。

    V1 用 `websearch_to_tsquery('simple', ...)` 接受 OR 组合字符串。
    `websearch_to_tsquery` 在中文空白分隔时更宽容，对 `simple` 配置
    有效——每字符为一个 token，OR 组合多词时可召回任一匹配。

    空列表/空词返 None。

    受控决策 2：V1 tsvector 用 `simple` 配置——按空白/标点/字符边界朴素切分
    CJK。不引入 `zhparser`/`jieba` 等中文分词扩展。
    """
    if not terms:
        return None
    # 去重后 OR 组合：`websearch_to_tsquery('simple', ...)` 接受 OR 组合
    # 字符串。对 `simple` 配置，每字符为一个 token——OR 组合多词时召回
    # 任一匹配（V1 用 simple 配置，受控决策 2）。
    unique = list(dict.fromkeys(terms))  # 保序去重
    # websearch_to_tsquery 对 simple 配置有效——OR 组合多词时召回任一匹配。
    tsquery_parts = " | ".join(unique)
    return tsquery_parts if tsquery_parts else None


async def _keyword_recall(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    current_chapter: int,
    limit: int,
) -> list[RecallCtxItem]:
    """tsvector 关键词召回（AC1/AC3：阶段 2）。

    **关键词来源**：取当前章号附近 N 章（`chapters[current-5..current-1]`）的
    chapter_card 五要素文本去重分词作搜索 query tsquery。

    **搜索目标**（AC3）：
    - `chapter_card` 五要素（`what_happened`、`character_changes`、
      `new_facts_clues`、`unresolved_hooks`、`end_state`）
    - `story_thread.content`（仅 status='open'）
    - `embedding.content`（chunk 原文）

    用 PG `ts_rank` 近似 BM25 排序（`ts_rank(cd, query)`），取 top M。

    **V1 用 `simple` 配置**（受控决策 2）：不引入 `zhparser`/`jieba` 等中文
    分词扩展。`ts_rank` 对 `simple` 分词的结果排序——每字符为一个 token，
    对中文关键词匹配带噪声但可用。
    """
    if current_chapter <= 1:
        return []  # 第一章无前序关键词来源

    # 关键词来源：附近 N 章的 chapter_card 五要素文本去重分词。
    start_ch = max(1, current_chapter - _KEYWORD_SOURCE_WINDOW)
    end_ch = current_chapter - 1  # 不含当前章自身

    cards = await chapter_card_repo.list_recent_chapter_cards(
        session,
        user_id=user_id,
        project_id=project_id,
        before_number=current_chapter,
        limit=_KEYWORD_SOURCE_WINDOW,
    )
    # 过滤：只取章节号在 [start_ch, end_ch] 范围内的 card。
    cards_in_range = [
        c for c in cards if start_ch <= c.chapter_number <= end_ch
    ]

    # 从 cards_in_range 的五要素文本提取关键词。
    all_terms: list[str] = []
    for card in cards_in_range:
        for card_field in (
            card.what_happened,
            card.character_changes,
            card.new_facts_clues,
            card.unresolved_hooks,
            card.end_state,
        ):
            if card_field and card_field.strip():
                # V1 用 `simple` 分词——按空白/标点/字符边界切 token。
                # 对中文：每个非空白字符切为一个 token。
                tokens = _simple_tokenize_cjk(card_field.strip())
                all_terms.extend(tokens[:20])  # 每要素取前 20 个词防膨胀

    if not all_terms:
        return []

    tsquery = _build_recall_tsquery_from_terms(all_terms)
    if tsquery is None:
        return []

    items: list[RecallCtxItem] = []

    # 搜索 chapter_card 五要素（tsvector 在 content 类列上做全文检索）。
    # V1 在 Python 侧用 `simple` 配置生成的 tsvector + tsquery 过滤。
    # 实际 PG 查询：用 `to_tsvector('simple', content)` 而非 PG 默认配置。
    # 方法：在 SQL 中显式指定 `simple` 配置。
    card_sql = text(
        """
        SELECT cc.chapter_number,
               COALESCE(cc.what_happened, '') || ' ' ||
               COALESCE(cc.character_changes, '') || ' ' ||
               COALESCE(cc.new_facts_clues, '') || ' ' ||
               COALESCE(cc.unresolved_hooks, '') || ' ' ||
               COALESCE(cc.end_state, '') AS combined_text,
               ts_rank(
                 to_tsvector('simple', COALESCE(cc.what_happened, '') || ' ' ||
                   COALESCE(cc.character_changes, '') || ' ' ||
                   COALESCE(cc.new_facts_clues, '') || ' ' ||
                   COALESCE(cc.unresolved_hooks, '') || ' ' ||
                   COALESCE(cc.end_state, '')),
                 websearch_to_tsquery('simple', :tsq)
               ) AS rank
        FROM chapter_card cc
        WHERE cc.user_id = :uid
          AND cc.project_id = :pid
          AND to_tsvector('simple', COALESCE(cc.what_happened, '') || ' ' ||
            COALESCE(cc.character_changes, '') || ' ' ||
            COALESCE(cc.new_facts_clues, '') || ' ' ||
            COALESCE(cc.unresolved_hooks, '') || ' ' ||
            COALESCE(cc.end_state, '')) @@ websearch_to_tsquery('simple', :tsq)
        ORDER BY rank DESC
        LIMIT :lim
        """
    ).bindparams(
        uid=user_id,
        pid=project_id,
        tsq=tsquery,
        lim=limit,
    )
    result = await session.execute(card_sql)
    for row in result:
        ch_num = cast(int, row.chapter_number)
        combined = cast(str, row.combined_text)
        rank_score = cast(float, row.rank)
        items.append(
            RecallCtxItem(
                chapter_number=ch_num,
                content=combined,
                score=round(rank_score, 4),
                source="keyword",
            )
        )

    # 搜索 story_thread.content（仅 status='open'）。
    # 用 `to_tsvector('simple', content) @@ to_tsquery('simple', tsq)` 过滤。
    thread_sql = text(
        """
        SELECT st.content,
               st.last_touched_chapter_number AS chapter_number,
               ts_rank(to_tsvector('simple', st.content),
                       websearch_to_tsquery('simple', :tsq)) AS rank
        FROM story_thread st
        WHERE st.user_id = :uid
          AND st.project_id = :pid
          AND st.status = 'open'
          AND to_tsvector('simple', st.content) @@ websearch_to_tsquery('simple', :tsq)
        ORDER BY rank DESC
        LIMIT :lim
        """
    ).bindparams(
        uid=user_id,
        pid=project_id,
        tsq=tsquery,
        lim=limit,
    )
    result = await session.execute(thread_sql)
    for row in result:
        content = cast(str, row.content)
        ch_num = cast(int, row.chapter_number)
        rank_score = cast(float, row.rank)
        items.append(
            RecallCtxItem(
                chapter_number=ch_num,
                content=content,
                score=round(rank_score, 4),
                source="keyword",
            )
        )

    # 搜索 embedding.content（chunk 原文）。
    embed_sql = text(
        """
        SELECT e.chapter_number,
               e.content,
               ts_rank(to_tsvector('simple', e.content),
                       websearch_to_tsquery('simple', :tsq)) AS rank
        FROM embedding e
        WHERE e.user_id = :uid
          AND e.project_id = :pid
          AND to_tsvector('simple', e.content) @@ websearch_to_tsquery('simple', :tsq)
        ORDER BY rank DESC
        LIMIT :lim
        """
    ).bindparams(
        uid=user_id,
        pid=project_id,
        tsq=tsquery,
        lim=limit,
    )
    result = await session.execute(embed_sql)
    for row in result:
        ch_num = cast(int, row.chapter_number)
        content = cast(str, row.content)
        rank_score = cast(float, row.rank)
        items.append(
            RecallCtxItem(
                chapter_number=ch_num,
                content=content,
                score=round(rank_score, 4),
                source="keyword",
            )
        )

    # 去重：同一 (project_id, content) 的多个命中只留一条。
    seen: set[tuple[int, str]] = set()
    deduped: list[RecallCtxItem] = []
    for item in items:
        key = (item.chapter_number, item.content)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:limit]


# ---------------------------------------------------------------------------
# 阶段 3：RRF 融合
# ---------------------------------------------------------------------------


def _rrf_fuse(
    *,
    vector_items: list[RecallCtxItem],
    keyword_items: list[RecallCtxItem],
    k: int = _RRF_K,
    top_n: int = 20,
) -> list[RecallCtxItem]:
    """Reciprocal Rank Fusion（AC1：阶段 3）。

    `RRF_score = 1 / (k + rank_i)`，k 取 60（RRF 典型值）。

    对阶段 1 结果（rank_vector）和阶段 2 结果（rank_keyword）按排序位置
    （1-based）做 RRF 融合。陷阱⑦：RRF 对 rank 位置而非原始得分敏感——
    `rank_i` 用排序位置（1-based），不直接用得分值。

    向量段或关键词段任意为空时，返回另一段的前 top_n 条（不融合）。
    两段皆空 → 返回空列表。
    """
    # 空段降级：只有一段有结果时直接返回该段前 top_n。
    if not vector_items and not keyword_items:
        return []
    if not vector_items:
        return keyword_items[:top_n]
    if not keyword_items:
        return vector_items[:top_n]

    # 按 (item, rank) 的 rank 索引计算 RRF 得分。
    # vector 段：rank_vector[0]=rank 1, rank_vector[1]=rank 2, ...
    # keyword 段：rank_keyword[0]=rank 1, rank_keyword[1]=rank 2, ...
    rrf_scores: dict[tuple[int, str], float] = {}
    item_map: dict[tuple[int, str], RecallCtxItem] = {}

    for rank_idx, item in enumerate(vector_items, start=1):
        key = (item.chapter_number, item.content)
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank_idx)
        item_map[key] = item

    for rank_idx, item in enumerate(keyword_items, start=1):
        key = (item.chapter_number, item.content)
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank_idx)
        # 若已存在（同一 item 被两段命中），保留两段中更早的 rank 对应的 source。
        if key not in item_map:
            item_map[key] = item
        elif item.score > item_map[key].score:
            item_map[key] = item

    # 按 RRF 得分降序取 top_n。
    sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
    fused: list[RecallCtxItem] = []
    for key in sorted_keys[:top_n]:
        item = item_map[key]
        fused.append(
            dataclasses.replace(
                item,
                score=round(rrf_scores[key], 4),
                source="rrf_fused",
            )
        )
    return fused


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _simple_tokenize_cjk(text_str: str) -> list[str]:
    """V1 中文分词：按空白/标点/字符边界切 token（受控决策 2）。

    PG `simple` 配置对中文按空白/标点/字符边界切 token——每个非空白字符切为
    一个 token。本函数模拟此行为：按非字母/数字/中文字符边界切分。

    **V2 可换 `zhparser`/`jieba` 等中文分词扩展**（留注释标记）。
    """
    import re

    if not text_str or not text_str.strip():
        return []
    # 按空白/标点拆分 token（PG `simple` 配置近似）。
    tokens = re.findall(r"[\w一-鿿]+", text_str, re.UNICODE)
    # 去重、去停用词、去长度 ≤ 1 的 token（单字词召回信息量极低）。
    filtered = [t for t in tokens if len(t) > 1]
    return list(dict.fromkeys(filtered))  # 保序去重


def _is_null_provider(provider: EmbeddingProvider) -> bool:
    """判断是否为 NullEmbeddingProvider（AC4 降级）。"""
    # 延迟 import：防止在模块顶部加载时导入 NullEmbeddingProvider 引入
    # 不必要的依赖。
    from muse.providers.embedding_null import NullEmbeddingProvider

    return isinstance(provider, NullEmbeddingProvider)