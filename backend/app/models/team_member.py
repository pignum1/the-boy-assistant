"""TeamMember 模型：团队成员，自定义角色 + 能力标签

对标 CrewAI 的 agent(role, goal, backstory) + MetaGPT 的固定角色体系，
我们采用 agent + 自定义 role_name + 能力标签 的灵活结构化方案。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── 角色定义（对标 CrewAI 的 role + goal） ──
    role_name: Mapped[str] = mapped_column(String(100), default="成员")
        # 自定义角色名，不限于 pm/dev/qa
        # 例如: "安全审计专家", "性能优化顾问", "技术文档写手"
    role_icon: Mapped[str] = mapped_column(String(10), default="🤖")  # emoji 图标

    # ── 能力标签 ──
    capabilities: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # ["python", "fastapi", "postgresql", "security_audit"]

    # ── 配置覆盖 ──
    preferred_model: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )  # 该成员偏好的模型，null 则使用 Agent 默认
    tools: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # 该成员可用工具，覆盖团队默认

    # ── 运行时行为 ──
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
        # 是否必须参与每次任务（如 PM、架构师）
    can_delegate: Mapped[bool] = mapped_column(Boolean, default=True)
        # 是否可以委派任务给其他成员

    # 注意：层级关系不在这里，存于 supervisor_relations 表
    # （只有 supervisor 模式下才有委派关系）

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
