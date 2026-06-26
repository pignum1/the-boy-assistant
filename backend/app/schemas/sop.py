"""SOP Schemas"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SOPCreate(BaseModel):
    team_id: uuid.UUID
    name: str
    description: Optional[str] = None
    nodes: list[dict]
    edges: list[dict]
    format: str = "yaml"
    version: str = "1.0"
    is_template: bool = False


class SOPUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[list[dict]] = None
    edges: Optional[list[dict]] = None
    format: Optional[str] = None
    version: Optional[str] = None
    is_template: Optional[bool] = None


class SOPResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    name: str
    description: Optional[str] = None
    nodes: Optional[list[dict]] = None
    edges: Optional[list[dict]] = None
    format: str
    version: str
    is_template: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
