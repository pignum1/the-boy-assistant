"""Alembic Migration Template

Revision ID: {revision_id}
Revises: {down_revision}
Create Date: {datetime}
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '{revision_id}'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        '{table_name}',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('metadata', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('idx_{table}_name', '{table_name}', ['name'])
    op.create_index('idx_{table}_status', '{table_name}', ['status'])


def downgrade() -> None:
    op.drop_index('idx_{table}_status', '{table_name}')
    op.drop_index('idx_{table}_name', '{table_name}')
    op.drop_table('{table_name}')
