"""add_output_format_to_persona

Revision ID: 221e574d978f
Revises: 217c2da75ebc
Create Date: 2026-06-01 15:55:24.163648
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '221e574d978f'
down_revision: Union[str, None] = '217c2da75ebc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('personas', sa.Column('output_format', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('personas', 'output_format')
