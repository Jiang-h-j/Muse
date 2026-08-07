---
baseline_commit: 7724d269d0650761af0a86de4ff183c63079e252
---

# Story 5.6: RAG 三级召回接回写前上下文

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 写长篇的用户，
I want 系统在写新章节时自动调取相关的历史设定与事实，
so that 就算写到几百章，故事也不会前后矛盾、跑偏穿帮。

## Acceptance Criteria

**AC1（RAG 三级召回：向量 + tsvector + RRF 融合 + rerank，AR18）**
**Given** RAG 三级召回（AR18）
**When** 实现召回
**Then** 向量（pgvector HNSW）+ tsvector 关键词 + RRF 融合 + rerank 三级召回——由 `rag/retrieval.py` 的 `recall_context_for_chapter(project_id, chapter_number, ...)` 函数实现，返回排序后的相关 chunk 列表（含 chunk 原文 + 章号 + 相似度得分）

**AC2（写前上下文增强：回改 context-agent 注入点，AR16/AR19）**
**Given** RAG 回头增强 Epic 4 写前上下文（架构原意「回头增强」）
**When** context-agent 组装写作任务书
**Then** 回改 `orchestration/steps.py` 的 `run_context_agent`——从「全量设定+最近定稿章节」升级为「story_bible + 最近 chapter_cards + 未回收 story_threads + 世界规则 + 主角状态 + RAG 召回的相关历史」（AR16），RAG 召回块作为 `【相关历史设定（RAG 召回，供本章参考）】` 段注入写作任务书

**AC3（真 BM25 V1 用 tsvector 近似，AR18）**
**Given** 真 BM25（pg_search）V1 用 tsvector 近似（AR18）
**When** V1 实现关键词召回
**Then** 用 PostgreSQL 原生 tsvector + `ts_rank` 近似 BM25，不引入 pg_search 扩展（视需要 V2 引入）。关键词字段对标 chapter_card 五要素 + embedding.content（chunk 原文）+ story_thread.content

**AC4（embedding 降级场景，接 Story 5.5）**
**Given** embedding 降级场景（接 Story 5.5）
**When** 无 embedding key（get_embedding_provider 返回 NullEmbeddingProvider）
**Then** RAG 退化为纯 tsvector 关键词召回 + 纯 chapter_cards/story_threads/story_state 注入——向量段自然返回空集（embedding 表为空或查询被跳过），tsvector 仍能提供基础一致性保障

**AC5（长程一致性保障，NFR4）**
**Given** 长程一致性（NFR4，不设章数上限）
**When** 故事写到几百章
**Then** RAG 召回通过语义检索 + 关键词匹配，让写前上下文覆盖长距离伏笔/设定，使状态/人物/世界规则/时间线不穿帮；`recall_context_for_chapter` 内部对召回结果做上限截断（防写前上下文暴涨挤爆 context window）

## Tasks / Subtasks

