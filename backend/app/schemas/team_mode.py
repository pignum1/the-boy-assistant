"""Team 协作模式配置 · Pydantic schemas"""

import uuid
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Mode 切换 ──

class TeamModeUpdate(BaseModel):
    mode: Literal["swarm", "supervisor", "langgraph"]


# ── Swarm ──

class SwarmConfigUpsert(BaseModel):
    max_rounds: int = Field(default=10, ge=1, le=50)
    speak_strategy: Literal["auto", "round_robin", "priority"] = "auto"
    termination_condition: Optional[str] = None


class SwarmConfigResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    max_rounds: int
    speak_strategy: str
    termination_condition: Optional[str]


# ── Supervisor ──

class SupervisorLeaderUpdate(BaseModel):
    leader_member_id: Optional[uuid.UUID] = None


class SupervisorRelation(BaseModel):
    member_id: uuid.UUID
    supervisor_member_id: uuid.UUID


class SupervisorRelationsBulkUpdate(BaseModel):
    relations: list[SupervisorRelation]


class SupervisorConfigResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    leader_member_id: Optional[uuid.UUID]
    relations: list[dict]  # [{member_id, supervisor_member_id}]


# ── LangGraph ──

class LanggraphWorkflowUpdate(BaseModel):
    workflow_id: Optional[uuid.UUID] = None


class LanggraphNodeBinding(BaseModel):
    node_key: str
    agent_id: uuid.UUID


class LanggraphBindingsBulkUpdate(BaseModel):
    bindings: list[LanggraphNodeBinding]


class LanggraphConfigResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    workflow_id: Optional[uuid.UUID]
    bindings: list[dict]  # [{node_key, agent_id}]
