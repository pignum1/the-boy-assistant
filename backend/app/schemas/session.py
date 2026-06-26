"""Session DTO：请求/响应 schemas"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class SessionCreate(BaseModel):
    """创建会话请求"""
    team_id: uuid.UUID
    title: str = "新对话"
    workspace_path: Optional[str] = None
    mode: str = "discussion"  # discussion | sop

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("discussion", "sop"):
            raise ValueError("mode 必须为 discussion 或 sop")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("标题不能超过 200 个字符")
        return v


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    workspace_path: Optional[str] = None
    status: Optional[str] = None  # active | archived

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "archived"):
            raise ValueError("status 必须为 active 或 archived")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 200:
            raise ValueError("标题不能超过 200 个字符")
        return v


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    team_id: str
    title: str
    status: str
    mode: str
    workspace_path: Optional[str] = None
    message_count: int
    created_at: str
    updated_at: str
    team_name: Optional[str] = None  # 联表查询团队名称


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: list[SessionResponse]
    total: int


class WorkspaceInfo(BaseModel):
    """工作空间信息"""
    session_id: str
    path: str
    status: str  # active | archived | deleted
    created_at: str
    last_accessed: str
    file_count: int = 0
    total_size_bytes: int = 0


class WorkspaceUpdate(BaseModel):
    """更新工作空间路径"""
    path: str


class SessionMessage(BaseModel):
    """会话消息"""
    id: str
    role: str  # user | assistant | system
    content: str
    agent_name: Optional[str] = None
    timestamp: str
