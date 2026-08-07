---
baseline_commit: 7724d269d0650761af0a86de4ff183c63079e252
---

# Story 5.5: embedding 表 + EmbeddingProvider（pgvector）

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Muse 后端开发者，
I want 一张 pgvector embedding 表和可切换的 EmbeddingProvider 抽象，
so that 长篇故事的历史事实能被语义检索、为 RAG（Story 5.6）打底。

## Acceptance Criteria

**AC1（embedding 表 + pgvector 扩展 + HNSW 索引，AR8/AR10）**
**Given** AR8/AR10 要求向量库与关系数据同库
**When** 建表迁移执行
**Then** 先 `CREATE EXTENSION IF NOT EXISTS vector`，再建 `embedding` 表（pgvector `Vector` 列 + chunk 文本 + 元数据），带 `user_id`+`project_id`（NFR3），并对向量列建 HNSW 索引（pgvector 0.8.x）

**AC2（EmbeddingProvider 抽象 + 阿里实现，AR18，类比 LLMProvider）**
**Given** EmbeddingProvider 抽象（AR18，类比 `providers/base.py` 的 `LLMProvider`）
**When** 定义接口并实现
**Then** 定义 `EmbeddingProvider` 接口（`embed(texts) -> list[list[float]]` + `dimensions`），阿里 `text-embedding-v3`（1024 维）为默认实现，业务层只依赖接口；工厂 `get_embedding_provider` 按托管配置构造（`provider_not_supported` 留扩展点，同 LLM 工厂）

**AC3（章节投影时 chunk 化 + 向量化写入 embedding，接 Story 5.2 chapter-commit）**
**Given** 章节投影时（接 Story 5.2 chapter-commit）
**When** 定稿正文投影
**Then** 章节正文 chunk 化 + 向量化写入 `embedding`——**向量化调外部 API 在 chapter_commit 三表单事务之外**、**写入 embedding 行紧随其后独立事务**（受控决策 3：`chapter_commit` 保持「只做 DB 投影、不调 LLM/embedding」的分层）

**AC4（无 embedding 配置的降级，AR18）**
**Given** 无 embedding 配置的降级（AR18）
**When** 未配置托管 embedding（`settings.embedding_api_key` 为空）
**Then** 工厂返回 `NullEmbeddingProvider`（或投影侧 skip），投影/定稿**不阻断**——embedding 段跳过、只记 warning，RAG（5.6）退回纯 tsvector 关键词（召回质量下降但可用）

**AC5（数据不出境，NFR8）**
**Given** 数据不出境（NFR8）
**When** 选 embedding Provider
**Then** embedding（阿里）与 LLM（DeepSeek）同区、部署国内云，满足数据合规——配置项 base_url 指向阿里国内 endpoint，注释写明合规约束

## Tasks / Subtasks

- [x] **Task 1 (AC: 1)** — pgvector 扩展 + `embedding` 模型 + Alembic 迁移
  - [x] Subtask 1.1：新建 `backend/src/muse/models/embedding.py` 定义 `Embedding` 模型——继承 `Base, UUIDPKMixin, TimestampMixin`（同 chapter_card）；列：`user_id`(FK user, index)、`project_id`(FK project, index)、`chapter_number`(Integer NOT NULL)、`chunk_index`(Integer NOT NULL，一章多 chunk 的序号)、`content`(Text NOT NULL，chunk 原文，供 RAG 回读)、`embedding`(pgvector `Vector(1024)` NOT NULL)、`model_name`(Text NOT NULL server_default=""，记录产出向量的模型，便于换模型/审计维度漂移)。向量列用 `from pgvector.sqlalchemy import Vector`（依赖已在 pyproject.toml:13）
  - [x] Subtask 1.2：`__table_args__` 加复合唯一 `(user_id, project_id, chapter_number, chunk_index)`（名 `uq_embedding_user_project_chapter_chunk`）——幂等键：重跑投影覆盖/清删同章 chunk 不产生副本（见陷阱④「重跑先删后插」）
  - [x] Subtask 1.3：在 `backend/src/muse/models/__init__.py` 注册 `Embedding`（若该文件显式导入各模型供 Alembic autogenerate；照 chapter_card 既有注册方式）
  - [x] Subtask 1.4：新建迁移 `uv run alembic revision -m "create embedding + pgvector extension"`（**手改，勿纯 autogenerate**——autogenerate 不会产 `CREATE EXTENSION`，且不认识 `Vector` 类型 / HNSW 索引，见陷阱①②）：
    - `down_revision = "8c55d1bfbdaf"`（当前 head，`alembic heads` 已确认）
    - `upgrade()`：① `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` **必须在 create_table 之前**（Vector 列类型依赖扩展已装）；② `op.create_table("embedding", ...)`——`embedding` 列用 `pgvector.sqlalchemy.Vector(1024)`（迁移文件顶部 `from pgvector.sqlalchemy import Vector`）；③ 建 2 列级索引（`ix_embedding_user_id` / `ix_embedding_project_id`，同 chapter_card 命名）+ 复合唯一约束；④ **HNSW 向量索引**：`op.execute("CREATE INDEX ix_embedding_vector_hnsw ON embedding USING hnsw (embedding vector_cosine_ops)")`（余弦距离，与 5.6 RAG 余弦召回一致）
    - `downgrade()`：drop HNSW 索引 → drop 2 列级索引 → drop_table → **不 drop extension**（扩展可能被其他对象依赖，删表即可；同「建表迁移不清理共享资源」先例）
  - [x] Subtask 1.5：验证迁移可跑通——`MUSE_DB_READY=1 uv run alembic upgrade head` + `alembic check`（本地 PG 镜像 `pgvector/pgvector:pg16` 已带扩展，见 deferred-work.md:72）

