import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    default_model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id", ondelete="RESTRICT"), index=True)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="RESTRICT"), index=True)
    tools: Mapped[Optional[list[uuid.UUID]]] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="idle")  # idle/busy/error
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0)  # 被选为 Reviewer 的次数（Harness 公平选择）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
