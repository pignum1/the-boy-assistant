import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    persona_id: uuid.UUID
    model_id: uuid.UUID
    tool_ids: Optional[list[uuid.UUID]] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    persona_id: Optional[uuid.UUID] = None
    model_id: Optional[uuid.UUID] = None
    tool_ids: Optional[list[uuid.UUID]] = None
    status: Optional[str] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    default_model_id: uuid.UUID
    persona_id: uuid.UUID
    tools: Optional[list[str]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: Optional[str] = None
    team_id: Optional[str] = None
    mock: bool = False
