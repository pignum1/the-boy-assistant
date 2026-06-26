"""remove_capability_tags

Revision ID: 217c2da75ebc
Revises: 9a1b2c3d4e5f
Create Date: 2026-06-01 15:40:58.118706
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '217c2da75ebc'
down_revision: Union[str, None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('capability_tags')
    op.drop_column('personas', 'capabilities')


def downgrade() -> None:
    op.add_column('personas', sa.Column('capabilities', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.create_table('capability_tags',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('key', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('category', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('sort_order', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('capability_tags_pkey')),
    sa.UniqueConstraint('key', name=op.f('capability_tags_key_key')),
    sa.UniqueConstraint('name', name=op.f('capability_tags_name_key'))
    )
