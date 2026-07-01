import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # 单 Agent 执行模式：single_pass | plan_execute | react | chain_of_thought | rewoo | reflexion | self_consistency
    # 决定该 Agent 在直接聊天与管道中如何推理；一处配置、处处生效。
    execution_mode: Mapped[str] = mapped_column(String(20), default="single_pass")
    # 执行模式专属参数（JSONB），按模式不同存不同字段：
    #   plan_execute: {enable_review, min_score}  react: {max_iterations, enable_self_review}
    #   reflexion: {max_reflections}  self_consistency: {sample_count}
    #   single_pass / chain_of_thought / rewoo → null
    execution_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0)  # 被选为 Reviewer 的次数（Harness 公平选择）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