- [x] **Task 1（AC: 1, 4）** — `rag/retrieval.py`：recall_context_for_chapter 三级召回实现
  - [x] Subtask 1.1：新建 `backend/src/muse/rag/retrieval.py`（`rag/` 目录已有 `chunking.py`）。定义 `RecallCtxItem` dataclass（`chapter_number: int, content: str, score: float, source: str`——source 标记 `vector`/`keyword`/`rrf_fused`）和 `RecallResult` dataclass（`items: list[RecallCtxItem], metadata: dict`——含召回耗时/各段命中数/降级标志）
  - [x] Subtask 1.2：实现 `async def recall_context_for_chapter(session, *, user_id, project_id, current_chapter, limit=20) -> RecallResult`：
    - **阶段 1—向量召回**：检查 `get_embedding_provider()` 是否为 NullEmbeddingProvider → 是则 skip 降级（AC4）。否则：`select embedding.content, embedding.chapter_number, 1 - (embedding.embedding <=> query_embedding) AS cosine_sim`——对每章最新的 embedding chunk 做余弦距离查询，取 top N 的 `(chapter_number, content, score)`。query_embedding 用上一章（chapter_number=current_chapter-1）的全部 chunk embedding 的均值向量作查询向量（降级：如上一章无 embedding 则降级为纯 tsvector）。**余弦距离（`<=>`）返 0~1（距离越小越相似），`1 - <=>` 就是余弦相似度（越大越相似）**——排序用 `cosine_sim DESC`。HNSW 索引 `ix_embedding_vector_hnsw` 带 `vector_cosine_ops` 自动加速此查询（见 5.5 建 HNSW 余弦索引的决策）。
    - **阶段 2—tsvector 关键词召回**：对 `chapter_card` 的五要素字段（`what_happened`、`character_changes`、`new_facts_clues`、`unresolved_hooks`、`end_state`）+ `story_thread.content`（仅 status='open'）+ `embedding.content` 做 tsvector 全文检索。关键词：用当前章号附近 N 章的 chapter_card 五要素做关键词来源（取 `chapters[current-5..current-1]` 的五要素文本去重分词作为搜索 query tsquery）。`ts_rank(cd, query)` 排序取 top M。同一（project_id, chapter_number）的 tsvector 结果与向量结果按 source 标记，留待 RRF 融合。
    - **阶段 3—RRF 融合**：对阶段 1 结果（rank_vector）和阶段 2 结果（rank_keyword）做 Reciprocal Rank Fusion——`RRF_score = 1/(k + rank_i)`，k 取 60（RRF 典型值）。按 RRF 得分降序取 top limit。
    - **阶段 4—rerank（V1 用 RRF 排序代替，不做独立 rerank step）**：架构原文「三级检索向量 + tsvector + RRF 融合 + rerank」中的 rerank V1 直接用 RRF 排序后的 top N 作为最终结果（不做独立的 LLM/模型 rerank step）。**受控决策 1**：V1 以 RRF 排序代替独立 rerank，理由见 Dev Notes。留注释指明 V2 可加交叉编码器/LLM rerank step 增强排序质量。
    - 结果上限 `limit` 防写前上下文暴涨：默认 20 条（chunk + card + thread 混合）。metadata 含每段命中数、是否降级、总耗时约（log 级别，不做精确毫秒计时）。
  - [x] Subtask 1.3：阶段 2 tsvector 的辅助函数——`_build_recall_tsquery_from_terms(terms: list[str])`：将关键词列表转为 tsquery（用 `|` OR 组合词根化后搜索，`plainto_tsquery` 或 `websearch_to_tsquery` 保兼容性）
  - [x] Subtask 1.4：`_score_utf8(text: str)` 对中文 content 的 tsvector 支持验证——PG `tsvector` 对中文需要分词，V1 用 `simple` 配置（按空白/标点拆分 CJK 字符的朴素 token）做近似匹配。**受控决策 2**：V1 tsvector 用 `simple` 配置，理由见 Dev Notes。留注释标记 V2 可换 `zhparser`/`jieba` 等中文分词扩展。

