"""add_workflow_tables

Revision ID: a1b2c3d4e5f6
Revises: 7108b608f5e3
Create Date: 2026-06-02 18:00:00.000000

添加统一 Workflow 架构相关表：
- workflows: 工作流定义
- workflow_nodes: 工作流节点
- workflow_edges: 工作流边
- workflow_instances: 工作流执行实例
- node_executions: 节点执行记录
- workflow_templates: 预设模板
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7108b608f5e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === workflows 表 ===
    op.create_table(
        'workflows',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template_type', sa.String(length=50), nullable=True),
        sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('is_template', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['agents.id'], ),
    )
    op.create_index('idx_workflows_template_type', 'workflows', ['template_type'], unique=False)
    op.create_index('idx_workflows_status', 'workflows', ['status'], unique=False)

    # === workflow_nodes 表 ===
    op.create_table(
        'workflow_nodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('position_x', sa.Integer(), nullable=True),
        sa.Column('position_y', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_workflow_nodes_workflow_id', 'workflow_nodes', ['workflow_id'], unique=False)

    # === workflow_edges 表 ===
    op.create_table(
        'workflow_edges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('condition', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['workflow_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['workflow_nodes.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_workflow_edges_workflow_id', 'workflow_edges', ['workflow_id'], unique=False)
    op.create_index('idx_workflow_edges_source_id', 'workflow_edges', ['source_id'], unique=False)

    # === workflow_instances 表 ===
    op.create_table(
        'workflow_instances',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=False),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('current_node_id', sa.Uuid(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hitl_pending', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('hitl_node_id', sa.Uuid(), nullable=True),
        sa.Column('hitl_action_type', sa.String(length=50), nullable=True),
        sa.Column('hitl_timeout_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    )
    op.create_index('idx_workflow_instances_workflow_id', 'workflow_instances', ['workflow_id'], unique=False)
    op.create_index('idx_workflow_instances_session_id', 'workflow_instances', ['session_id'], unique=False)
    op.create_index('idx_workflow_instances_status', 'workflow_instances', ['status'], unique=False)

    # === node_executions 表 ===
    op.create_table(
        'node_executions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('instance_id', sa.Uuid(), nullable=False),
        sa.Column('node_id', sa.Uuid(), nullable=True),
        sa.Column('node_type', sa.String(length=50), nullable=False),
        sa.Column('node_label', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('input', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('agent_id', sa.Uuid(), nullable=True),
        sa.Column('agent_name', sa.String(length=100), nullable=True),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['instance_id'], ['workflow_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['node_id'], ['workflow_nodes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ),
    )
    op.create_index('idx_node_executions_instance_id', 'node_executions', ['instance_id'], unique=False)
    op.create_index('idx_node_executions_status', 'node_executions', ['status'], unique=False)
    op.create_index('idx_node_executions_agent_id', 'node_executions', ['agent_id'], unique=False)

    # === workflow_templates 表 ===
    op.create_table(
        'workflow_templates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('template_type', sa.String(length=50), nullable=False, unique=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('default_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='1.0'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_workflow_templates_template_type', 'workflow_templates', ['template_type'], unique=True)


def downgrade() -> None:
    # 删除表（按依赖顺序逆序）
    op.drop_index('idx_workflow_templates_template_type', table_name='workflow_templates')
    op.drop_table('workflow_templates')

    op.drop_index('idx_node_executions_agent_id', table_name='node_executions')
    op.drop_index('idx_node_executions_status', table_name='node_executions')
    op.drop_index('idx_node_executions_instance_id', table_name='node_executions')
    op.drop_table('node_executions')

    op.drop_index('idx_workflow_instances_status', table_name='workflow_instances')
    op.drop_index('idx_workflow_instances_session_id', table_name='workflow_instances')
    op.drop_index('idx_workflow_instances_workflow_id', table_name='workflow_instances')
    op.drop_table('workflow_instances')

    op.drop_index('idx_workflow_edges_source_id', table_name='workflow_edges')
    op.drop_index('idx_workflow_edges_workflow_id', table_name='workflow_edges')
    op.drop_table('workflow_edges')

    op.drop_index('idx_workflow_nodes_workflow_id', table_name='workflow_nodes')
    op.drop_table('workflow_nodes')

    op.drop_index('idx_workflows_status', table_name='workflows')
    op.drop_index('idx_workflows_template_type', table_name='workflows')
    op.drop_table('workflows')
