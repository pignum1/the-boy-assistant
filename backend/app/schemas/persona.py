import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PersonaCreate(BaseModel):
    name: str
    # 结构化字段
    role: Optional[str] = None
    expertise: Optional[str] = None
    constraints: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    tags: Optional[list[str]] = None
    # 可使用的技能与 MCP 服务器
    skill_ids: Optional[list[str]] = None
    mcp_server_ids: Optional[list[str]] = None
    # 输出
    output_format: Optional[str] = None
    output_prefs: Optional[dict] = None


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    expertise: Optional[str] = None
    constraints: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    tags: Optional[list[str]] = None
    skill_ids: Optional[list[str]] = None
    mcp_server_ids: Optional[list[str]] = None
    output_format: Optional[str] = None
    output_prefs: Optional[dict] = None


class PersonaResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: Optional[str] = None
    expertise: Optional[str] = None
    constraints: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    tags: Optional[list[str]] = None
    skill_ids: Optional[list[str]] = None
    mcp_server_ids: Optional[list[str]] = None
    output_format: Optional[str] = None
    output_prefs: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
