"""add_requires_approval_to_tools

Revision ID: 64122bed0612
Revises: 2bfe5aea0e67
Create Date: 2026-05-29 17:51:28.062041
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '64122bed0612'
down_revision: Union[str, None] = '2bfe5aea0e67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tools', sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('tools', 'requires_approval')
