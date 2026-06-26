import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Tool ──

class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = None
    param_schema: Optional[dict] = None
    server_id: uuid.UUID
    is_stateful: bool = False
    is_enabled: bool = True
    requires_approval: bool = False
    config: Optional[dict] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    param_schema: Optional[dict] = None
    is_stateful: Optional[bool] = None
    is_enabled: Optional[bool] = None
    requires_approval: Optional[bool] = None
    config: Optional[dict] = None


class ToolResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    param_schema: Optional[dict] = None
    server_id: uuid.UUID
    is_stateful: bool
    is_enabled: bool = True
    requires_approval: bool = False
    config: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── MCPServer ──

class MCPServerCreate(BaseModel):
    name: str
    transport: str = "sse"  # sse / stdio / http
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict] = None
    api_key_ref: Optional[str] = None


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    transport: Optional[str] = None
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict] = None
    api_key_ref: Optional[str] = None


class MCPServerResponse(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    env: Optional[dict] = None
    api_key_ref: Optional[str] = None
    status: str
    config: Optional[dict] = None
    tool_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoverResult(BaseModel):
    added: int = 0
    removed: int = 0
    unchanged: int = 0
    tools: list[str] = []


class TestConnectionResult(BaseModel):
    success: bool
    message: str
