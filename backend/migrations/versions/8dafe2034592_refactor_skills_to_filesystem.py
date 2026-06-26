"""refactor_skills_to_filesystem

Revision ID: 8dafe2034592
Revises: 64122bed0612
Create Date: 2026-06-01 14:08:51.653481
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8dafe2034592'
down_revision: Union[str, None] = '64122bed0612'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('skills', sa.Column('path', sa.String(length=500), nullable=False, server_default=''))
    op.add_column('skills', sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
    op.add_column('skills', sa.Column('git_url', sa.String(length=1000), nullable=True))
    op.drop_column('skills', 'directory_path')
    op.drop_column('skills', 'skill_md')
    op.drop_column('skills', 'config_yaml')


def downgrade() -> None:
    op.add_column('skills', sa.Column('config_yaml', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('skills', sa.Column('skill_md', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('skills', sa.Column('directory_path', sa.VARCHAR(length=500), autoincrement=False, nullable=False, server_default=''))
    op.drop_column('skills', 'git_url')
    op.drop_column('skills', 'source')
    op.drop_column('skills', 'path')
