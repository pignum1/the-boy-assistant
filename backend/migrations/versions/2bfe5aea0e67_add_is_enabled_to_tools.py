"""add_is_enabled_to_tools

Revision ID: 2bfe5aea0e67
Revises: 2c91ee38c06b
Create Date: 2026-05-29 17:49:45.731030
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2bfe5aea0e67'
down_revision: Union[str, None] = '2c91ee38c06b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tools', sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')))


def downgrade() -> None:
    op.drop_column('tools', 'is_enabled')