- [x] **Task 2 (AC: 2, 5)** — EmbeddingProvider 抽象接口 + 阿里实现
  - [x] Subtask 2.1：新建 `backend/src/muse/providers/embedding_base.py`（**独立文件、勿并进 base.py**——base.py 顶部注释明写「禁止 import openai」，而阿里实现要 import openai；分文件隔离，同 base.py / deepseek.py 分离先例）：定义 `class EmbeddingProvider(ABC)`——抽象方法 `async def embed(self, texts: list[str]) -> list[list[float]]`（批量文本 → 向量列表，顺序对齐）+ 属性 `dimensions: int`（供建表维度校验/文档）。docstring 写明「业务层只依赖本抽象，换 embedding 供应商=换实现、不改业务层」（同 LLMProvider 立身之本）
  - [x] Subtask 2.2：新建 `backend/src/muse/providers/embedding_dashscope.py`（阿里百炼 DashScope，`text-embedding-v3` 1024 维）——**用 OpenAI 兼容接口**（DashScope 提供 OpenAI 兼容 endpoint，同 DeepSeek 走 base_url 切换的先例）：`AsyncOpenAI(api_key=..., base_url=settings.embedding_base_url)`，`await client.embeddings.create(model=..., input=texts, dimensions=1024)`，取 `resp.data[i].embedding`（**按 `.index` 排序回原顺序**，防乱序，见陷阱⑤）。空 `texts` 直接返 `[]`（不打 API）。构造签名 `(api_key, base_url, *, model=None, dimensions=1024)`，`model` 缺省用 `settings.embedding_model`
  - [x] Subtask 2.3：新建 `backend/src/muse/providers/embedding_null.py`——`class NullEmbeddingProvider(EmbeddingProvider)`：`embed` 恒返 `[]`（或对每条 text 返空——统一让投影侧据 `[]` skip 写入），`dimensions` 返 1024。用于「无 embedding 配置」降级（AC4），让业务层无需到处判 `if provider is None`
  - [x] Subtask 2.4：`backend/src/muse/core/settings.py` 新增 3 个配置项（照 `deepseek_api_key` 的**无 fail-fast 决策** + 详细注释）：`embedding_api_key: str = ""`（**Muse 自有托管 key**——受控决策：V1 embedding 只走托管、不开放 BYOK，理由见 Dev Notes 受控决策 1；空值触发 AC4 降级）、`embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"`（阿里国内 endpoint，NFR8 数据不出境，注释写明合规约束）、`embedding_model: str = "text-embedding-v3"`
  - [x] Subtask 2.5：`backend/src/muse/providers/embedding_factory.py` 新增 `get_embedding_provider() -> EmbeddingProvider`（**无 session/user_id 入参**——V1 托管单路径，不按用户 BYOK 分叉，不同于 `get_provider_for_user`）：`settings.embedding_api_key` 为空 → 返 `NullEmbeddingProvider`（AC4）；非空 → 返 `DashScopeEmbeddingProvider(api_key=settings.embedding_api_key, base_url=..., model=...)`。**V1 不做 embedding 用量记账**（受控决策 2：无 MeteredProvider 包裹，理由见 Dev Notes）——留注释指明 5.6/后续若要计量在此包裹

