"""Team 模型：持久化多 Agent 协作团队

Team 是系统的组织核心，定义：
- 谁在团队里（members）
- 怎么协作（collaboration_mode）
- 能做什么（capabilities）
- 通信规则（allow_agent_to_agent）
- 安全边界（require_hitl_for）
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Team(Base):
    __tablename__ = "teams"

    # ── 身份 ──
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(10), default="👥")  # emoji 图标

    # ── 协作模式 ──
    # supervisor | swarm | round_robin | custom_sop
    collaboration_mode: Mapped[str] = mapped_column(String(20), default="supervisor")
    leader_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )

    # ── 能力定义 ──
    capabilities: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # ["web_dev", "api_design", "ui_design", "testing"]
    default_tools: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # 团队默认工具ID列表
    knowledge_sources: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # 关联知识库ID列表

    # ── 运行时配置 ──
    allow_agent_to_agent: Mapped[bool] = mapped_column(default=True)  # Agent 间直接通信
    require_hitl_for: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # ["file_delete", "db_write", "deploy"] 需要人工确认的操作
    max_parallel_agents: Mapped[int] = mapped_column(Integer, default=3)  # 最大并行Agent数

    # ── 状态 ──
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | inactive | archived

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
