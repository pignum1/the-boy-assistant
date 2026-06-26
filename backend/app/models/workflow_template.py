"""WorkflowTemplate 数据模型：预设工作流模板

核心概念：
- 预设模板：系统内置的工作流模板，用户可以基于模板快速创建工作流
- 5 种预设模板：free_discussion, supervisor_dispatch, sequential, product_dev, hotfix

设计原则：
1. 模板与工作流分离，模板是可复用的定义
2. 模板版本化，支持升级
3. 模板可以包含默认配置（如默认的 Agent、超时时间等）
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkflowTemplate(Base):
    """工作流模板：预设的工作流定义

    模板类型：
    - free_discussion: 自由讨论模式，所有成员并行参与
    - supervisor_dispatch: 主管调度模式，主管分配任务并审核
    - sequential: 顺序执行模式，按步骤依次执行
    - product_dev: 产品开发模式，多角色并行协作
    - hotfix: 紧急修复模式，快速路由和执行
    """
    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 模板类型（唯一标识）
    template_type: Mapped[str] = mapped_column(String(50), unique=True)

    # 模板名称
    name: Mapped[str] = mapped_column(String(100))

    # 模板描述
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 模板定义（包含 nodes 和 edges）
    definition: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 默认配置（可选，用于模板特定的配置）
    # 例如：{default_timeout: 300, default_retry: 3}
    default_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 版本号
    version: Mapped[str] = mapped_column(String(20), default="1.0")

    # 是否为系统模板（系统模板不能删除）
    is_system: Mapped[bool] = mapped_column(default=False)

    # 状态：active（可用）、deprecated（已弃用）
    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 索引：按 template_type 查询
    __table_args__ = (
        Index("idx_workflow_templates_template_type", "template_type"),
    )
