"""create stage_plan

Revision ID: a7c31f9d2e04
Revises: e5e0b47fef12
Create Date: 2026-08-04 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c31f9d2e04'
down_revision: Union[str, Sequence[str], None] = 'e5e0b47fef12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    纯新增表 stage_plan（Story 4.3 幕后阶段规划落库）：照 chapter_generation_run 迁移范式
    （e5e0b47fef12）——多租户 user_id+project_id（FK+index）、(user_id, project_id,
    stage_number) 复合唯一（幂等键，留阶段循环扩展位）、goal Text、chapters JSONB。
    """
    op.create_table('stage_plan',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('stage_number', sa.Integer(), server_default='1', nullable=False),
    sa.Column('goal', sa.Text(), server_default='', nullable=False),
    sa.Column('chapters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'project_id', 'stage_number', name='uq_stage_plan_user_project_stage')
    )
    op.create_index(op.f('ix_stage_plan_project_id'), 'stage_plan', ['project_id'], unique=False)
    op.create_index(op.f('ix_stage_plan_user_id'), 'stage_plan', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    纯新增表，无 alter：直接删索引 + 删表即可（stage_plan 整表随之丢弃，有数据损失，仅用于
    开发/回滚场景）。
    """
    op.drop_index(op.f('ix_stage_plan_user_id'), table_name='stage_plan')
    op.drop_index(op.f('ix_stage_plan_project_id'), table_name='stage_plan')
    op.drop_table('stage_plan')
