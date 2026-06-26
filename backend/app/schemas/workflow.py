"""Workflow Schemas：工作流相关的数据传输对象

包含：
- WorkflowCreate/Update/Response：工作流 CRUD
- WorkflowNodeCreate/Update/Response：节点操作
- WorkflowEdgeCreate/Response：边操作
- WorkflowInstanceResponse：执行实例
- NodeExecutionResponse：节点执行记录
"""

import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


# ==================== Workflow Schemas ====================

class WorkflowCreate(BaseModel):
    """创建工作流"""
    name: str = Field(..., min_length=1, max_length=255, description="工作流名称")
    description: Optional[str] = Field(None, description="工作流描述")
    template_type: Optional[str] = Field(
        None,
        pattern="^(free_discussion|supervisor_dispatch|sequential|product_dev|hotfix|custom)$",
        description="模板类型"
    )
    definition: Optional[dict] = Field(None, description="完整定义（包含节点和边）")


class WorkflowUpdate(BaseModel):
    """更新工作流"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    template_type: Optional[str] = None
    definition: Optional[dict] = None
    status: Optional[str] = Field(None, pattern="^(draft|active|archived)$")
    version: Optional[int] = None


class WorkflowResponse(BaseModel):
    """工作流响应"""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    template_type: Optional[str] = None
    definition: dict
    version: int
    created_by: Optional[uuid.UUID] = None
    is_template: bool = False
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Workflow Node Schemas ====================

class WorkflowNodeCreate(BaseModel):
    """创建节点"""
    workflow_id: uuid.UUID
    type: str = Field(..., pattern="^(Agent|Router|Parallel|Condition|HITL|Validation|Start|End)$")
    label: str = Field(..., min_length=1, max_length=100)
    config: dict = Field(default_factory=dict)
    position_x: Optional[int] = None
    position_y: Optional[int] = None


class WorkflowNodeUpdate(BaseModel):
    """更新节点"""
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    config: Optional[dict] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None


class WorkflowNodeResponse(BaseModel):
    """节点响应"""
    id: uuid.UUID
    workflow_id: uuid.UUID
    type: str
    label: str
    config: dict
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== Workflow Edge Schemas ====================

class WorkflowEdgeCreate(BaseModel):
    """创建边"""
    workflow_id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str = Field(..., pattern="^(Forward|Reject|Escalate|Timeout|Fallback)$")
    condition: Optional[dict] = None


class WorkflowEdgeUpdate(BaseModel):
    """更新边（可选字段）"""
    type: Optional[str] = Field(None, pattern="^(Forward|Reject|Escalate|Timeout|Fallback)$")
    condition: Optional[dict] = None


class WorkflowEdgeResponse(BaseModel):
    """边响应"""
    id: uuid.UUID
    workflow_id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str
    condition: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== Workflow Instance Schemas ====================

class WorkflowInstanceCreate(BaseModel):
    """创建工作流实例"""
    workflow_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None


class WorkflowInstanceResponse(BaseModel):
    """工作流实例响应"""
    id: uuid.UUID
    workflow_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    status: str
    state: Optional[dict] = None
    current_node_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    hitl_pending: bool = False
    hitl_node_id: Optional[uuid.UUID] = None
    hitl_action_type: Optional[str] = None
    hitl_timeout_at: Optional[datetime] = None
    issues_count: int = 0
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Node Execution Schemas ====================

class NodeExecutionResponse(BaseModel):
    """节点执行记录响应"""
    id: uuid.UUID
    instance_id: uuid.UUID
    node_id: Optional[uuid.UUID] = None
    node_type: str
    node_label: Optional[str] = None
    status: str
    input: Optional[dict] = None
    output: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    agent_id: Optional[uuid.UUID] = None
    agent_name: Optional[str] = None
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== Workflow Template Schemas ====================

class WorkflowTemplateResponse(BaseModel):
    """工作流模板响应"""
    id: uuid.UUID
    template_type: str
    name: str
    description: Optional[str] = None
    definition: dict
    default_config: Optional[dict] = None
    version: str
    is_system: bool = False
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Combined Schemas ====================

class WorkflowDetailResponse(WorkflowResponse):
    """工作流详情（包含节点和边）"""
    nodes: list[WorkflowNodeResponse] = []
    edges: list[WorkflowEdgeResponse] = []


class WorkflowInstanceDetailResponse(WorkflowInstanceResponse):
    """工作流实例详情（包含执行记录）"""
    workflow: Optional[WorkflowResponse] = None
    node_executions: list[NodeExecutionResponse] = []
