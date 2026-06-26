"""add_team_members_and_allowed_tools

Revision ID: c6621bc9c943
Revises: 025e0404b09e
Create Date: 2026-05-27 15:20:30.611685
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c6621bc9c943'
down_revision: Union[str, None] = '025e0404b09e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add allowed_tools to teams
    op.add_column('teams', sa.Column('allowed_tools', postgresql.ARRAY(sa.String()), nullable=True))

    # Create team_members table
    op.create_table(
        'team_members',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('agent_id', sa.UUID(), nullable=False),
        sa.Column('role_slot', sa.String(50), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'role_slot', name='uq_team_role_slot'),
    )


def downgrade() -> None:
    op.drop_table('team_members')
    op.drop_column('teams', 'allowed_tools')