- [x] **Task 3 (AC: 3)** — embedding chunk 化 + 向量化 + 写入（接 chapter-commit 之后独立事务）
  - [x] Subtask 3.1：新建 `backend/src/muse/repositories/embedding_repo.py`（照 chapter_card_repo 写路径约定：不 commit、flush+refresh、租户守卫）：
    - `async def delete_by_chapter(session, *, user_id, project_id, chapter_number) -> int`——删本章全部旧 chunk 行（重跑投影「先删后插」保幂等，见陷阱④），返回删除行数
    - `async def bulk_insert(session, *, user_id, project_id, chapter_number, chunks: list[tuple[int, str, list[float]]]) -> int`——批量插入 `(chunk_index, content, embedding)`；`session.add_all([...])` + `flush`；不 commit；返回插入行数
    - `async def list_by_chapter(session, *, user_id, project_id, chapter_number) -> list[Embedding]`——按 (user_id, project_id, chapter_number) 取全部 chunk（升序 chunk_index），供测试断言 + 5.6 读用
  - [x] Subtask 3.2：新建 `backend/src/muse/rag/chunking.py`（`rag/` 目录已存在但空）——`def chunk_chapter_text(text: str, *, max_chars: int = 800, overlap: int = 100) -> list[str]`：按段落（`\n\n` 切）聚合到 ~`max_chars` 字上限的 chunk，超长段落硬切，相邻 chunk 留 `overlap` 字重叠（防语义截断）。**V1 用字符数近似、不做 token 精确切分**（同 count_tokens 「粗估够用」先例；embedding 模型有自身 token 上限，800 字 CJK ≈ 480 token 远低于阿里 8192 上限，安全）。空文本返 `[]`
  - [x] Subtask 3.3：新建 `backend/src/muse/services/embedding_projection_service.py`——`async def project_chapter_embeddings(*, user_id, project_id, chapter_number, chapter_text) -> None`：
    1. `provider = get_embedding_provider()`；`chunks = chunk_chapter_text(chapter_text)`
    2. `chunks` 为空 或 `isinstance(provider, NullEmbeddingProvider)` → **early return + logger.info**（AC4 降级，不打 API、不写库）
    3. **向量化调外部 API 在事务之外**（AC3、陷阱③）：`vectors = await provider.embed(chunks)`；`embed` 返 `[]`（Null 或空）→ early return
    4. 长度校验：`len(vectors) != len(chunks)` → `logger.warning` + return（不写半截，防错位）
    5. **独立事务写入**（陷阱③）：`async with async_session_maker() as session:` → `await embedding_repo.delete_by_chapter(...)`（先删旧 chunk，重跑幂等）→ `await embedding_repo.bulk_insert(..., chunks=list(zip(range(len(chunks)), chunks, vectors)), model_name=...)` → `await session.commit()`
  - [x] Subtask 3.4：**接入 finalize 投影链路**——修改 `backend/src/muse/services/chapter_service.py` 的 `finalize_and_project_chapter`：在 `chapter_projection_service.chapter_commit(...)` + `projection_session.commit()` **成功之后**，**新增一段** try/except 调 `embedding_projection_service.project_chapter_embeddings(chapter_text=<定稿正文>, ...)`。
    - **`chapter_text` 来源**：用 `existing.text`（finalize 入口已读的 chapter 行正文——不重读、不用 polisher 产物；embedding 要的是「实际定稿入库的正文」，见陷阱⑥，区别于 5.2 data-agent 用 polisher 产物）
    - **失败不向上抛 + 不回滚三表**（受控决策 3 同构「投影失败 ≠ 定稿失败」）：embedding 失败只 `logger.warning`/`logger.exception`——三表已 commit 成功、status 已 finalized，用户已收到成功响应；embedding 缺失只降级 RAG 召回质量（5.6 退 tsvector），**不阻断定稿、不回滚已成功的三表投影**。except 只吞预期异常（`ErrorEnvelope` / `Exception` 中的网络/API 类——参照现有 embedding 段独立于三表事务的定位）
  - [x] Subtask 3.5：**幂等重入衔接**——`finalize_and_project_chapter` 入口的幂等判定（已 finalized + chapter_card 存在 → 直接返回）当前**会跳过 embedding**。本 story **不改该幂等分支**（受控决策 4：embedding 缺失不作为「需补投影」的触发条件——避免每次幂等重入都重打 embedding API）；embedding 的补投影靠「下一章定稿」或后续 5.6 显式回填任务。**在 story file 待确认项登记**此局限

- [x] **Task 4 (AC: 1, 2, 3, 4)** — 单测覆盖
  - [x] Subtask 4.1：新建 `backend/tests/test_embedding_repo.py`（异步，照 test_chapter_projection_repo.py 风格）——`bulk_insert` + `list_by_chapter` 往返；`delete_by_chapter` 后重插「先删后插」幂等（同章重跑 chunk 数不翻倍）；租户守卫（别的 user/project 读不到）。**需真实 PG（pgvector 扩展）**——用 `MUSE_DB_READY=1` 条件跳过标记（照既有 repo 测试）
  - [x] Subtask 4.2：新建 `backend/tests/test_embedding_provider.py`——`NullEmbeddingProvider.embed` 恒返 `[]`；`DashScopeEmbeddingProvider` mock `AsyncOpenAI.embeddings.create` 返固定乱序 data（`.index` 打乱）→ 断言按 index 排序回原顺序（陷阱⑤）；空 `texts` 不打 API 直接返 `[]`；`get_embedding_provider` 在 `embedding_api_key` 空/非空两态返正确类型（AC4）
  - [x] Subtask 4.3：新建 `backend/tests/test_chunking.py`——短文本 1 chunk；长文本多 chunk 且相邻有 overlap 重叠；空文本 `[]`；超长单段落硬切
  - [x] Subtask 4.4：新建 `backend/tests/test_embedding_projection_service.py`——mock `get_embedding_provider` 返固定向量的 fake provider + mock `async_session_maker`（或用真实 session）：断言 chunk 化→向量化→写入链路；`NullEmbeddingProvider` 时 skip 不写库（AC4）；`len(vectors)!=len(chunks)` 时不写半截（陷阱错位防线）；**向量化异常时不抛、不影响调用方**（AC3 失败降级）
  - [x] Subtask 4.5：扩展 `backend/tests/test_chapter_finalize_api.py`——新增「定稿后 embedding 落库」用例（mock embedding provider 返固定向量，断言 finalize 后 `embedding` 表有本章 chunk 行）+「embedding 失败不影响定稿成功 + 三表仍落库」用例（mock provider 抛异常，断言 finalize 仍 200、chapter_card 仍在、status 仍 finalized）。**沿用既有 `@pytest.mark.real_pipeline` / autouse mock pipeline fixture 范式**（5.2 已建）

