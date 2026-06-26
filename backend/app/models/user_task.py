"""用户任务数据模型：用户发起的待办事项

核心概念：
- UserTask: 用户输入的任务需求，通过 AI 生成 Workflow 并执行
- TaskIssue: 任务执行过程中发现的问题记录

设计原则（DDD）：
1. 任务属于 Workflow 领域的扩展，但通过 ID 引用其他领域
2. 不直接导入 Team/Session/Agent 等其他领域模型
3. 状态管理与 WorkflowInstance 同步
4. 支持问题记录和迭代反馈
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserTask(Base):
    """用户任务：用户发起的待办事项

    状态流转：
    planning（规划中）→ generated（已生成方案）→ running（执行中）
    → paused（暂停）→ running → completed（已完成）
                      ↘ failed（失败）
                      ↘ cancelled（已取消）
    """
    __tablename__ = "user_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 外键引用（可选，允许独立任务）
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("teams.id"), nullable=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )

    # 任务基本信息
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requirement: Mapped[str] = mapped_column(Text)  # 用户原始需求描述

    # 关联的 Workflow（通过 ID 引用，遵循 DDD）
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflows.id"), nullable=True
    )
    workflow_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflow_instances.id"), nullable=True
    )

    # 状态管理
    status: Mapped[str] = mapped_column(
        String(50), default="planning"
    )  # planning/generated/running/paused/completed/failed/cancelled
    priority: Mapped[str] = mapped_column(
        String(20), default="medium"
    )  # low/medium/high/critical

    # 进度追踪
    current_step: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)

    # 时间戳
    planned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # AI 规划信息（存储 AI 生成的方案摘要）
    ai_plan_summary: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # 迭代信息（支持任务迭代优化）
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    previous_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        nullable=True
    )  # 指向前一个迭代版本

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 索引
    __table_args__ = (
        Index("idx_user_tasks_team_id", "team_id"),
        Index("idx_user_tasks_session_id", "session_id"),
        Index("idx_user_tasks_status", "status"),
        Index("idx_user_tasks_workflow_id", "workflow_id"),
        Index("idx_user_tasks_instance_id", "workflow_instance_id"),
    )


class TaskIssue(Base):
    """任务执行过程中的问题记录

    状态：open（待处理）→ in_progress（处理中）
    → resolved（已解决）/ ignored（已忽略）
    """
    __tablename__ = "task_issues"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 关联任务
    user_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_tasks.id", ondelete="CASCADE")
    )
    workflow_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflow_instances.id"), nullable=True
    )
    node_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        nullable=True
    )  # 可选，记录发生问题的节点

    # 问题信息
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), default="medium"
    )  # low/medium/high/critical

    # 状态
    status: Mapped[str] = mapped_column(
        String(50), default="open"
    )  # open/in_progress/resolved/ignored

    # 问题分类
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # bug/performance/requirement/ux/security

    # 解决信息
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 创建者类型
    created_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # user/agent/system

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 索引
    __table_args__ = (
        Index("idx_task_issues_user_task_id", "user_task_id"),
        Index("idx_task_issues_instance_id", "workflow_instance_id"),
        Index("idx_task_issues_status", "status"),
        Index("idx_task_issues_severity", "severity"),
    )
