"""归档域 ORM 模型：Embedding（章节正文向量 chunk，Story 5.5 建）。

**RAG 地基**（Epic 5 一致性链 5.5→5.6）：章节定稿后，正文被 chunk 化 + 向量化，
每个 chunk 落一行本表，供 Story 5.6 三级召回（向量 + tsvector + RRF + rerank）
查出「写前上下文」注入下一章生成。本 story 只「写入向量」，不「读取召回」——
召回归 5.6，别越界。

**写路径不在 chapter_commit 单事务内**（受控决策 3，Jianghj 2026-08-06 拍板）：
`chapter_projection_service.chapter_commit` 的分层契约是「只做 DB 投影、不调
LLM/embedding」；向量化是外部 HTTP 调用，塞进三表单事务会让外部 API 延迟/失败
拖垮已成功的三表原子投影、并在事务内持有 DB 连接等外部 API（连接占用反模式）。
故 embedding 走「三表 commit 成功后、独立事务写入、失败降级不回滚」。

**pgvector 向量列**：`embedding` 列 `Vector(1024)`——阿里 `text-embedding-v3`
默认 1024 维（陷阱⑦：建表维度必须与 provider `dimensions` 三方对齐；换维度需同步
改建表迁移）。向量列上建 HNSW 余弦索引（迁移里手写 `USING hnsw`，autogenerate
不认识 pgvector，见迁移文件陷阱①②）。
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from muse.models.base import Base, TimestampMixin, UUIDPKMixin

# 向量维度：阿里 text-embedding-v3 默认 1024。V1 锁死此值——建表列 / provider
# dimensions / settings 三方对齐（陷阱⑦）。换模型/换维度须同步改本常量 + 建表迁移。
EMBEDDING_DIM = 1024


class Embedding(Base, UUIDPKMixin, TimestampMixin):
    """某作品某章某个正文 chunk 的向量行；归属 user（租户根）+ project（作品）。

    表名单数 snake_case（与 chapter_card / story_bible / chapter 一致）。一章多行
    （按 chunk_index 序号），与 chapter_card「一章一行」不同——故用「先删后插」保
    重跑幂等（陷阱④），而非 get-or-create upsert。
    """

    __tablename__ = "embedding"

    # 一作品一章一 chunk 一行：(user_id, project_id, chapter_number, chunk_index)
    # 复合唯一——幂等键。重跑投影「先删后插」（delete_by_chapter → bulk_insert）不产
    # 副本；即便并发误插同 chunk_index 也被唯一约束兜底（同 chapter_card 复合唯一先例）。
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "chapter_number",
            "chunk_index",
            name="uq_embedding_user_project_chapter_chunk",
        ),
        # HNSW 余弦向量索引（与 5.6 RAG 余弦召回一致）。在模型元数据里显式声明——
        # 否则 `alembic check` 会把迁移里 op.execute 建的索引当作「DB 有、模型无」的漂移。
        # postgresql_using="hnsw" + postgresql_ops 让 SQLAlchemy 生成同名同定义索引。
        Index(
            "ix_embedding_vector_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    # 租户外键：指向 user 表（1.2）。index 支撑按 user_id 的租户过滤（NFR3）。
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False, index=True
    )
    # 归属作品：指向 project 表（1.4）。architecture.md:295 硬规——业务表必带
    # user_id + project_id；index 支撑「按作品/章召回 chunk」查询（5.6）。
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id"), nullable=False, index=True
    )

    # 第几章（从 1 起），与 chapter.chapter_number 对齐（Integer NOT NULL，不设
    # server_default，同 chapter_card.chapter_number——按定稿章号显式写入）。
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # 章内 chunk 序号（从 0 起）：一章多 chunk 的顺序标识，与复合唯一键共同去重。
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # chunk 原文：供 5.6 RAG 召回后回读原始文本注入上下文（向量只用于相似度检索，
    # 回读要原文）。Text NOT NULL——chunk 必有内容（空文本不产 chunk，见 chunking）。
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 向量列（pgvector Vector(1024)）：chunk 的语义向量。NOT NULL——有行即有向量。
    # mypy 对 pgvector Vector 无完整 stub，注解 Mapped[list[float]] + Vector(dim)。
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    # 产出该向量的模型名（如 text-embedding-v3）：便于换模型/审计维度漂移。
    # Text NOT NULL server_default=""（同 chapter_card 五要素「必备但可空串」先例——
    # 老数据/降级路径不爆约束）。
    model_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
