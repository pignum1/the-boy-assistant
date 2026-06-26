"""add_sessions_table_and_task_session_id

Revision ID: ce9cf9e810ec
Revises: 751f5569dd1c
Create Date: 2026-06-02 13:41:43.449917
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce9cf9e810ec'
down_revision: Union[str, None] = '751f5569dd1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 创建 sessions 表
    op.create_table('sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('workspace_path', sa.String(length=500), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. 为 tasks 表添加 session_id 外键
    op.add_column('tasks', sa.Column('session_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'tasks_session_id_fkey', 'tasks', 'sessions',
        ['session_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('tasks_session_id_fkey', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'session_id')
    op.drop_table('sessions')