- [x] **Task 2（AC: 2, 5）** — 写前上下文升级：context-agent 注入增强
  - [x] Subtask 2.1：`orchestration/steps.py` 新增 `_format_story_threads_block`——取未回收 story_threads（`story_thread_repo.list_open_by_project`，按 `last_touched_chapter_number DESC` 取最近活跃的若干条），渲染为「【未回收伏笔/线索（需在本章关注或回收）】」块
  - [x] Subtask 2.2：新增 `_format_story_state_block`——取 `story_state_repo.get_by_project`，渲染为「【当前故事状态（主角状态/世界规则/叙事位置）】」块
  - [x] Subtask 2.3：新增 `_format_recalled_block(recalled: RecallResult)`——把 RAG 召回结果渲染为「【相关历史设定（RAG 召回，供本章参考）】」块。格式：每条 `{source}[章{chapter_number}](score={score:.2f})：{content[:200]}...`（截断 200 字防上下文暴涨）。召回为空或降级时输出「（当前无相关历史设定召回）」提示。上限防超过 3000 字（≈ 15 条 ×200 字平均，大数上界用 metadata 理论上限限幅）。
  - [x] Subtask 2.4：**修改 `run_context_agent`**——在 Revisions 段写入前插入 RAG 块注入：开一个 `async with async_session_maker()` 新 session（现行 session 已在 recent_chapters 读出后结束），调 `recall_context_for_chapter(project_id, current_chapter, ...)` 取RecallResult，拼 recalled_block 注入任务书。注意：**RAG 调用不阻断**——若 recall_context 内部抛异常（如向量查询超时），catch 后只 `logger.warning` 跳过、不影响写作任务书组装（写上下文降级为无 RAG 块，等效于 4.4 基线行为）。
  - [x] Subtask 2.5：往 `run_context_agent` 的任务书（brief）追加三个新增块：
    - 在 `【前情提要（最近前序章节正文）】` 之后追加 `【未回收伏笔/线索】` 块（来自 story_threads）
    - 在设定块附近追加 `【当前故事状态】` 块（来自 story_state）
    - 在写作要求之前追加 `【相关历史设定（RAG 召回）】` 块（来自 RecallResult）
    - **三块为空/降级时写入空提示**，同 `_format_recent_chapters_block` 的典范做法
  - [x] Subtask 2.6：**适配 _RECENT_CHAPTERS_FOR_CONTEXT 与 RAG 的关系**——V1 保持 `_RECENT_CHAPTERS_FOR_CONTEXT=1` 且保留 recent_chapters 块（作为「最近一篇文章节全文」锚点，与「RAG 召回片段」互补）。RAG 召回提供长距离语义碎片，recent 章节提供最近章全文上下文。两者共存而非替换。

- [x] **Task 3（AC: 0）** — 新 repo 方法（若既有接口不足）
  - [x] Subtask 3.1：检查 `story_thread_repo.list_open_by_project` 是否已有接口（有，5.1 已建：按 `user_id + project_id + status=open` + `last_touched_chapter_number DESC` 排序，5.1 review 已确认）；若未做上限截断则追加 `limit` 参数
  - [x] Subtask 3.2：story_state 读法——`story_state_repo.get_by_project` 已存在（5.1 已建最小读法），直接复用
  - [x] Subtask 3.3：embedding 向量查询——`embedding_repo.list_by_chapter` 已有（按章逐一取向量）。本次在 `embedding_repo.py` 新增 `async def search_similar(session, *, user_id, project_id, query_embedding: list[float], limit: int, exclude_chapter: int|None) -> list[tuple[int, str, float]]`——`select embedding.chapter_number, embedding.content, 1-(embedding.embedding <=> query_embedding) AS cosine_sim`，`ORDER BY cosine_sim DESC`，`LIMIT limit`。`exclude_chapter` 可选排除当前章（当前章自身的 chunk 不应该被召回当作历史）
  - [x] Subtask 3.4：tsvector 召回——若需要新增 repo 方法（在 chapter_card_repo / embedding_repo / story_thread_repo上加 tsvector 全文检索方法），单文件新增对应 repo search 函数

- [x] **Task 4（AC: 0）** — 测试覆盖
  - [x] Subtask 4.1：`test_retrieval.py`（`test_rag_retrieval.py` 或 `test_retrieval.py`）——mock 三段召回中的 embedding/tsvector 查询，断言 RRF 排序 top N 正确；NullEmbeddingProvider 时降级为纯 tsvector 结果（AC4）；空结果时 recall 为 0 条不报错；query_embedding 构建逻辑（均值向量）在无上一章 embedding 时的降级行为
  - [x] Subtask 4.2：`test_orchestration_steps.py` ——扩展 existing 测试：`run_context_agent` 注入的新建三个块在章节正文中正确呈现；story_threads 为空 / story_state 空时输出空提示而非报错；recall_context 抛异常时 context-agent 降级成功（不抛错、等效于 4.4 基线行为）
  - [x] Subtask 4.3：`test_embedding_repo.py` ——若新增 search_similar 则在测试中覆盖：余弦距离排序正确性；`exclude_chapter` 排除生效；HNSW 索引加速不阻断（仅功能验证）
  - [x] Subtask 4.4：全量回归——`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q`（零回归）+ `uv run ruff check .` + 定向 mypy

- [x] **Task 5** — 收尾
  - [x] Subtask 5.1：填 File List + Completion Notes；更新 sprint-status 5-6 → review

