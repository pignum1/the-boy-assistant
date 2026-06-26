"""WorkflowInstance 数据模型：工作流执行实例

核心概念：
- WorkflowInstance: 工作流的一次执行实例
- NodeExecution: 节点的执行记录

设计原则：
1. 工作流定义（Workflow）和执行（WorkflowInstance）分离
2. 每个实例有独立的状态，支持并发执行
3. 完整记录每个节点的执行历史，支持回溯和分析
4. 支持 HITL 暂停/恢复、超时处理、失败重试
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkflowInstance(Base):
    """工作流执行实例：记录一次工作流的执行过程

    状态流转：
    pending → running → paused → running → completed
                  ↘ failed
                  ↘ cancelled
    """
    __tablename__ = "workflow_instances"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))

    # 关联的会话 ID（可选，用于会话级工作流）
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)

    # 状态：pending（待执行）、running（执行中）、paused（暂停）、completed（已完成）、failed（失败）、cancelled（已取消）
    status: Mapped[str] = mapped_column(String(50), default="pending")

    # 运行时状态（JSONB，存储工作流执行过程中的变量、临时数据）
    state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 当前执行的节点 ID
    current_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)

    # 开始时间、完成时间
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 错误信息（执行失败时记录）
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 重试次数
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # HITL 等待信息（当前节点需要人工介入时记录）
    hitl_pending: Mapped[bool] = mapped_column(default=False)
    hitl_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    hitl_action_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hitl_timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 用户任务扩展字段
    # 问题数量统计（用于 UI 展示）
    issues_count: Mapped[int] = mapped_column(Integer, default=0)

    # 最后活跃时间（用于判断"卡住"的任务）
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 索引：按 workflow_id、session_id、status 查询
    __table_args__ = (
        Index("idx_workflow_instances_workflow_id", "workflow_id"),
        Index("idx_workflow_instances_session_id", "session_id"),
        Index("idx_workflow_instances_status", "status"),
    )


class NodeExecution(Base):
    """节点执行记录：记录单个节点的执行过程

    状态：pending（待执行）、running（执行中）、completed（已完成）、failed（失败）、skipped（跳过）
    """
    __tablename__ = "node_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.id", ondelete="CASCADE"))

    # 节点信息（独立存储，遵循 DDD 原则，无外键关联）
    node_id: Mapped[uuid.UUID] = mapped_column(nullable=True)  # 存储节点 ID，非外键
    node_type: Mapped[str] = mapped_column(String(50))  # Agent/Router/Parallel/Condition/HITL/Validation
    node_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 状态：pending/running/completed/failed/skipped
    status: Mapped[str] = mapped_column(String(50), default="pending")

    # 输入输出（JSONB）
    input: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 错误信息
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 执行时间
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 重试次数
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Agent 信息（独立存储，遵循 DDD 原则，无外键关联）
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 模型信息（记录使用的模型，用于分析）
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Token 统计（用于成本分析）
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 索引：按 instance_id 和 status 查询
    __table_args__ = (
        Index("idx_node_executions_instance_id", "instance_id"),
        Index("idx_node_executions_status", "status"),
        Index("idx_node_executions_agent_id", "agent_id"),
    )
