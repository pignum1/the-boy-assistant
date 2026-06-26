import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Skill Install ──

class SkillInstallRequest(BaseModel):
    method: str = "git"  # "git" | "upload"
    git_url: Optional[str] = None
    name: Optional[str] = None  # optional override name
    branch: Optional[str] = None


class SkillInstallResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version: str
    path: str
    source: str
    git_url: Optional[str] = None


# ── Skill CRUD ──

class SkillCreate(BaseModel):
    name: str
    description: Optional[str] = None
    version: str = "1.0"


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version: str
    path: str
    source: str
    git_url: Optional[str] = None
    skill_md: Optional[str] = None  # read from filesystem on demand
    config_yaml: Optional[str] = None  # read from filesystem on demand
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version: str
    path: str
    source: str
    git_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