## Dev Notes

### 本 story 性质：回头增强（读三遍再动手）

**Story 5.6 是 Epic 5 RAG 链的收官**——5.5 embed 写入 + 5.6 召回接回，辉映架构文档焦点四「三段闭环：①写前 context-agent → ②写后 data-agent → ③RAG 召回回头增强」（architecture.md:239-253）。Story 5.6 不新建任何表（消费 5.1 chapter_card/story_thread/story_state + 5.5 embedding），只建设 `rag/retrieval.py` 召回逻辑 + 回改 `orchestration/steps.py context_agent` 注入点。

**核心改动量**：
1. 全新 `rag/retrieval.py` ~100-150 LOC（三级召回编排 + 辅助函数）
2. 修改 `orchestration/steps.py` 追加 3 个块格式化函数 + 在 `run_context_agent` 尾部插入 RAG 块 + 开独立 session 调 recall
3. 可能新增 `embedding_repo.py` 的 `search_similar` 方法
4. 可能新增 repo 层 tsvector 检索方法
5. 新增测试文件 + 扩展现有测试

**此故事前面 5 个 story 均已 done**：5.1 三张归档表（chapter_card/story_thread/story_state）+ 5.2 投影写入 + 5.3/5.4 归档页前端 + 5.5 embedding 写入。所有依赖均已就绪。

### 五个受控决策（Jianghj 拍板 + 本 story 显式声明）

1. **V1 无独立 rerank step**（以 RRF 排序代替）：架构原文「三级：向量 + tsvector + RRF 融合 + rerank」中的「rerank」V1 不做独立步骤——RRF 排序结果 top N 直接作为最终召回。理由：①独立 rerank（交叉编码器/LLM）需要额外模型调用 + 延迟，V1 内测阶段召回结果量级不大（几十条级），RRF 排序已提供基线质量。②待内测后有召回质量数据再决定投入独立 rerank。**留注释在 retrieval.py 标记 V2 可增强**。

2. **V1 tsvector 用 `simple` 配置做中文近似**：PG 原生 tsvector 对中文需要分词（`simple` 按空白/标点/字符边界朴素切分 CJK）。V1 用 `simple` 近似，召回质量不及专用中文分词（`zhparser`/`jieba`），但零外部依赖、零安装成本、能跑通。**留注释标记 V2 可换中文分词扩展**。

3. **query_embedding 用上一章均值向量**：以当前要写章节的上一章正文 chunk embedding 均值作查询向量，召回「语义上与上一章相似的历史章节」。理由：长篇里「场景/设定切换」通常跨章发生，上一章的最新事实最能召回同类话题的历史段落。降级：上一章无 embedding（如 key 后补）→ 降级为纯 tsvector。

4. **RAG 召回不阻断写前上下文组装**：`recall_context_for_chapter` 内的异常（embedding 查询/tsvector 超时/Repo 异常）被 `run_context_agent` 的 try/except 包裹 —— catch 后只 `logger.warning` 跳过、任务书无 RAG 块（等效 4.4 行为）。理由：写章节不能因 RAG 召回失败而中断；RAG 是增强而非必备，降级后已有 story_bible + 最近章节 + story_state + story_threads 相结合的基础上下文。

5. **RAG 召回结果上限受控截断防上下文暴涨**：默认 limit=20 条（混合来源），每条格式化后最大约 250 字，合计上限 ~5000 字放在写作任务书中。加上 story_bible（~1500 字）+ story_state 块（~600 字）+ story_threads 块（~500 字）+ 最近前序章节正文（~2500 字）+ style_profile（~200 字）+ revision 块（~1500 字），整份写作任务书理论上限 ~15000 字。在 DeepSeek 128K 上下文中占比 ~11%，安全。

### 现状代码事实（本 story 依赖/复用的既有结构）

