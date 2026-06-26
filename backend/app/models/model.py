import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_provider_model"),
        Index("ix_models_provider", "provider"),
        Index("ix_models_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50))  # openai/anthropic/zhipu/google
    model_name: Mapped[str] = mapped_column(String(100))  # gpt-4o/claude-sonnet-4-6/glm-5.1
    display_name: Mapped[str] = mapped_column(String(100))
    capabilities: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=60)
    tpm_limit: Mapped[int] = mapped_column(Integer, default=100000)
    api_key_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
