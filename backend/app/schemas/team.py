import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── TeamMember Schemas ──

class TeamMemberAdd(BaseModel):
    """添加成员"""
    agent_id: uuid.UUID
    role_name: str = "成员"              # 自定义角色名
    role_icon: str = "🤖"               # emoji 图标
    capabilities: Optional[list[str]] = None  # ["python", "fastapi"]
    preferred_model: Optional[uuid.UUID] = None
    tools: Optional[list[str]] = None
    is_required: bool = False
    can_delegate: bool = True


class TeamMemberUpdate(BaseModel):
    """更新成员"""
    role_name: Optional[str] = None
    role_icon: Optional[str] = None
    capabilities: Optional[list[str]] = None
    preferred_model: Optional[uuid.UUID] = None
    tools: Optional[list[str]] = None
    is_required: Optional[bool] = None
    can_delegate: Optional[bool] = None


class MemberInfo(BaseModel):
    """成员信息（响应）"""
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str = ""
    role_name: str
    role_icon: str
    capabilities: Optional[list[str]] = None
    preferred_model: Optional[uuid.UUID] = None
    tools: Optional[list[str]] = None
    is_required: bool
    can_delegate: bool
    joined_at: datetime


# ── Team Schemas ──

class TeamCreate(BaseModel):
    """创建团队"""
    name: str
    description: Optional[str] = None
    icon: str = "👥"
    collaboration_mode: str = "supervisor"  # supervisor | swarm | round_robin | custom_sop
    leader_id: Optional[uuid.UUID] = None
    capabilities: Optional[list[str]] = None  # ["web_dev", "api_design"]
    default_tools: Optional[list[str]] = None
    knowledge_sources: Optional[list[str]] = None
    allow_agent_to_agent: bool = True
    require_hitl_for: Optional[list[str]] = None  # ["file_delete", "db_write"]
    max_parallel_agents: int = 3


class TeamUpdate(BaseModel):
    """更新团队"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    collaboration_mode: Optional[str] = None
    leader_id: Optional[uuid.UUID] = None
    capabilities: Optional[list[str]] = None
    default_tools: Optional[list[str]] = None
    knowledge_sources: Optional[list[str]] = None
    allow_agent_to_agent: Optional[bool] = None
    require_hitl_for: Optional[list[str]] = None
    max_parallel_agents: Optional[int] = None
    status: Optional[str] = None


class TeamResponse(BaseModel):
    """团队响应"""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    icon: str
    collaboration_mode: str
    leader_id: Optional[uuid.UUID] = None
    capabilities: Optional[list[str]] = None
    default_tools: Optional[list[str]] = None
    knowledge_sources: Optional[list[str]] = None
    allow_agent_to_agent: bool
    require_hitl_for: Optional[list[str]] = None
    max_parallel_agents: int
    status: str
    members: list[MemberInfo] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