- **context-agent 接口**（`orchestration/steps.py:208-293`）：`run_context_agent` 当前已注入：confirmed 12 字段设定 + style_profile + 去 AI 味词表约束 + chapter_idea + 前序章节正文（`_RECENT_CHAPTERS_FOR_CONTEXT=1` 取最近 1 章）+ revision 块。**本 story 不替换任何现有块，只追加 3 个新块**（story_threads / story_state / recalled_block）。函数体在当前 session 关闭后（L256）拼装纯文本，先过 session 取数据、后拼装——本 story 追加 recall 时需开第二个 session（在 L256 外侧已无存活session）。
- **chapter_card 五要素字段**：`what_happened` / `character_changes` / `new_facts_clues` / `unresolved_hooks` / `end_state`（model L90-L100）——tsvector 关键词召回的目标字段之一。
- **story_thread 字段**：`content` / `status` / `last_touched_chapter_number`（model L75-L95）——`list_open_by_project` 按 `status='open'` 筛选 + `last_touched_chapter_number DESC` 排序已就绪（5.1 review 已确认），RAG 取 `limit` 条活跃 thread。
- **story_state 字段**：`protagonist_state` / `world_rules_state` / `current_stage`（model L71-L80）——`get_by_project` 已就绪（5.1 最小读法），本 story 直接取三列渲染。
- **embedding 模型**：`content`（chunk 原文）/ `embedding`（`Vector(1024)` 向量列）/ `chapter_number`——HNSW 余弦索引 `ix_embedding_vector_hnsw` 已建（5.5），`<=>` 余弦距离查询自动走索引。
- **Provider 先例**：`get_embedding_provider()` 工厂一次性构造（无 session 入参），NullEmbeddingProvider 时 `embed()` 恒返 `[]`（embedding_repo 自然为空集）。5.5 的 `embedding_null.py` 可用于本 story 判断是否降级。
- **_settings 配置**：`embedding_api_key / embedding_base_url / embedding_model` 三个配置已在 5.5 settings.py 追加。

### 陷阱清单

**陷阱①：context-agent 现有 session 已完成，RAG 召回要开独立 session。** `run_context_agent` L232-254 在 `async with async_session_maker()` 内读写 project/bible/chapters 后 session 已关闭（L254 缩进退出）。L256 之后全是纯文本拼装。RAG 调用 `recall_context_for_chapter` 需要独立 session——**在拼装段（L274 写 brief 之前）开一个新 `async with async_session_maker()` session**，调 recall 后关闭，再接拼装。

**陷阱②：RAG 块不可在「无更好替代」时占据最近前序章节正文的位置。** 两个块各自独立、不互斥——`_format_recalled_block` 插入 recalled_block，不做成「有 RAG 召回时隐藏最近前序正文」的逻辑。任务书读者（drafter LLM）需要同时看到「最近一章的完整正文」和「长程相关片段」两个信息来源。

**陷阱③：tsvector query 构建须处理中文分词不足。** `tsvector` on CJK with `simple` config 会按空白/标点/字符边界切 token——意味着「程野」被切为「程」和「野」两个 token。`websearch_to_tsquery('程野')` 会搜不到复合词。**受控决策 2 已授权此局限**。搜索时用 `OR` 组合各关键词的 `plainto_tsquery`（自动处理标点的短语保留尝试），对纯中文可接受召回下降。

**陷阱④：均值向量构建不能假设上一章 embedding 必存在。** 降级场景（5.5 null embedding）或 5.5 仅在部分章跑过 embedding 时，`current_chapter - 1` 可能无 embedding 行。回退策略：取当前作品中 chapter_number 最接近 current_chapter 且有 embedding 的上一章作为 query。若全作品无任何 embedding 行 → 降级为纯 tsvector（AC4）。

**陷阱⑤：结果上限截断可能导致重要伏笔被排除。** RRF 排序取 top 20 可能遗漏某个埋在 80 章前的关键伏笔（低频率但高重要性）。V1 不做额外缓解——受控决策接受此折衷。留注释描述 V2 可考虑「重要性加权」或按 thread `last_touched_chapter_number` 距离做额外优先级补偿。

**陷阱⑥：tsvector 索引未建。** 在 chapter_card / story_thread / embedding 表的 content 类字段上建 `GIN` tsvector 索引可以加速关键词召回。但 V1 召回规模小（单作品几百章级），不建也够用。**归 V2**：若内测出现 tsvector 召回延迟，再建 `GIN idx_xxx_fts ON xxx USING gin(to_tsvector('simple', content_column))`。索引定义不出现在 `__table_args__` 中（与 embedding 的 HNSW 不同，tsvector 索引是迫不得已时才加的性能优化）。

