import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ModelResponse(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    model_name: str
    context_window: int
    capabilities: Optional[list[str]] = None
    status: str
    api_key_masked: Optional[str] = None
    agent_count: int = 0
    rpm_limit: int
    tpm_limit: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelCreate(BaseModel):
    provider: str
    model_name: str
    display_name: str
    capabilities: Optional[list[str]] = None
    context_window: int = 128000
    rpm_limit: int = 60
    tpm_limit: int = 100000
    api_key_ref: Optional[str] = None


class ModelUpdate(BaseModel):
    display_name: Optional[str] = None
    capabilities: Optional[list[str]] = None
    context_window: Optional[int] = None
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    api_key_ref: Optional[str] = None
    is_active: Optional[bool] = None
