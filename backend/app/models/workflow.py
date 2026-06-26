"""Workflow 数据模型：统一工作流定义

核心概念：
- Workflow: 工作流定义，包含节点和边
- WorkflowNode: 工作流节点（Agent/Router/Parallel/Condition/HITL/Validation/Start/End）
- WorkflowEdge: 工作流边（Forward/Reject/Escalate/Timeout/Fallback）

设计原则：
1. 取消 Team.mode/Session.mode/SOP 等多重概念，统一为 Workflow
2. 节点和边使用 JSONB 存储配置，保持灵活性
3. 支持可视化编辑（position_x/position_y）
4. 通过 template_type 关联预设模板
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Workflow(Base):
    """工作流定义：描述一个完整的协作流程

    一个 Workflow 包含多个 Node 和 Edge，定义了 Agent 之间的协作方式。
    取代旧的 Team.mode + SOP 概念。
    """
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 模板类型：free_discussion, supervisor_dispatch, sequential, product_dev, hotfix, custom
    template_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 完整定义（包含 nodes 和 edges），用于快速加载完整工作流
    definition: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 版本号，支持工作流版本管理
    version: Mapped[int] = mapped_column(Integer, default=1)

    # 创建者（可选，用于权限控制）
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    # 是否为模板（模板可供其他团队引用）
    is_template: Mapped[bool] = mapped_column(default=False)

    # 状态：draft（草稿）、active（活跃）、archived（归档）
    status: Mapped[str] = mapped_column(String(20), default="draft")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_workflows_status", "status"),
        Index("ix_workflows_template_type", "template_type"),
    )


class WorkflowNode(Base):
    """工作流节点：执行单元

    节点类型：
    - Start: 开始节点，工作流入口
    - End: 结束节点，工作流出口
    - Agent: 执行单个 Agent
    - Router: 路由节点，根据策略选择下一个 Agent
    - Parallel: 并行节点，同时执行多个分支
    - Condition: 条件节点，根据条件判断执行路径
    - HITL: 人工介入节点，等待人工审批/输入
    - Validation: 验证节点，验证前一个节点的输出
    """
    __tablename__ = "workflow_nodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))

    # 节点类型：Agent/Router/Parallel/Condition/HITL/Validation/Start/End
    type: Mapped[str] = mapped_column(String(50))

    # 节点标签（显示名称）
    label: Mapped[str] = mapped_column(String(100))

    # 节点唯一标识（用于前端引用 + Agent 绑定）
    node_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 节点配置（JSONB，不同类型有不同配置）
    # Agent 节点：{agent_id, prompt_template, tools, model_config}
    # Router 节点：{strategy, candidates, fallback_agent_id}
    # Parallel 节点：{branches, merge_strategy, timeout}
    # Condition 节点：{expression, on_true, on_false}
    # HITL 节点：{action_type, timeout, escalation_target}
    # Validation 节点：{validator, criteria, on_fail}
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 可视化编辑器中的位置
    position_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 索引：按 workflow_id 快速查询节点
    __table_args__ = (
        Index("idx_workflow_nodes_workflow_id", "workflow_id"),
    )


class WorkflowEdge(Base):
    """工作流边：连接节点，定义流转规则

    边类型：
    - Forward: 正常流转
    - Reject: 拒绝返回（验证失败等）
    - Escalate: 升级处理（无法处理时升级）
    - Timeout: 超时流转（节点执行超时）
    - Fallback: 降级处理（主流程失败）
    """
    __tablename__ = "workflow_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))

    # 源节点 ID
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_nodes.id", ondelete="CASCADE"))

    # 目标节点 ID
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_nodes.id", ondelete="CASCADE"))

    # 边类型：Forward/Reject/Escalate/Timeout/Fallback
    type: Mapped[str] = mapped_column(String(50))

    # 边条件（可选，用于条件判断）
    # 例如：{"validator": "quality_check", "min_score": 0.8}
    condition: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 索引：按 workflow_id 和 source_id 快速查询边
    __table_args__ = (
        Index("idx_workflow_edges_workflow_id", "workflow_id"),
        Index("idx_workflow_edges_source_id", "source_id"),
    )