**陷阱⑦：`1 - (embedding <=> query_embedding)` 的得分语义。** `<=>` 是余弦距离（0=完全相同，1=完全不相似），`1 - <=>` 是余弦相似度（1=完全相同，0=完全不相似）。RRF 融合时需要归一化得分。注意：其他字段（ts_rank）得分在 0-1 之间不均匀分布，RRF 对 rank 位置而非原始得分敏感——`rank_i` 用排序位置（1-based），不直接用得分值。

**陷阱⑧：现有测试 fixture 中的 `_patch_step` 模式。** `test_orchestration_steps.py` 用 `_patch_step` mock `async_session_maker` 和相关 repo 方法。本 story 需 mock `recall_context_for_chapter`，沿用此范式。

### Project Structure Notes

- **新增**：`backend/src/muse/rag/retrieval.py`（RAG 三级召回编排——向量 + tsvector + RRF + rerank 占位）
- **修改（核心）**：`backend/src/muse/orchestration/steps.py`——`run_context_agent` 追加 RAG 块 + story_threads 块 + story_state 块 + 独立 session recall 调用；新增 3 个 `_format_*` 函数
- **可能新增（repo）**：`embedding_repo.py` 新增 `search_similar`（若不在 retrieval.py 内联 SQLAlchemy 查询）
- **可能新增（tsvector repo）**：chapter_card_repo / story_thread_repo / embedding_repo 新增 tsvector 全文检索方法（若不在 retrieval.py 内联）
- **不动**：`chapter_projection_service.py`（embedding 写入已归 5.5，5.6 只读），`embedding_projection_service.py`（写入不动），`rag/chunking.py`（chunk 方式不动），`providers/`（embedding provider 不动），`routers/`（context-agent 无 API 变更，routers 零改），前端，测试 fixture 现有 mock 范式（扩展而非修改）
- **新增测试**：`test_rag_retrieval.py`（或 `test_retrieval.py`）；扩展 `test_orchestration_steps.py` + 若新增 repo 方法则扩展对应 repo 测试

### 上游依赖状态（均已就绪）

- `chapter` 表 + 定稿正文（4.4/4.7 done）
- `chapter_card` / `story_thread` / `story_state` 三表 + repo 读法（5.1 done）
- `chapter-commit` data-agent 投影写入（5.2 done）
- embedding 表 + HNSW 索引 + EmbeddingProvider 抽象 + chunk 化 + 向量写入（5.5 done）
- `run_context_agent` 组装写作任务书 + `_RECENT_CHAPTERS_FOR_CONTEXT` 最近 1 章前序注入（4.4 done）
- 5.5 settings 三配置（`embedding_api_key`/`base_url`/`model`）就绪
- PG pgvector 扩展 `vector` 已装（本地镜像 `pgvector/pgvector:pg16`）

### Testing Standards

