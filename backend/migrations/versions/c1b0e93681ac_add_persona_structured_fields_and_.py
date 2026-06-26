"""add_persona_structured_fields_and_capability_tags

Revision ID: c1b0e93681ac
Revises: c6621bc9c943
Create Date: 2026-05-29 16:50:17.296778
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1b0e93681ac'
down_revision: Union[str, None] = 'c6621bc9c943'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── capability_tags table ──
    op.create_table('capability_tags',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(length=50), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key'),
    sa.UniqueConstraint('name')
    )

    # ── personas: new structured fields ──
    op.add_column('personas', sa.Column('role', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('expertise', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('constraints', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('prompt_template', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('personas', sa.Column('temperature', sa.Float(), nullable=True))
    op.add_column('personas', sa.Column('max_tokens', sa.Integer(), nullable=True))
    op.add_column('personas', sa.Column('top_p', sa.Float(), nullable=True))
    op.alter_column('personas', 'system_prompt',
               existing_type=sa.TEXT(),
               nullable=True)


def downgrade() -> None:
    op.alter_column('personas', 'system_prompt',
               existing_type=sa.TEXT(),
               nullable=False)
    op.drop_column('personas', 'top_p')
    op.drop_column('personas', 'max_tokens')
    op.drop_column('personas', 'temperature')
    op.drop_column('personas', 'tags')
    op.drop_column('personas', 'prompt_template')
    op.drop_column('personas', 'constraints')
    op.drop_column('personas', 'expertise')
    op.drop_column('personas', 'role')
    op.drop_table('capability_tags')
