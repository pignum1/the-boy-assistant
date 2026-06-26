"""Team Manager：团队 CRUD、成员管理

新 Team 模型: 持久化组织核心
- collaboration_mode: supervisor | swarm | round_robin | custom_sop
- capabilities: 团队能力标签
- allow_agent_to_agent: Agent 间直接通信开关
- require_hitl_for: 需人工确认的操作列表
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.agent import Agent

logger = logging.getLogger(__name__)


class TeamManager:
    """团队管理器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Team CRUD ──

    async def create_team(
        self,
        name: str,
        description: Optional[str] = None,
        icon: str = "👥",
        collaboration_mode: str = "supervisor",
        leader_id: Optional[uuid.UUID] = None,
        capabilities: Optional[list[str]] = None,
        default_tools: Optional[list[str]] = None,
        knowledge_sources: Optional[list[str]] = None,
        allow_agent_to_agent: bool = True,
        require_hitl_for: Optional[list[str]] = None,
        max_parallel_agents: int = 3,
    ) -> Team:
        team = Team(
            name=name,
            description=description,
            icon=icon,
            collaboration_mode=collaboration_mode,
            leader_id=leader_id,
            capabilities=capabilities,
            default_tools=default_tools,
            knowledge_sources=knowledge_sources,
            allow_agent_to_agent=allow_agent_to_agent,
            require_hitl_for=require_hitl_for,
            max_parallel_agents=max_parallel_agents,
            status="active",
        )
        self.db.add(team)
        await self.db.commit()
        await self.db.refresh(team)
        logger.info(f"Team created: {name} (mode={collaboration_mode}, capabilities={capabilities})")
        return team

    async def get_team(self, team_id: uuid.UUID) -> Optional[Team]:
        return await self.db.get(Team, team_id)

    async def list_teams(self, status: Optional[str] = None) -> list[Team]:
        stmt = select(Team)
        if status:
            stmt = stmt.where(Team.status == status)
        stmt = stmt.order_by(Team.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_team(self, team_id: uuid.UUID, **kwargs) -> Optional[Team]:
        team = await self.get_team(team_id)
        if not team:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(team, k):
                setattr(team, k, v)
        await self.db.commit()
        await self.db.refresh(team)
        return team

    async def delete_team(self, team_id: uuid.UUID) -> bool:
        team = await self.get_team(team_id)
        if not team:
            return False
        await self.db.delete(team)
        await self.db.commit()
        logger.info(f"Team deleted: {team.name}")
        return True

    # ── Member Management ──

    async def add_member(
        self,
        team_id: uuid.UUID,
        agent_id: uuid.UUID,
        role_name: str = "成员",
        role_icon: str = "🤖",
        capabilities: Optional[list[str]] = None,
        preferred_model: Optional[uuid.UUID] = None,
        tools: Optional[list[str]] = None,
        is_required: bool = False,
        can_delegate: bool = True,
    ) -> TeamMember:
        # Verify team exists
        team = await self.get_team(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found")

        # Verify agent exists
        agent = await self.db.get(Agent, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Check agent not already in team
        existing_agent = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == agent_id,
            )
        )
        if existing_agent.scalar_one_or_none():
            raise ValueError(f"Agent {agent_id} already in team {team_id}")

        member = TeamMember(
            team_id=team_id,
            agent_id=agent_id,
            role_name=role_name,
            role_icon=role_icon,
            capabilities=capabilities,
            preferred_model=preferred_model,
            tools=tools,
            is_required=is_required,
            can_delegate=can_delegate,
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        logger.info(f"Member added: agent={agent_id} role={role_name} team={team_id}")
        return member

    async def update_member(
        self, team_id: uuid.UUID, agent_id: uuid.UUID, **kwargs
    ) -> Optional[TeamMember]:
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == agent_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(member, k):
                setattr(member, k, v)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def remove_member(self, team_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.agent_id == agent_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        await self.db.delete(member)
        await self.db.commit()
        return True

    async def get_members(self, team_id: uuid.UUID) -> list[TeamMember]:
        result = await self.db.execute(
            select(TeamMember).where(TeamMember.team_id == team_id)
        )
        return list(result.scalars().all())

    async def get_member_info(self, team_id: uuid.UUID) -> list[dict]:
        """Get member info with agent names"""
        members = await self.get_members(team_id)
        info = []
        for m in members:
            agent = await self.db.get(Agent, m.agent_id)
            info.append({
                "id": str(m.id),
                "agent_id": str(m.agent_id),
                "agent_name": agent.name if agent else "unknown",
                "role_name": m.role_name,
                "role_icon": m.role_icon,
                "capabilities": m.capabilities,
                "preferred_model": str(m.preferred_model) if m.preferred_model else None,
                "tools": m.tools,
                "is_required": m.is_required,
                "can_delegate": m.can_delegate,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            })
        return info

    async def get_members_by_capability(
        self, team_id: uuid.UUID, capability: str
    ) -> list[TeamMember]:
        """Find team members with a specific capability"""
        members = await self.get_members(team_id)
        return [
            m for m in members
            if m.capabilities and capability in m.capabilities
        ]

    async def get_agent_for_role(
        self, team_id: uuid.UUID, role_name: str
    ) -> Optional[Agent]:
        """Get the agent assigned to a specific role name"""
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.role_name == role_name,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return None
        return await self.db.get(Agent, member.agent_id)

    async def get_agent_for_slot(
        self, team_id: uuid.UUID, role_slot: str
    ) -> Optional[Agent]:
        """Backward compat: get agent by role (searches role_name)"""
        return await self.get_agent_for_role(team_id, role_slot)

    async def get_required_members(self, team_id: uuid.UUID) -> list[TeamMember]:
        """Get all required members (is_required=True)"""
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.is_required == True,
            )
        )
        return list(result.scalars().all())
