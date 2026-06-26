"""Session 持久化模型：Team 的一次工作实例

Session = Team 的临时分身，用于完成具体任务。
一个 Team 可以同时有多个活跃 Session。

Session 内部包含:
- Task List (共享任务列表)
- Chat Messages (对话历史)
- Workspace (文件工作区)
- Mailbox (Agent 间通信，通过 WebSocket 事件)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, ForeignKey, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )

    # ── 基本信息 ──
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        # 这次会话要达成什么目标，例如 "开发用户认证模块"

    # ── 状态 ──
    status: Mapped[str] = mapped_column(String(20), default="active")
        # active | paused | completed | archived
    mode: Mapped[str] = mapped_column(String(20), default="discussion")
        # discussion | sop

    # ── 协作模式（可覆盖 Team 默认） ──
    collaboration_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
        # null 时继承 Team 的 collaboration_mode
        # supervisor | swarm | round_robin | custom_sop

    # ── 工作空间 ──
    workspace_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # null 时使用默认路径

    # ── 统计 ──
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    task_total: Mapped[int] = mapped_column(Integer, default=0)
    task_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
        # 0.0 - 100.0，自动从 task_completed / task_total 计算

    # ── 时间戳 ──
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
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

    __table_args__ = (
        Index("ix_sessions_team_id", "team_id"),
        Index("ix_sessions_status", "status"),
        Index("ix_sessions_team_status", "team_id", "status"),
    )
