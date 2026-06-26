"""三模式协作配置 · 数据模型

每种 Team.collaboration_mode 对应一张配置表，让 schema 清晰、查询简单：

  swarm (群聊式 / AutoGen 风格)
    └── TeamSwarmConfig：max_rounds, speak_strategy, termination_condition

  supervisor (主管式 / CrewAI 风格)
    ├── TeamSupervisorConfig：leader_member_id（团队 Leader）
    └── TeamSupervisorRelation[]：member → supervisor 委派关系（多级）

  langgraph (图编排式 / LangGraph 风格)
    ├── TeamLanggraphConfig：workflow_id（绑 SOP/Workflow）
    └── TeamLanggraphNodeBinding[]：节点 key → agent_id 映射

DDD 边界：这些都属于 Workflow 域（团队协作编排），不混入 Identity / Agent 域。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── 群聊式（Swarm / AutoGen） ──

class TeamSwarmConfig(Base):
    __tablename__ = "team_swarm_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 最大对话轮次（防失控）
    max_rounds: Mapped[int] = mapped_column(Integer, default=10)

    # 发言策略：round_robin(轮询) | priority(按优先级) | auto(LLM 选下一个发言者)
    speak_strategy: Mapped[str] = mapped_column(String(20), default="auto")

    # 终止条件描述（LLM 用来判断是否达成结论）
    termination_condition: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        default="所有参与者达成共识，或得出最终答案"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ── 主管式（Supervisor / CrewAI） ──

class TeamSupervisorConfig(Base):
    __tablename__ = "team_supervisor_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 团队顶层 Leader（通常是 PM / 老板），所有任务从这里开始下分
    leader_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TeamSupervisorRelation(Base):
    """委派关系：member 的直属上级是 supervisor_member.

    示例：架构师.supervisor = PM；前端.supervisor = 架构师
    """
    __tablename__ = "team_supervisor_relations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False
    )
    supervisor_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("team_id", "member_id", name="uq_team_member_supervisor"),
    )


# ── 图编排式（LangGraph） ──

class TeamLanggraphConfig(Base):
    __tablename__ = "team_langgraph_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 绑定的 Workflow / SOP（图结构定义）
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TeamLanggraphNodeBinding(Base):
    """图节点 → Agent 的绑定。

    workflow 定义节点（key），具体由哪个 Agent 执行在这里绑定。
    """
    __tablename__ = "team_langgraph_node_bindings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_langgraph_configs.id", ondelete="CASCADE"), nullable=False
    )
    node_key: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("config_id", "node_key", name="uq_config_node"),
    )
