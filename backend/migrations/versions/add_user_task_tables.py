"""add_user_task_tables

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-02 20:00:00.000000

添加 AI 任务协作系统相关表：
- user_tasks: 用户任务
- task_issues: 任务问题记录

扩展 workflow_instances 表：
- issues_count: 问题数量统计
- last_activity_at: 最后活跃时间
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === user_tasks 表 ===
    op.create_table(
        'user_tasks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('team_id', sa.Uuid(), nullable=True),
        sa.Column('session_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('workflow_id', sa.Uuid(), nullable=True),
        sa.Column('workflow_instance_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='planning'),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('current_step', sa.String(length=255), nullable=True),
        sa.Column('progress_percentage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('planned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ai_plan_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('iteration_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('previous_task_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
        sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id'], ),
    )
    op.create_index('idx_user_tasks_team_id', 'user_tasks', ['team_id'], unique=False)
    op.create_index('idx_user_tasks_session_id', 'user_tasks', ['session_id'], unique=False)
    op.create_index('idx_user_tasks_status', 'user_tasks', ['status'], unique=False)
    op.create_index('idx_user_tasks_workflow_id', 'user_tasks', ['workflow_id'], unique=False)
    op.create_index('idx_user_tasks_instance_id', 'user_tasks', ['workflow_instance_id'], unique=False)

    # === task_issues 表 ===
    op.create_table(
        'task_issues',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_task_id', sa.Uuid(), nullable=False),
        sa.Column('workflow_instance_id', sa.Uuid(), nullable=True),
        sa.Column('node_execution_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='open'),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_task_id'], ['user_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workflow_instance_id'], ['workflow_instances.id'], ),
    )
    op.create_index('idx_task_issues_user_task_id', 'task_issues', ['user_task_id'], unique=False)
    op.create_index('idx_task_issues_instance_id', 'task_issues', ['workflow_instance_id'], unique=False)
    op.create_index('idx_task_issues_status', 'task_issues', ['status'], unique=False)
    op.create_index('idx_task_issues_severity', 'task_issues', ['severity'], unique=False)

    # === 扩展 workflow_instances 表 ===
    op.add_column(
        'workflow_instances',
        sa.Column('issues_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'workflow_instances',
        sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    # 删除添加的列
    op.drop_column('workflow_instances', 'last_activity_at')
    op.drop_column('workflow_instances', 'issues_count')

    # 删除表
    op.drop_index('idx_task_issues_severity', table_name='task_issues')
    op.drop_index('idx_task_issues_status', table_name='task_issues')
    op.drop_index('idx_task_issues_instance_id', table_name='task_issues')
    op.drop_index('idx_task_issues_user_task_id', table_name='task_issues')
    op.drop_table('task_issues')

    op.drop_index('idx_user_tasks_instance_id', table_name='user_tasks')
    op.drop_index('idx_user_tasks_workflow_id', table_name='user_tasks')
    op.drop_index('idx_user_tasks_status', table_name='user_tasks')
    op.drop_index('idx_user_tasks_session_id', table_name='user_tasks')
    op.drop_index('idx_user_tasks_team_id', table_name='user_tasks')
    op.drop_table('user_tasks')
