"""add_mcp_servers_table

Revision ID: 2c91ee38c06b
Revises: c1b0e93681ac
Create Date: 2026-05-29 17:20:24.388198
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2c91ee38c06b'
down_revision: Union[str, None] = 'c1b0e93681ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create mcp_servers table
    op.create_table('mcp_servers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('transport', sa.String(length=20), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('command', sa.String(length=500), nullable=True),
    sa.Column('args', postgresql.ARRAY(sa.String()), nullable=True),
    sa.Column('env', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('api_key_ref', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )

    # 2. Remove old function/api tools — they cannot be used and must be
    #    re-discovered from MCP servers
    op.execute("DELETE FROM tools")

    # 3. Restructure tools table: drop old columns, add server_id FK
    op.drop_constraint('tools_name_key', 'tools', type_='unique')
    op.drop_column('tools', 'tool_type')
    op.drop_column('tools', 'mcp_server_url')
    op.add_column('tools', sa.Column('server_id', sa.Uuid(), nullable=False))
    op.create_foreign_key(None, 'tools', 'mcp_servers', ['server_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Re-add old tool columns
    op.add_column('tools', sa.Column('mcp_server_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True))
    op.add_column('tools', sa.Column('tool_type', sa.VARCHAR(length=20), autoincrement=False, nullable=False, server_default='mcp'))
    op.drop_constraint(None, 'tools', type_='foreignkey')
    op.drop_column('tools', 'server_id')
    op.create_unique_constraint('tools_name_key', 'tools', ['name'])
    op.drop_table('mcp_servers')