- [x] **Task 5** — 全量回归 + ruff + mypy + 收尾 story file
  - [x] Subtask 5.1：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q`（全量回归 ≥ 642 + 本 story 新增用例，零回归）
  - [x] Subtask 5.2：`uv run ruff check .` 全过 + 定向 `uv run mypy src/muse/providers/ src/muse/rag/ src/muse/services/embedding_projection_service.py src/muse/repositories/embedding_repo.py`（pgvector `Vector` 类型注解可能需 `# type: ignore` 或 stub，如遇 mypy 报错在 Completion Notes 记明口径）
  - [x] Subtask 5.3：填 File List + Completion Notes + Change Log；更新 sprint-status 5-5 → review（dev 完成后）

## Dev Notes

### 本 story 性质：全新落地（读三遍再动手）

Story 5.5 是 **Epic 5 RAG 链的地基**——`5.1→5.2→{5.3→5.4, 5.5→5.6}`，5.5/5.6 是 RAG 子链，在 5.2 后与归档页链（5.3/5.4）并行。**本 story 之前，全项目没有任何 embedding 代码、pgvector 扩展从未 `CREATE EXTENSION`**（`grep` 确认迁移/源码零引用；`providers/embedding.py`、`rag/retrieval.py` 架构文档提过但**尚未创建**——以本 story 实际落地文件名为准，见「Project Structure Notes」）。你是从零建：扩展 + 表 + Provider 抽象 + chunk 化 + 投影接入。

**5.5 只「写入 embedding」，不「读取召回」**——三级召回（向量+tsvector+RRF+rerank）+ 回改 4.4 写前上下文注入点全部归 **5.6**。本 story 交付「章节定稿后向量落库」，5.6 才把落好的向量查出来用。别越界实现召回。

### 5.2 待确认项 → 本 story 兑现（关键接续点）

5.2 dev notes「待确认项」明确把 embedding 交给 5.5（[Source: 5-2 待确认项 2]）：
> **【embedding 投影】5.5 纳入 chapter-commit**：AC2 写「+ `embedding` 见 Story 5.5」——本 story 不投 embedding；5.5 落地时在 `chapter_commit` 里追加 embedding 投影（**或紧随其后独立事务**）。

**创始人已拍板选「紧随其后独立事务」**（见受控决策 3）——不塞进 `chapter_commit` 单事务。理由：`chapter_commit` 的分层契约是「只做 DB 投影、不调 LLM/embedding」（[Source: chapter_projection_service.py:4-7 docstring]），把外部 embedding API 调用塞进三表单事务会①让外部 API 延迟/失败拖垮已成功的三表原子投影、②在事务内持有 DB 连接等外部 API（连接占用反模式，同 5.2 dismiss 的 B2）。故 embedding 走「三表 commit 成功后、独立事务写入、失败降级不回滚」。

### 现状代码事实（本 story 依赖/复用的既有实现）

