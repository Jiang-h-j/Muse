"""create embedding + pgvector extension

Revision ID: 4c2c9a05cfe9
Revises: 8c55d1bfbdaf
Create Date: 2026-08-06 18:16:38.380990

Story 5.5：建 `embedding` 表 + pgvector 扩展 + HNSW 向量索引。

**手写迁移体（勿纯 autogenerate，陷阱①②）**：Alembic autogenerate
① 不会产 `CREATE EXTENSION`；② 不认识 pgvector `Vector` 类型（可能渲染成错误类型）；
③ 绝不会产 HNSW 向量索引（`USING hnsw`）。故 extension / Vector 列 / HNSW 索引全部手写。

顺序硬约束（陷阱①）：`CREATE EXTENSION IF NOT EXISTS vector` 必须在 `create_table`
之前——Vector 列类型依赖扩展已装。`IF NOT EXISTS` 保幂等（本地镜像 pgvector/pgvector:pg16
已带扩展，重跑不报错）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "4c2c9a05cfe9"
down_revision: str | Sequence[str] | None = "8c55d1bfbdaf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 向量维度：与 models/embedding.EMBEDDING_DIM 对齐（阿里 text-embedding-v3，1024）。
_EMBEDDING_DIM = 1024


def upgrade() -> None:
    """建 pgvector 扩展 + embedding 表 + 列级/复合唯一索引 + HNSW 向量索引。"""
    # ① 扩展必须先于建表（Vector 列类型依赖之）。IF NOT EXISTS 保幂等。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ② 建表：embedding 列用 pgvector Vector(1024)（顶部 import）。其余列/时间戳/主键
    #    照 chapter_card 建表范式。
    op.create_table(
        "embedding",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column("model_name", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            "chapter_number",
            "chunk_index",
            name="uq_embedding_user_project_chapter_chunk",
        ),
    )
    # ③ 2 列级索引（同 chapter_card 命名 ix_<table>_<col>）+ 复合唯一已在建表内。
    op.create_index(
        op.f("ix_embedding_project_id"), "embedding", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_embedding_user_id"), "embedding", ["user_id"], unique=False
    )

    # ④ HNSW 向量索引（余弦距离 vector_cosine_ops，与 5.6 RAG 余弦召回一致）。
    #    autogenerate 不会产此索引——手写 op.execute。
    op.execute(
        "CREATE INDEX ix_embedding_vector_hnsw "
        "ON embedding USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """反序删索引 + 删表；**不 drop extension**（扩展可能被其他对象依赖，删表即可）。"""
    # 先删 HNSW 向量索引 → 2 列级索引 → 表。**不 DROP EXTENSION vector**——同「建表迁移
    # 不清理共享资源」先例（扩展是库级共享资源，可能被将来其他表/对象依赖）。
    op.execute("DROP INDEX IF EXISTS ix_embedding_vector_hnsw")
    op.drop_index(op.f("ix_embedding_user_id"), table_name="embedding")
    op.drop_index(op.f("ix_embedding_project_id"), table_name="embedding")
    op.drop_table("embedding")
