"""add_metadata_to_memories

Revision ID: 7108b608f5e3
Revises: ce9cf9e810ec
Create Date: 2026-06-02 14:13:40.492253
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7108b608f5e3'
down_revision: Union[str, None] = 'ce9cf9e810ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('memories', sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('memories', 'metadata')