- **Provider 抽象先例**：`providers/base.py`（`LLMProvider` ABC，**禁止 import openai**）+ `providers/deepseek.py`（**唯一允许 import openai**，`AsyncOpenAI` + base_url 切换 + async 全栈）+ `providers/factory.py`（`get_provider_for_user` 按 BYOK 分叉 + `MeteredProvider` 记账包裹 + `provider_not_supported` 扩展点）。**EmbeddingProvider 照此三分：`embedding_base.py`（抽象）/ `embedding_dashscope.py`（阿里实现，import openai）/ `embedding_factory.py`（工厂）**
- **建表模式先例**：`models/chapter_card.py`（`Base, UUIDPKMixin, TimestampMixin` + FK user/project 带 index + 复合唯一 + Text NOT NULL server_default）+ `migrations/versions/f472170cd859`（5.1 三表迁移范式）。**embedding 表照此 + pgvector `Vector` 列 + HNSW 索引手写迁移**
- **repo 写路径先例**：`chapter_card_repo.upsert_chapter_card`（不 commit、flush+refresh、租户守卫、get-or-create 幂等）+ `story_thread_repo`（不 commit、logger.warning 防线）
- **投影接入点**：`chapter_service.finalize_and_project_chapter`（[Source: chapter_service.py，约 L530-611]）——status 翻 finalized + commit → 独立事务跑 data-agent + `chapter_commit(projection_session)` + `projection_session.commit()` → **本 story 在此 commit 成功后追加 embedding 投影段**
- **settings 无 fail-fast 决策**：`deepseek_api_key: str = ""`（[Source: settings.py:71-77]）——业务配置非安全密钥，空值只导致调用报错不导致越权，故不加 model_validator。**embedding 三配置照此**
- **run 表复用**：`chapter_generation_run.steps` JSONB（data-agent 产物落此）——**本 story 不动 run 表 / pipeline**（embedding 不进五段流水线，是投影后独立步骤，见受控决策 5）
- **本地 PG 镜像带 pgvector**：`docker-compose.yml` 用 `pgvector/pgvector:pg16`（[Source: deferred-work.md:72]）——扩展可 `CREATE EXTENSION` 成功；CI/无 DB 环境用 `MUSE_DB_READY` 跳过 pgvector 相关测试

### 五个受控决策（Jianghj 2026-08-06 拍板 + 本 story 显式声明）

1. **V1 embedding 只走托管、不开放 BYOK**（密钥来源问答拍板）：理由——「很多用户不懂嵌入模型」，让用户配 embedding key 不现实；embedding 是系统内部一致性能力（RAG 打底），不是用户可感知的模型选择。故 `get_embedding_provider` **无 session/user_id 入参**、不查 `byok_key` 表、只读 `settings.embedding_*`。若未来要开放 BYOK embedding，再扩展工厂签名（同 LLM 工厂演进路径）
2. **V1 embedding 不做用量记账**（无 `MeteredProvider` 包裹）：理由——embedding 走托管归 Muse 账、成本远低于正文生成（1024 维嵌入 vs 5-10 次 LLM 生成调用）、且额度护栏（1.8）计量单位是 LLM tokens；V1 embedding 成本先不纳入护栏，避免过早耦合。留注释在 `embedding_factory.py` 指明「后续要计量在此包裹 MeteredEmbeddingProvider」
3. **embedding 投影 = chapter_commit 三表 commit 成功后、独立事务、失败降级不回滚**（事务边界问答拍板，见上「5.2 待确认项」）：向量化 API 调用在事务外，写入 embedding 行紧随独立事务；失败只 warning、不阻断定稿、不回滚三表
4. **幂等重入不把「embedding 缺失」作为需补投影的触发**：`finalize_and_project_chapter` 已 finalized + chapter_card 存在 → 直接返回（不改此分支）；避免每次幂等重入/重复定稿都重打 embedding API（成本+延迟）。embedding 补投影靠下一章定稿或 5.6 显式回填。**列入待确认项**
5. **embedding 不进五段流水线（run 表）**：五段流水线（context/drafter/reviewer/polisher/data_agent）是「生成一章正文」的编排，data_agent 产结构化 JSON 落 run.steps 供断点续跑。embedding 是「投影后的向量落库」，输入是定稿正文（已在 chapter 表）、无需断点续跑复用（重跑=重新 embed 幂等覆盖），故**不加进 PIPELINE 常量、不落 run.steps**——直接在 `finalize_and_project_chapter` 里调独立 service。避免污染 `_CHAPTER_TOTAL_STEPS`（5.2 已踩过 progress 卡 80% 的坑）

### 陷阱清单（看三遍）

**陷阱①：迁移必须 `CREATE EXTENSION` 且在建表前**。Vector 列类型依赖 `vector` 扩展已装。`op.execute("CREATE EXTENSION IF NOT EXISTS vector")` 放在 `op.create_table` **之前**。`IF NOT EXISTS` 保幂等（本地镜像已带扩展也不报错）。

**陷阱②：Alembic autogenerate 不认识 pgvector**。纯 `--autogenerate` 不会产 `CREATE EXTENSION`、可能把 `Vector` 列渲染成错误类型、绝不会产 HNSW 索引（`USING hnsw`）。**必须手写迁移体**（extension + Vector 列 + `op.execute` 建 HNSW 索引）。生成迁移骨架后逐行核对。

**陷阱③：向量化 API 调用在事务外，写入在独立事务内**。`provider.embed(chunks)` 是外部 HTTP 调用（可能几百 ms~数秒），**绝不在 DB 事务/session 块内调**（占用连接等外部 API）。顺序：① `embed()` 拿 vectors（无 session）→ ② `async with async_session_maker()` 独立事务 delete+insert+commit。与 5.2 的 chapter_commit（三表单事务）完全分开。

