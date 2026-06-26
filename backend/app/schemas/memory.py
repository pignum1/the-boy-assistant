import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryLevel(str, Enum):
    system = "system"
    team = "team"
    agent_global = "agent_global"
    context = "context"


class MemoryType(str, Enum):
    decision = "decision"
    standard = "standard"
    context = "context"
    conclusion = "conclusion"
    warning = "warning"


MEMORY_TYPE_COLORS = {
    MemoryType.decision: "blue",
    MemoryType.standard: "green",
    MemoryType.context: "yellow",
    MemoryType.conclusion: "cyan",
    MemoryType.warning: "red",
}


class MemoryCreate(BaseModel):
    level: MemoryLevel
    type: MemoryType = MemoryType.standard
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    team_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    session_id: Optional[str] = None
    created_by: Optional[str] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    type: Optional[MemoryType] = None


class MemoryResponse(BaseModel):
    id: uuid.UUID
    level: str
    type: str
    content: str
    importance: float
    team_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    session_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentMemoryView(BaseModel):
    """四层记忆视图"""
    L1_system: list[MemoryResponse] = []
    L2_team: list[MemoryResponse] = []
    L3_agent_global: list[MemoryResponse] = []
    L4_context: list[MemoryResponse] = []
