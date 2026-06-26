"""Workflows API：工作流 CRUD + 节点/边管理"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.workflow_service import WorkflowService
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowNodeCreate,
    WorkflowNodeUpdate,
    WorkflowNodeResponse,
    WorkflowEdgeCreate,
    WorkflowEdgeUpdate,
    WorkflowEdgeResponse,
    WorkflowDetailResponse,
)

router = APIRouter()


# ── Workflow CRUD ───────────────────────────────────────────

@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    req: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建工作流"""
    svc = WorkflowService(db)
    try:
        workflow = await svc.create_workflow(
            name=req.name,
            description=req.description,
            template_type=req.template_type,
            definition=req.definition,
        )
        return WorkflowResponse.model_validate(workflow)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_workflows(
    template_type: Optional[str] = Query(None, description="按模板类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """列出工作流（分页）"""
    svc = WorkflowService(db)
    workflows, total = await svc.list_workflows(
        template_type=template_type, status=status, skip=skip, limit=limit,
    )
    return {
        "items": [WorkflowResponse.model_validate(w) for w in workflows],
        "total": total,
    }


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取工作流详情（包含节点和边）"""
    svc = WorkflowService(db)
    workflow = await svc.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    nodes = await svc.get_nodes(workflow_id)
    edges = await svc.get_edges(workflow_id)

    return WorkflowDetailResponse(
        **WorkflowResponse.model_validate(workflow).model_dump(),
        nodes=[WorkflowNodeResponse.model_validate(n) for n in nodes],
        edges=[WorkflowEdgeResponse.model_validate(e) for e in edges],
    )


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    req: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新工作流"""
    svc = WorkflowService(db)
    workflow = await svc.update_workflow(
        workflow_id, **req.model_dump(exclude_unset=True)
    )
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除工作流"""
    svc = WorkflowService(db)
    deleted = await svc.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/{workflow_id}/validate")
async def validate_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """验证工作流完整性"""
    svc = WorkflowService(db)
    result = await svc.validate_workflow(workflow_id)
    return result


# ── Template Management ───────────────────────────────────────

@router.get("/templates/list", response_model=list[dict])
async def list_templates(db: AsyncSession = Depends(get_db)):
    """列出所有预设模板"""
    svc = WorkflowService(db)
    return await svc.list_templates()


@router.post("/templates/{template_type}/create", response_model=WorkflowResponse)
async def create_from_template(
    template_type: str,
    name: str = Query(..., description="工作流名称"),
    description: Optional[str] = Query(None, description="工作流描述"),
    db: AsyncSession = Depends(get_db),
):
    """从预设模板创建工作流"""
    svc = WorkflowService(db)
    try:
        workflow = await svc.create_from_template(
            template_type=template_type,
            name=name,
            description=description,
        )
        return WorkflowResponse.model_validate(workflow)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Node Management ──────────────────────────────────────────

@router.post("/{workflow_id}/nodes", response_model=WorkflowNodeResponse)
async def add_node(
    workflow_id: uuid.UUID,
    req: WorkflowNodeCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加节点"""
    svc = WorkflowService(db)
    # 确保 workflow_id 一致
    req.workflow_id = workflow_id
    node = await svc.add_node(req)
    return WorkflowNodeResponse.model_validate(node)


@router.put("/nodes/{node_id}", response_model=WorkflowNodeResponse)
async def update_node(
    node_id: uuid.UUID,
    req: WorkflowNodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新节点"""
    svc = WorkflowService(db)
    node = await svc.update_node(node_id, req)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return WorkflowNodeResponse.model_validate(node)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除节点"""
    svc = WorkflowService(db)
    deleted = await svc.delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")


# ── Edge Management ──────────────────────────────────────────

@router.post("/{workflow_id}/edges", response_model=WorkflowEdgeResponse)
async def add_edge(
    workflow_id: uuid.UUID,
    req: WorkflowEdgeCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加边"""
    svc = WorkflowService(db)
    # 确保 workflow_id 一致
    req.workflow_id = workflow_id
    edge = await svc.add_edge(req)
    return WorkflowEdgeResponse.model_validate(edge)


@router.put("/{workflow_id}/edges/{edge_id}", response_model=WorkflowEdgeResponse)
async def update_edge(
    workflow_id: uuid.UUID,
    edge_id: uuid.UUID,
    req: WorkflowEdgeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新边（类型、条件等）"""
    svc = WorkflowService(db)
    edge = await svc.update_edge(edge_id, type=req.type, condition=req.condition)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    return WorkflowEdgeResponse.model_validate(edge)


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除边"""
    svc = WorkflowService(db)
    deleted = await svc.delete_edge(edge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")
