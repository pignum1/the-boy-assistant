"""team mode configs (swarm / supervisor / langgraph)

Revision ID: c0ff33aabbcc
Revises: 60787b3dfa6e
Create Date: 2026-06-09 11:30:00

PR-A · 三模式协作框架：
1. 回滚 team_members.reports_to_member_id（之前的方案撤销）
2. 新建 5 张配置表，每种 mode 一组：
   - team_swarm_configs
   - team_supervisor_configs + team_supervisor_relations
   - team_langgraph_configs + team_langgraph_node_bindings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0ff33aabbcc"
down_revision: Union[str, None] = "60787b3dfa6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. 回滚 reports_to_member_id（撤回之前的方案） ──
    op.drop_constraint("fk_team_members_reports_to", "team_members", type_="foreignkey")
    op.drop_column("team_members", "reports_to_member_id")

    # ── 2. Swarm 配置 ──
    op.create_table(
        "team_swarm_configs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("max_rounds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("speak_strategy", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("termination_condition", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── 3. Supervisor 配置 + 关系 ──
    op.create_table(
        "team_supervisor_configs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("leader_member_id", sa.Uuid(), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "team_supervisor_relations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.Uuid(), sa.ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supervisor_member_id", sa.Uuid(), sa.ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("team_id", "member_id", name="uq_team_member_supervisor"),
    )

    # ── 4. LangGraph 配置 + 节点绑定 ──
    op.create_table(
        "team_langgraph_configs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("workflow_id", sa.Uuid(), sa.ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "team_langgraph_node_bindings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("config_id", sa.Uuid(), sa.ForeignKey("team_langgraph_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(length=100), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("config_id", "node_key", name="uq_config_node"),
    )


def downgrade() -> None:
    op.drop_table("team_langgraph_node_bindings")
    op.drop_table("team_langgraph_configs")
    op.drop_table("team_supervisor_relations")
    op.drop_table("team_supervisor_configs")
    op.drop_table("team_swarm_configs")

    # 还原 reports_to_member_id
    op.add_column(
        "team_members",
        sa.Column("reports_to_member_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_team_members_reports_to",
        "team_members",
        "team_members",
        ["reports_to_member_id"],
        ["id"],
        ondelete="SET NULL",
    )