**陷阱④：重跑投影「先删后插」保幂等**。同章重复定稿/补投影时，若只 insert 会撞复合唯一约束或产重复 chunk。`project_chapter_embeddings` 写入前先 `delete_by_chapter`（删本章全部旧 chunk）再 `bulk_insert`——同一独立事务内，重跑覆盖不产副本（区别于 chapter_card 的 get-or-create upsert：embedding 一章多行、chunk 数可能变，先删后插最干净）。

**陷阱⑤：批量 embedding 结果按 `.index` 排序回原顺序**。OpenAI 兼容 `embeddings.create(input=[...])` 返回的 `resp.data` 理论按输入顺序，但**契约上带 `.index` 字段**——保险起见 `sorted(resp.data, key=lambda d: d.index)` 再取 embedding，防乱序导致 chunk 文本与向量错配（错配=RAG 召回张冠李戴，隐蔽且致命）。

**陷阱⑥：embedding 的 `chapter_text` 用 chapter 表实际定稿正文，不用 polisher 产物**。5.2 的 data-agent 用 polisher 段产物（pipeline 内局部变量，避免多一次 DB 往返）。但 embedding 在 `finalize_and_project_chapter` 里、chapter 行已 commit（`existing.text` 就是入库正文）——**直接用 `existing.text`**，语义上「向量化的是实际入库的定稿正文」，且避免从 run 表再解一次 polisher 产物。（注意 `existing` 是入口读的行，status 翻转用 upsert 保留了 text，`existing.text` 仍是定稿正文。）

**陷阱⑦：维度必须与建表 `Vector(1024)` 一致**。阿里 `text-embedding-v3` 支持 `dimensions` 参数（可选 1024/768/512 等），**显式传 `dimensions=1024`** 与建表列一致。若模型返回维度 ≠1024，pgvector 写入会报错——`DashScopeEmbeddingProvider` 构造固定 `dimensions=1024`，与 `settings`/建表三方对齐。换模型/换维度需同步改建表迁移（V1 锁死 1024，注释写明）。

**陷阱⑧：mypy 对 pgvector `Vector` 类型**。`pgvector.sqlalchemy.Vector` 可能无完整类型 stub，`Mapped[list[float]]` 注解 + `mapped_column(Vector(1024))` 或需 `# type: ignore[...]`。定向 mypy 若报错，在 Completion Notes 记明口径（同项目既有 `# type: ignore` 先例）。

### Project Structure Notes

- **新增（模型/迁移）**：`backend/src/muse/models/embedding.py`、`backend/migrations/versions/<新>_create_embedding.py`（+ `models/__init__.py` 注册）
- **新增（Provider）**：`backend/src/muse/providers/embedding_base.py`、`embedding_dashscope.py`、`embedding_null.py`、`embedding_factory.py`
  - 命名偏离架构文档：architecture.md:419 写 `providers/embedding.py`（单文件）。**实际按 base/deepseek/factory 三分先例落多文件**（LLMProvider 已如此，架构文档 llm.py 也实际拆成 base/deepseek/factory）——以代码先例为准，dev 时无需回改架构文档，在 Completion Notes 记明偏差理由
- **新增（RAG/服务/repo）**：`backend/src/muse/rag/chunking.py`（`rag/` 目录已存在空 `__init__.py`）、`backend/src/muse/services/embedding_projection_service.py`、`backend/src/muse/repositories/embedding_repo.py`
- **修改**：`backend/src/muse/core/settings.py`（+3 配置）、`backend/src/muse/services/chapter_service.py`（`finalize_and_project_chapter` 三表 commit 后追加 embedding 投影段）
- **不动**：`chapter_projection_service.py`（`chapter_commit` 三表单事务契约不变——embedding 不进此函数）、`orchestration/`（embedding 不进五段流水线）、`tasks/worker.py`、`routers/`（finalize 端点签名不变，router 零改）、前端、`rag/retrieval.py`（召回归 5.6，本 story 不建）
- **新增测试**：`test_embedding_repo.py`、`test_embedding_provider.py`、`test_chunking.py`、`test_embedding_projection_service.py`、扩展 `test_chapter_finalize_api.py`

### 上游依赖状态（均已就绪）

- `chapter` 表 + 定稿正文（4.4/4.7 done）
- 三张归档表 + chapter-commit 单事务投影 + `finalize_and_project_chapter`（5.2 done）
- pgvector 依赖装好（pyproject.toml:13）+ 本地 PG 镜像带扩展（deferred-work.md:72）
- Provider 抽象 + OpenAI SDK 兼容用法（2.1 done，DeepSeek 走 base_url 切换）
- settings 无 fail-fast 业务配置先例（1.8/2.1 done）

### Testing Standards

