import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    # ── 结构化角色定义 ──
    role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)            # 角色身份："你是一位资深软件架构师"
    expertise: Mapped[Optional[str]] = mapped_column(Text, nullable=True)       # 核心能力描述
    constraints: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # 行为边界/限制
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # 完整系统提示词（兼容旧数据）
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # 模板：{role} {expertise} {constraints}

    # ── 标签 ──
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True) # 标签：["架构设计", "代码审查"]

    # ── 可使用的技能与 MCP 服务器 ──
    skill_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    mcp_server_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # ── 输出偏好 ──
    output_format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # 输出格式规范：如"先对比方案再给出建议"
    output_prefs: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
