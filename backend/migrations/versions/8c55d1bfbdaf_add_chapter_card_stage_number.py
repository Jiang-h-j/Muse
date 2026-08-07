"""add chapter card stage number

Revision ID: 8c55d1bfbdaf
Revises: f472170cd859
Create Date: 2026-08-06 14:44:32.835919

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c55d1bfbdaf"
down_revision: str | Sequence[str] | None = "f472170cd859"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为章节归档卡添加不可变阶段归属，并尽力回填已有历史卡。"""
    op.add_column(
        "chapter_card",
        sa.Column("stage_number", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_chapter_card_stage_number"),
        "chapter_card",
        ["stage_number"],
        unique=False,
    )

    # 旧卡没有阶段归属。按迁移执行时的 stage_plan 顺序和每个计划的章数，回填其
    # 所属全局章节区间；无计划、计划已缩短或章号超出范围的卡保留 NULL，由归档
    # API 放进“未归类归档”组，而不是错误塞入别的阶段或直接隐藏。
    op.execute(
        """
        WITH stage_ranges AS (
            SELECT
                user_id,
                project_id,
                stage_number,
                COALESCE(jsonb_array_length(chapters), 0) AS chapter_count,
                COALESCE(
                    SUM(COALESCE(jsonb_array_length(chapters), 0)) OVER (
                        PARTITION BY user_id, project_id
                        ORDER BY stage_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS chapter_offset
            FROM stage_plan
        )
        UPDATE chapter_card AS card
        SET stage_number = ranges.stage_number
        FROM stage_ranges AS ranges
        WHERE card.user_id = ranges.user_id
          AND card.project_id = ranges.project_id
          AND card.chapter_number > ranges.chapter_offset
          AND card.chapter_number <= ranges.chapter_offset + ranges.chapter_count
        """
    )


def downgrade() -> None:
    """移除章节卡阶段归属（会丢弃该历史归属信息）。"""
    op.drop_index(op.f("ix_chapter_card_stage_number"), table_name="chapter_card")
    op.drop_column("chapter_card", "stage_number")