- retrieval 测试：mock embedding provider（返 null provider / fake provider）+ mock session 层的 [`<=>` 查询、tsvector 查询] → 断言 RRF 排序 + 降级 + 空结果
- context-agent 扩展测试：沿用 `_patch_step` fixture 范式，mock `recall_context_for_chapter` 返固定 RecallResult → 断言任务书中包含正确的 recalled_block / story_threads_block / story_state_block；mock 抛异常 → 断言任务书无 RAG 块但其他块完整（降级不阻断）
- repo 测试（若新增）：需真实 PG（pgvector 扩展），`MUSE_DB_READY=1` 条件跳过
- **必跑**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q`（全量回归零回归）+ `uv run ruff check .` + 定向 mypy

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.6]（1193-1219，AC 原文）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5]（1053-1059：5.5→5.6 RAG 子链）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点四-一致性机制迁移]（239-253：RAG 三级召回、EmbeddingProvider 抽象、阿里/智谱、数据不出境、无 key 退 tsvector、clean-room）
- [Source: _bmad-output/planning-artifacts/architecture.md:106-112]（pgvector 0.8.x HNSW + RRF、真 BM25 需 pg_search V1 用 tsvector 近似）
- [Source: _bmad-output/planning-artifacts/architecture.md:230,451-452]（embedding 表定位、单事务 chapter-commit 投影 story_state/chapter_card/story_thread/embedding）
- [Source: _bmad-output/planning-artifacts/architecture.md:294,419-421]（表名单数 snake_case `embedding`、rag/retrieval.py 结构落点、焦点四上下文注入）
- [Source: _bmad-output/implementation-artifacts/5-5-embedding表-EmbeddingProviderpgvector.md]（embedding 表结构 1024 维 HNSW、NullEmbeddingProvider 降级、chunking 策略）
- [Source: backend/src/muse/orchestration/steps.py:208-293]（run_context_agent 现有注入点——本 story 追加 RAG + story_threads + story_state 块）
- [Source: backend/src/muse/models/embedding.py + chapter_card.py + story_thread.py + story_state.py]（四张检索目标表的字段结构）
- [Source: backend/src/muse/repositories/embedding_repo.py]（现有 list_by_chapter，需新增 search_similar）
- [Source: backend/src/muse/repositories/story_thread_repo.py:51-66]（`list_open_by_project`——未回收伏笔取法已就绪）
- [Source: backend/src/muse/repositories/story_state_repo.py:27-44]（`get_by_project`——当前故事状态取法已就绪）
- [Source: backend/src/muse/repositories/chapter_card_repo.py:116-141]（`list_recent_chapter_cards`——最近前序章节卡取法已就绪）
- [Source: backend/src/muse/providers/embedding_factory.py]（`get_embedding_provider`——降级判断入口）

## Dev Agent Record

### Agent Model Used

Sonnet 4.6 (claude-sonnet-4-6-20250627)

### Debug Log References

### Completion Notes List

**Story 5.6 三级召回 + 写前上下文升级已完成（2026-08-07）**：
- `rag/retrieval.py`（新建 ~250 LOC）：三级召回编排——向量（pgvector 余弦距离）+ tsvector（PG 原生 `simple` 全文检索）+ RRF 融合（k=60）+ rerank 占位。降级：NullEmbeddingProvider 时跳过向量段退纯 tsvector。
- `orchestration/steps.py`（修改 ~120 LOC）：新增 3 个格式化函数（`_format_story_threads_block`、`_format_story_state_block`、`_format_recalled_block`）+ `run_context_agent` 中追加 RAG 独立 session 调用 + 三个新块注入写作任务书（不替换任何现有块，只追加）。RAG 调用不阻断——异常时只 logger.warning 跳过，等效 4.4 基线行为。
- `story_thread_repo.py`（修改 ~3 LOC）：`list_open_by_project` 新增 `limit` 参数（SQL 层 limit，0=全量）。
- 测试：`test_rag_retrieval.py`（19 条单元测试）+ `test_orchestration_steps.py`（4 条扩展测试），零回归、ruff+mypy 通过。

### File List

**新增**
- `backend/src/muse/rag/retrieval.py`（三级召回编排——recall_context_for_chapter + RecallCtxItem/RecallResult dataclass + RRF 融合 + 辅助函数）

**修改**
- `backend/src/muse/orchestration/steps.py`（run_context_agent 追加 RAG 块 + story_threads 块 + story_state 块 + 3×_format_* 函数 + 独立 session recall；新增 import: story_state_repo, story_thread_repo, RecallResult, recall_context_for_chapter）
- `backend/src/muse/repositories/story_thread_repo.py`（list_open_by_project 新增 limit 参数——SQL 层截断，0=全量）
- `backend/tests/test_orchestration_steps.py`（_patch_step 新增 story_state_repo + story_thread_repo mock + 4 个 Story 5.6 扩展测试）

**新增测试**
- `backend/tests/test_rag_retrieval.py`（三级召回单元测试——RRF 融合、降级、空结果、embedding 降级、均值向量构建）

## Change Log

- 2026-08-07: Story 5.6 implemented — RAG 三级召回 (retrieval.py) + 写前上下文升级 (steps.py) + 测试覆盖 (19 + 4 new tests)