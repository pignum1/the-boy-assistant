"""add_skill_mcp_to_persona_drop_model_params

Revision ID: 9a1b2c3d4e5f
Revises: 8dafe2034592
Create Date: 2026-06-01 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, None] = '8dafe2034592'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('personas', sa.Column('skill_ids', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('personas', sa.Column('mcp_server_ids', postgresql.ARRAY(sa.String()), nullable=True))
    op.drop_column('personas', 'temperature')
    op.drop_column('personas', 'max_tokens')
    op.drop_column('personas', 'top_p')
    op.drop_column('personas', 'tools_declared')


def downgrade() -> None:
    op.add_column('personas', sa.Column('tools_declared', postgresql.ARRAY(sa.VARCHAR()), autoincrement=False, nullable=True))
    op.add_column('personas', sa.Column('top_p', sa.FLOAT(), autoincrement=False, nullable=True, server_default='1.0'))
    op.add_column('personas', sa.Column('max_tokens', sa.INTEGER(), autoincrement=False, nullable=True, server_default='4096'))
    op.add_column('personas', sa.Column('temperature', sa.FLOAT(), autoincrement=False, nullable=True, server_default='0.7'))
    op.drop_column('personas', 'mcp_server_ids')
    op.drop_column('personas', 'skill_ids')
