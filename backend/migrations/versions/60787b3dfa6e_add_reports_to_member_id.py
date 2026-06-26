"""add reports_to_member_id

Revision ID: 60787b3dfa6e
Revises: 922625f75cea
Create Date: 2026-06-09 10:57:25.449546
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '60787b3dfa6e'
down_revision: Union[str, None] = '922625f75cea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'team_members',
        sa.Column('reports_to_member_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_team_members_reports_to',
        'team_members',
        'team_members',
        ['reports_to_member_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_team_members_reports_to', 'team_members', type_='foreignkey')
    op.drop_column('team_members', 'reports_to_member_id')
