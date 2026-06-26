"""SessionTask 模型：会话内的共享任务列表

对标: CrewAI Task(context=prev_task, expected_output) + Claude Code Shared Task List(--depends-on)

特性:
- 任务状态: pending → claimed → in_progress → done (或 blocked)
- 依赖关系: depends_on 列表形成 DAG
- Agent 自主认领或 Supervisor 指派
- 产出追踪: expected_output / actual_output / artifacts
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessionTask(Base):
    __tablename__ = "session_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # ── 任务信息 ──
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── 状态 ──
    # pending → claimed(agent认领) → in_progress → done
    # 任何状态 → blocked(依赖未满足)
    status: Mapped[str] = mapped_column(String(20), default="pending")
        # pending | claimed | in_progress | done | blocked | cancelled

    # ── 优先级 ──
    priority: Mapped[str] = mapped_column(String(20), default="medium")
        # low | medium | high | critical

    # ── 分配 ──
    assigned_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )  # null 表示等待认领
    assigned_agent_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 依赖 ──
    depends_on: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # 依赖的任务ID列表，全部完成才能开始

    # ── 估算 ──
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── 产出 ──
    expected_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        # 期望产出描述，例如 "完整的 RESTful API 设计文档"
    actual_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        # 实际产出内容
    artifacts: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # 产出文件路径列表

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
