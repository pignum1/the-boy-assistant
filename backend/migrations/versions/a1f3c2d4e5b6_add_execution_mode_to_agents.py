"""add execution_mode to agents

Revision ID: a1f3c2d4e5b6
Revises: c0ff33aabbcc
Create Date: 2026-06-29 00:00:00

单 Agent 执行模式归 Agent：
- agents 增加 execution_mode 列（single_pass | plan_execute | react），默认 single_pass
- 按角色名回填存量 Agent（产品经理/架构师→plan_execute；工程师/测试/运维→react）

注意：开发库由 create_all 创建（alembic_version 为空），列与回填由直接 SQL 兜底执行；
本迁移仅作长期记录，供走 alembic 链的环境使用。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f3c2d4e5b6"
down_revision: Union[str, None] = "c0ff33aabbcc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default="single_pass",
        ),
    )
    # 按角色名回填（中文/英文双覆盖）
    op.execute(
        """
        UPDATE agents SET execution_mode='plan_execute'
        WHERE name LIKE '%产品经理%' OR name LIKE '%PM%' OR name LIKE '%架构师%' OR name LIKE '%architect%'
        """
    )
    op.execute(
        """
        UPDATE agents SET execution_mode='react'
        WHERE name LIKE '%后端%' OR name LIKE '%前端%' OR name LIKE '%工程师%' OR name LIKE '%backend%'
           OR name LIKE '%frontend%' OR name LIKE '%测试%' OR name LIKE '%test%' OR name LIKE '%运维%'
           OR name LIKE '%部署%' OR name LIKE '%devops%' OR name LIKE '%swarm%'
        """
    )


def downgrade() -> None:
    op.drop_column("agents", "execution_mode")
