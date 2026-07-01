import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    persona_id: uuid.UUID
    model_id: uuid.UUID
    tool_ids: Optional[list[uuid.UUID]] = None
    # single_pass | plan_execute | react | chain_of_thought | rewoo | reflexion | self_consistency
    execution_mode: Optional[str] = "single_pass"
    # 模式专属参数（JSONB），如 {enable_review, min_score} / {max_iterations, enable_self_review}
    execution_config: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    persona_id: Optional[uuid.UUID] = None
    model_id: Optional[uuid.UUID] = None
    tool_ids: Optional[list[uuid.UUID]] = None
    status: Optional[str] = None
    execution_mode: Optional[str] = None
    execution_config: Optional[dict] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    default_model_id: uuid.UUID
    persona_id: uuid.UUID
    tools: Optional[list[str]] = None
    status: str
    execution_mode: str = "single_pass"
    execution_config: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: Optional[str] = None
    team_id: Optional[str] = None
    mock: bool = False
