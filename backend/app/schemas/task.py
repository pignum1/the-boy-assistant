"""Task Schemas"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskStartRequest(BaseModel):
    sop_id: uuid.UUID
    team_id: uuid.UUID
    input: dict = {}
    auto_approve_hitl: bool = False
    session_id: Optional[uuid.UUID] = None  # 关联的会话 ID（从讨论模式创建任务时传入）


class TaskResumeRequest(BaseModel):
    action: str  # approve / reject
    comment: str = ""


class TaskResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    sop_id: uuid.UUID
    status: str
    input: Optional[dict] = None
    state: Optional[dict] = None
    artifacts: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
