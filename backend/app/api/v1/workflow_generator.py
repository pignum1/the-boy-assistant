"""Workflow Generator API：基于 LLM 的工作流生成接口

DDD 设计：通过 Application Service 协调跨领域操作
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.services.workflow_generator import WorkflowGenerator, DatabaseWorkflowRepository
from app.services.workflow_service import WorkflowService
from app.schemas.workflow import WorkflowResponse, WorkflowDetailResponse

router = APIRouter()


async def _get_team_agents(db: AsyncSession, team_id: uuid.UUID) -> list[dict]:
    """获取团队的 Agent 列表

    这是跨领域操作，在 API 层协调。
    Workflow 领域不直接依赖 Team/Agent 模型。
    """
    # 通过原生 SQL 查询避免导入其他领域模型
    result = await db.execute("""
        SELECT a.id, a.name, tm.role_name
        FROM agents a
        JOIN team_members tm ON a.id = tm.agent_id
        WHERE tm.team_id = :team_id
    """, {"team_id": str(team_id)})

    return [
        {"id": str(row[0]), "name": row[1], "role": row[2]}
        for row in result
    ]


@router.post("/generate", response_model=dict)
async def generate_workflow(
    requirement: str = Query(..., description="用户需求描述"),
    team_id: uuid.UUID = Query(..., description="团队 ID"),
    name: Optional[str] = Query(None, description="工作流名称"),
    db: AsyncSession = Depends(get_db),
):
    """根据需求生成工作流（LLM 驱动）

    遵循 DDD 原则：
    - 在 API 层协调跨领域操作
    - Workflow 领域只处理工作流定义
    - 其他领域数据通过参数传入
    """
    # 获取团队的 Agent（跨领域操作）
    agents = await _get_team_agents(db, team_id)

    if not agents:
        raise HTTPException(status_code=400, detail=f"Team {team_id} has no members")

    # 创建生成器和仓储（依赖注入）
    repository = DatabaseWorkflowRepository(db)
    generator = WorkflowGenerator(repository=repository)

    try:
        result = await generator.generate(
            requirement=requirement,
            available_agents=agents,
            name=name,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate workflow: {str(e)}")


@router.post("/generate-and-save", response_model=WorkflowDetailResponse)
async def generate_and_save_workflow(
    requirement: str = Query(..., description="用户需求描述"),
    team_id: uuid.UUID = Query(..., description="团队 ID"),
    name: Optional[str] = Query(None, description="工作流名称"),
    description: Optional[str] = Query(None, description="工作流描述"),
    created_by: Optional[uuid.UUID] = Query(None, description="创建者 ID"),
    db: AsyncSession = Depends(get_db),
):
    """生成并保存工作流"""
    # 获取团队的 Agent
    agents = await _get_team_agents(db, team_id)

    if not agents:
        raise HTTPException(status_code=400, detail=f"Team {team_id} has no members")

    # 创建生成器和仓储
    repository = DatabaseWorkflowRepository(db)
    generator = WorkflowGenerator(repository=repository)

    try:
        # 生成工作流
        workflow_def = await generator.generate(
            requirement=requirement,
            available_agents=agents,
            name=name,
        )

        # 保存到数据库
        workflow = await generator.save_workflow(
            workflow_def=workflow_def,
            repository=repository,
            name=workflow_def.get("name", name or "Generated Workflow"),
            description=description or workflow_def.get("description"),
            created_by=str(created_by) if created_by else None,
        )

        # 获取完整的工作流详情
        svc = WorkflowService(db)
        nodes = await svc.get_nodes(workflow.id)
        edges = await svc.get_edges(workflow.id)

        from app.schemas.workflow import WorkflowNodeResponse, WorkflowEdgeResponse

        return WorkflowDetailResponse(
            **WorkflowResponse.model_validate(workflow).model_dump(),
            nodes=[WorkflowNodeResponse.model_validate(n) for n in nodes],
            edges=[WorkflowEdgeResponse.model_validate(e) for e in edges],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate and save workflow: {str(e)}")


@router.get("/examples", response_model=list[dict])
async def list_workflow_examples():
    """列出所有工作流案例

    返回可供 LLM 参考的工作流案例库。
    """
    from app.services.workflow_examples import WORKFLOW_EXAMPLES
    return [
        {
            "id": ex["id"],
            "name": ex["name"],
            "scenario": ex["scenario"],
            "requirement_analysis": ex["requirement_analysis"],
            "expected_outcome": ex["expected_outcome"],
        }
        for ex in WORKFLOW_EXAMPLES
    ]


@router.get("/node-types", response_model=dict)
async def list_node_types():
    """列出所有节点类型

    返回可用的节点类型及其配置说明。
    """
    from app.services.workflow_examples import NODE_TYPE_REFERENCE
    return NODE_TYPE_REFERENCE


@router.get("/edge-types", response_model=dict)
async def list_edge_types():
    """列出所有边类型

    返回可用的边类型及其说明。
    """
    from app.services.workflow_examples import EDGE_TYPE_REFERENCE
    return EDGE_TYPE_REFERENCE


# 保留原有的查询端点，从文件顶部移除重复导入
