import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    sop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sops.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/paused/completed/failed
    input: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # TaskState
    artifacts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
