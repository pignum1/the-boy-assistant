"""UserTask Schemas：用户任务相关的数据传输对象

包含：
- UserTaskCreate/Update/Response：用户任务 CRUD
- TaskIssueCreate/Update/Response：问题记录
- TaskProgressResponse：任务进度详情
"""

import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


# ==================== UserTask Schemas ====================

class UserTaskCreate(BaseModel):
    """创建用户任务"""
    team_id: Optional[uuid.UUID] = Field(None, description="关联团队ID")
    session_id: Optional[uuid.UUID] = Field(None, description="关联会话ID")
    title: str = Field(..., min_length=1, max_length=255, description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    requirement: str = Field(..., min_length=1, description="用户需求描述")
    priority: str = Field(
        "medium",
        pattern="^(low|medium|high|critical)$",
        description="优先级"
    )


class UserTaskUpdate(BaseModel):
    """更新用户任务"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(
        None,
        pattern="^(planning|generated|running|paused|completed|failed|cancelled)$"
    )
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    current_step: Optional[str] = None
    progress_percentage: Optional[int] = Field(None, ge=0, le=100)


class UserTaskResponse(BaseModel):
    """用户任务响应"""
    id: uuid.UUID
    team_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    requirement: str
    workflow_id: Optional[uuid.UUID] = None
    workflow_instance_id: Optional[uuid.UUID] = None
    status: str
    priority: str
    current_step: Optional[str] = None
    progress_percentage: int = 0
    planned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ai_plan_summary: Optional[dict] = None
    iteration_count: int = 0
    previous_task_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== TaskIssue Schemas ====================

class TaskIssueCreate(BaseModel):
    """创建问题记录"""
    user_task_id: Optional[uuid.UUID] = Field(None, description="关联任务ID（从URL路径获取，此处可为空）")
    workflow_instance_id: Optional[uuid.UUID] = Field(None, description="关联工作流实例ID")
    node_execution_id: Optional[uuid.UUID] = Field(None, description="关联节点执行ID")
    title: str = Field(..., min_length=1, max_length=255, description="问题标题")
    description: Optional[str] = Field(None, description="问题详细描述")
    severity: str = Field(
        "medium",
        pattern="^(low|medium|high|critical)$",
        description="严重程度"
    )
    category: Optional[str] = Field(
        None,
        pattern="^(bug|performance|requirement|ux|security|other)$",
        description="问题分类"
    )
    created_by: Optional[str] = Field(
        "user",
        pattern="^(user|agent|system)$",
        description="创建者类型"
    )


class TaskIssueUpdate(BaseModel):
    """更新问题记录"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    status: Optional[str] = Field(
        None,
        pattern="^(open|in_progress|resolved|ignored)$"
    )
    category: Optional[str] = Field(
        None,
        pattern="^(bug|performance|requirement|ux|security|other)$"
    )
    resolution: Optional[str] = None


class TaskIssueResponse(BaseModel):
    """问题记录响应"""
    id: uuid.UUID
    user_task_id: uuid.UUID
    workflow_instance_id: Optional[uuid.UUID] = None
    node_execution_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    category: Optional[str] = None
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Task Progress Schemas ====================

class StepProgress(BaseModel):
    """步骤进度"""
    node_id: uuid.UUID
    node_label: str
    node_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_summary: Optional[str] = None


class TaskProgressDetailResponse(BaseModel):
    """任务进度详情响应"""
    task_id: uuid.UUID
    task_title: str
    status: str
    progress_percentage: int
    current_step: Optional[dict] = None
    steps: list[StepProgress] = []
    issues_count: int = 0
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskPlanRequest(BaseModel):
    """AI 规划请求"""
    available_agents: list[dict] = Field(
        ...,
        description="可用 Agent 列表，每个包含 id, name, capabilities"
    )
    team_context: Optional[dict] = Field(
        None,
        description="团队上下文信息"
    )
    preferences: Optional[dict] = Field(
        None,
        description="用户偏好配置"
    )


class TaskPlanResponse(BaseModel):
    """AI 规划响应"""
    task_name: str
    task_description: str
    estimated_steps: int
    estimated_duration_minutes: Optional[int] = None
    workflow: dict
    suggestions: list[str] = []
    risks: list[str] = []

    model_config = {"from_attributes": True}


class TaskStartRequest(BaseModel):
    """启动任务请求"""
    user_input: Optional[str] = Field(None, description="用户输入，用于触发工作流")
    initial_state: Optional[dict] = Field(None, description="初始状态")


class TaskIterationRequest(BaseModel):
    """任务迭代请求"""
    feedback: str = Field(..., min_length=1, description="用户反馈")
    issues_to_address: list[uuid.UUID] = Field(
        default_factory=list,
        description="需要解决的问题ID列表"
    )