- repo/迁移测试：需真实 PG（pgvector 扩展），`MUSE_DB_READY=1` 条件跳过（照既有 repo 测试范式）
- provider 测试：mock `AsyncOpenAI.embeddings.create`（不打真实阿里 API），断言排序/空输入/降级
- service 测试：mock `get_embedding_provider` 返 fake provider，验证 chunk→embed→写入链路 + 降级 skip + 失败不抛
- API 测试：扩展 `test_chapter_finalize_api.py`，沿用 5.2 `@pytest.mark.real_pipeline` + autouse mock pipeline fixture
- **必跑**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q`（全量回归零回归）+ `uv run ruff check .` + 定向 mypy
- **端到端（建议 Jianghj 本地手测，不做 UI 自动化）**：配好 `EMBEDDING_API_KEY` 真实阿里 key，走「生成第 1 章→定稿」看 `embedding` 表是否落 chunk 行 + 维度 1024；再清空 key 重定稿看是否降级 skip 不报错

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.5]（1165-1191，AC 原文）
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5]（1053-1059：5.5→5.6 RAG 子链、按需建表 5.5 embedding）
- [Source: _bmad-output/planning-artifacts/architecture.md#焦点四-一致性机制迁移]（239-253：EmbeddingProvider 抽象、阿里/智谱、数据不出境、无 key 退 tsvector、clean-room）
- [Source: _bmad-output/planning-artifacts/architecture.md:106-112]（pgvector 0.8.x HNSW + RRF、真 BM25 需 pg_search V1 用 tsvector 近似）
- [Source: _bmad-output/planning-artifacts/architecture.md:230,451-452]（embedding 表定位、单事务 chapter-commit 投影 story_state/chapter_card/story_thread/embedding）
- [Source: _bmad-output/planning-artifacts/architecture.md:294,419]（表名单数 snake_case `embedding`、providers/embedding.py 结构落点）
- [Source: _bmad-output/implementation-artifacts/5-2-写后投影-data-agent-chapter-commit单事务.md]（chapter-commit 单事务 + 待确认项 2「embedding 见 5.5」+ 陷阱①session 边界 + finalize 投影链路）
- [Source: _bmad-output/implementation-artifacts/5-1-归档核心表落地chapter_card-story_thread-story_state.md]（建表迁移范式 + repo 写路径约定）
- [Source: backend/src/muse/providers/base.py]（LLMProvider 抽象——EmbeddingProvider 照此，禁 import openai）
- [Source: backend/src/muse/providers/deepseek.py]（唯一允许 import openai + AsyncOpenAI + base_url 切换——DashScope 实现照此）
- [Source: backend/src/muse/providers/factory.py]（工厂 + provider_not_supported 扩展点 + MeteredProvider 记账——embedding_factory 照此但 V1 无记账/无 BYOK 分叉）
- [Source: backend/src/muse/core/settings.py:71-83]（deepseek_api_key 无 fail-fast 决策 + 双档模型配置——embedding 三配置照此）
- [Source: backend/src/muse/models/chapter_card.py + migrations/versions/f472170cd859]（建表模型/迁移范式——embedding 表照此 + Vector 列 + HNSW）
- [Source: backend/src/muse/repositories/chapter_card_repo.py]（repo 写路径：不 commit、flush+refresh、租户守卫——embedding_repo 照此）
- [Source: backend/src/muse/services/chapter_service.py]（finalize_and_project_chapter 投影链路——本 story 三表 commit 后追加 embedding 段）
- [Source: backend/src/muse/services/chapter_projection_service.py:4-7]（chapter_commit「只做 DB 投影、不调 LLM」分层契约——embedding 不进此函数的理由）
- [Source: _bmad-output/implementation-artifacts/deferred-work.md:72]（pgvector 镜像口径 `pgvector/pgvector:pg16`）
- [Source: 记忆 project_muse_setting_fields]（设定圣经结构——chunk 化上下文参考）

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (claude-opus-4.8-joybuilder)

### Debug Log References

- `alembic check` 首轮报「Detected removed index ix_embedding_vector_hnsw」——`op.execute`
  建的 HNSW 索引 SQLAlchemy 元数据不可见。修法：在 `Embedding.__table_args__` 用
  `Index(..., postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})`
  显式声明，让元数据与 DB 一致；check 转「No new upgrade operations detected」。
- `test_oversize_single_paragraph_hard_split` 首轮失败（块长 > max_chars）：`_hard_split`
  已带重叠、`_apply_overlap` 又叠加一次导致超限。重写 chunking——内部按
  `effective = max_chars - overlap` 攒块（无重叠硬切），事后统一 `_apply_overlap` 拼
  overlap，拼接后正好 ≤ max_chars。

### Completion Notes List

- **AC1**：`models/embedding.py` 定义 `Embedding`（`Vector(1024)` 列 + `chunk_index` +
  `content` + `model_name`），复合唯一 `uq_embedding_user_project_chapter_chunk` + 2 列级
  index + HNSW 余弦索引（元数据用 `Index(postgresql_using="hnsw")` 声明，迁移用
  `op.execute` 建）。手写迁移 `4c2c9a05cfe9`：`CREATE EXTENSION IF NOT EXISTS vector` 在
  `create_table` 之前；`downgrade` 不 drop extension。`upgrade head` + `alembic check` 通过。
- **AC2/AC5**：Provider 三分——`embedding_base.py`（抽象，禁 import openai）/
  `embedding_dashscope.py`（阿里 OpenAI 兼容，`dimensions=1024`，按 `.index` 排序回原顺序）/
  `embedding_null.py`（降级）/ `embedding_factory.py`（`get_embedding_provider` 无
  session/user_id 入参、无记账包裹）。settings +3 配置（`embedding_api_key/base_url/model`，
  无 fail-fast，base_url 指阿里国内 endpoint 满足 NFR8）。
- **AC3**：`embedding_projection_service.project_chapter_embeddings`——向量化在事务外，写入
  独立事务（delete_by_chapter → bulk_insert → commit）。`chapter_service.finalize_and_
  project_chapter` 在三表 commit 成功后追加 embedding 段（独立 try/except 吞异常，`chapter_
  text=existing.text` 用 chapter 表实际定稿正文，陷阱⑥），不复用外层 except（避免 rollback
  三表）。`chapter_commit` / 五段流水线 / router 零改。
- **AC4**：无 key → 工厂返 `NullEmbeddingProvider` → 投影 skip（不打 API、不写库、不报错）；
  embedding 失败被 finalize 层吞、status 仍 finalized、三表仍落库。
- **mypy 陷阱⑧**：pgvector `Vector` + `Mapped[list[float]]` 定向 mypy **无报错、无需
  `# type: ignore`**（pgvector 自带 sqlalchemy stub）。`embedding_repo.delete_by_chapter`
  的 `.rowcount` 需 `cast(CursorResult, result)`（Result 基类无 rowcount 属性）。
