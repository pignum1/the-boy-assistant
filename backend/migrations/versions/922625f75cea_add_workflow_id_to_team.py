"""add_workflow_id_to_team

Revision ID: 922625f75cea
Revises: 156711dd177f
Create Date: 2026-06-07 21:04:11.547917
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '922625f75cea'
down_revision: Union[str, None] = '156711dd177f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('workflow_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('teams_workflow_id_fkey', 'teams', 'workflows', ['workflow_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('teams_workflow_id_fkey', 'teams', type_='foreignkey')
    op.drop_column('teams', 'workflow_id')
