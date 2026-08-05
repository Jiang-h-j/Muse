"""create chapter

Revision ID: 55130c002b17
Revises: a7c31f9d2e04
Create Date: 2026-08-05 12:24:09.636308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55130c002b17'
down_revision: Union[str, Sequence[str], None] = 'a7c31f9d2e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    纯新增业务表 chapter（Story 4.4 章节终稿正文落库）：照 stage_plan 迁移范式
    （a7c31f9d2e04）——多租户 user_id+project_id（FK+index）、(user_id, project_id,
    chapter_number) 复合唯一（幂等键，重生成 upsert 同行）、text Text、revision/status
    留 4.6 升版 / 4.7 定稿扩展位。
    """
    op.create_table('chapter',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('project_id', sa.Uuid(), nullable=False),
    sa.Column('chapter_number', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), server_default='', nullable=False),
    sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('status', sa.Text(), server_default='draft', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'project_id', 'chapter_number', name='uq_chapter_user_project_number')
    )
    op.create_index(op.f('ix_chapter_project_id'), 'chapter', ['project_id'], unique=False)
    op.create_index(op.f('ix_chapter_user_id'), 'chapter', ['user_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema.

    纯新增表，无 alter：直接删索引 + 删表即可（chapter 整表随之丢弃，有数据损失，仅用于
    开发/回滚场景）。
    """
    op.drop_index(op.f('ix_chapter_user_id'), table_name='chapter')
    op.drop_index(op.f('ix_chapter_project_id'), table_name='chapter')
    op.drop_table('chapter')