- **架构文档命名偏差**（architecture.md:419 写单文件 `providers/embedding.py`）：实际按
  base/dashscope/null/factory 四分（LLMProvider 已如此先例）——以代码先例为准，未回改架构文档。
- **验证门禁**：`MUSE_DB_READY=1 MUSE_REDIS_READY=1 uv run pytest -q` → **663 passed / 2
  skipped**（基线 642 + 本 story 21 新增，零回归）；`ruff check .` 全过；定向 mypy
  `providers/ rag/ embedding_projection_service.py embedding_repo.py` → Success。
- **端到端（建议 Jianghj 本地手测，未做 UI 自动化）**：配 `EMBEDDING_API_KEY` 真实阿里 key，
  走「生成第 1 章→定稿」看 `embedding` 表落 chunk 行 + 维度 1024；清空 key 重定稿看降级 skip
  不报错。

### File List

**新增**
- `backend/src/muse/models/embedding.py`
- `backend/migrations/versions/4c2c9a05cfe9_create_embedding_pgvector_extension.py`
- `backend/src/muse/providers/embedding_base.py`
- `backend/src/muse/providers/embedding_dashscope.py`
- `backend/src/muse/providers/embedding_null.py`
- `backend/src/muse/providers/embedding_factory.py`
- `backend/src/muse/rag/chunking.py`
- `backend/src/muse/repositories/embedding_repo.py`
- `backend/src/muse/services/embedding_projection_service.py`
- `backend/tests/test_chunking.py`
- `backend/tests/test_embedding_provider.py`
- `backend/tests/test_embedding_repo.py`
- `backend/tests/test_embedding_projection_service.py`

**修改**
- `backend/src/muse/core/settings.py`（+3 embedding 配置）
- `backend/src/muse/services/chapter_service.py`（finalize 三表 commit 后追加 embedding 投影段 + import）
- `backend/tests/test_chapter_finalize_api.py`（+2 用例：embedding 落库 / embedding 失败不阻断）

**说明**：`models/__init__.py` 无需改（`load_all_models` 用 pkgutil 自动加载本包全部模型模块，
Subtask 1.3 自动满足）；`repositories/__init__.py` 为空、子模块直接导入。

### 待确认项（受控决策 4 局限登记）

- **幂等重入不补 embedding**：`finalize_and_project_chapter` 的幂等分支（已 finalized +
  chapter_card 存在 → 直接返回）在 embedding 投影段**之前** return，故重复定稿/幂等重入
  **不会补打 embedding**（受控决策 4：避免每次重入都重打 embedding API 的成本+延迟）。
  已有正文但 embedding 缺失（如首次定稿时未配 key、后补 key）的补投影，靠「下一章定稿」
  或后续 Story 5.6 显式回填任务——本 story 不做补投影触发。

## Change Log

- 2026-08-06：Story 5.5 落地——pgvector `embedding` 表 + HNSW 余弦索引 + Alembic 迁移
  `4c2c9a05cfe9`；EmbeddingProvider 抽象 + 阿里 DashScope 实现 + Null 降级 + 无 BYOK/无记账
  工厂；章节正文 chunk 化 + 定稿后独立事务向量化写入（接 finalize，失败降级不回滚三表）。
  663 passed / 2 skipped / ruff / 定向 mypy / alembic check 全过。
