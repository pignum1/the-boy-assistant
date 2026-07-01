"""add execution_config to agents

Revision ID: b2c3d4e5f6a7
Revises: a1f3c2d4e5b6
Create Date: 2026-06-29 00:00:00

Agent 执行模式专属参数配置（JSONB）：
- 不同模式不同参数，避免加 10+ 列
- plan_execute: {enable_review, min_score}
- react: {max_iterations, enable_self_review}
- reflexion: {max_reflections}
- self_consistency: {sample_count}
- 其他模式: null
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1f3c2d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "execution_config",
            JSONB,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "execution_config")
