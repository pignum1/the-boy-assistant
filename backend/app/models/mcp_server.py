import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MCPServer(Base):
    """MCP 服务器注册：连接配置 + 状态"""
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    transport: Mapped[str] = mapped_column(String(20), default="sse")  # sse / stdio / http
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    command: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    args: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    env: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    api_key_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="disconnected")  # disconnected / connected / error
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
