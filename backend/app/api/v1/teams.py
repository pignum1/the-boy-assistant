"""Teams API：团队 CRUD + 成员管理 + 协作模式配置

Team 协作模式（PR-A）：
- swarm        群聊式（AutoGen / OpenAI Swarm 风格）
- supervisor   主管式（CrewAI 风格，已实现 M0-M7）
- langgraph    图编排（LangGraph 风格，绑 workflow）
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.team_manager import TeamManager
from app.services.team_mode_service import TeamModeService
from app.schemas.team import TeamCreate, TeamUpdate, TeamMemberAdd, TeamMemberUpdate
from app.schemas.team_mode import (
    TeamModeUpdate,
    SwarmConfigUpsert,
    SupervisorLeaderUpdate,
    SupervisorRelationsBulkUpdate,
    LanggraphWorkflowUpdate,
    LanggraphBindingsBulkUpdate,
)

router = APIRouter()


@router.post("")
async def create_team(
    req: TeamCreate,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    try:
        team = await mgr.create_team(
            name=req.name,
            description=req.description,
            icon=req.icon,
            collaboration_mode=req.collaboration_mode,
            leader_id=req.leader_id,
            capabilities=req.capabilities,
            default_tools=req.default_tools,
            knowledge_sources=req.knowledge_sources,
            allow_agent_to_agent=req.allow_agent_to_agent,
            require_hitl_for=req.require_hitl_for,
            max_parallel_agents=req.max_parallel_agents,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _team_response(team, [])


@router.get("")
async def list_teams(
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    teams = await mgr.list_teams(status=status)
    result = []
    for t in teams:
        members = await mgr.get_member_info(t.id)
        result.append(_team_response(t, members))
    return result


@router.get("/{team_id}")
async def get_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    mgr = TeamManager(db)
    team = await mgr.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = await mgr.get_member_info(team_id)
    return _team_response(team, members)


@router.put("/{team_id}")
async def update_team(
    team_id: uuid.UUID,
    req: TeamUpdate,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    team = await mgr.update_team(team_id, **req.model_dump(exclude_unset=True))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    members = await mgr.get_member_info(team_id)
    return _team_response(team, members)


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    mgr = TeamManager(db)
    deleted = await mgr.delete_team(team_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found")


# ── Member Management ──

@router.post("/{team_id}/members")
async def add_member(
    team_id: uuid.UUID,
    req: TeamMemberAdd,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    try:
        member = await mgr.add_member(
            team_id=team_id,
            agent_id=req.agent_id,
            role_name=req.role_name,
            role_icon=req.role_icon,
            capabilities=req.capabilities,
            preferred_model=req.preferred_model,
            tools=req.tools,
            is_required=req.is_required,
            can_delegate=req.can_delegate,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _member_response(member)


@router.put("/{team_id}/members/{agent_id}")
async def update_member(
    team_id: uuid.UUID,
    agent_id: uuid.UUID,
    req: TeamMemberUpdate,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    member = await mgr.update_member(team_id, agent_id, **req.model_dump(exclude_unset=True))
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return _member_response(member)


@router.delete("/{team_id}/members/{agent_id}", status_code=204)
async def remove_member(
    team_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    mgr = TeamManager(db)
    removed = await mgr.remove_member(team_id, agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")


# ── Response Helpers ──

def _team_response(team, members: list) -> dict:
    return {
        "id": str(team.id),
        "name": team.name,
        "description": team.description,
        "icon": team.icon,
        "collaboration_mode": team.collaboration_mode,
        "leader_id": str(team.leader_id) if team.leader_id else None,
        "capabilities": team.capabilities,
        "default_tools": team.default_tools,
        "knowledge_sources": team.knowledge_sources,
        "allow_agent_to_agent": team.allow_agent_to_agent,
        "require_hitl_for": team.require_hitl_for,
        "max_parallel_agents": team.max_parallel_agents,
        "status": team.status,
        "members": members,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "updated_at": team.updated_at.isoformat() if team.updated_at else None,
    }


def _member_response(member) -> dict:
    return {
        "id": str(member.id),
        "team_id": str(member.team_id),
        "agent_id": str(member.agent_id),
        "agent_name": getattr(member, "agent_name", None),
        "role_name": member.role_name,
        "role_icon": member.role_icon,
        "capabilities": member.capabilities,
        "preferred_model": str(member.preferred_model) if member.preferred_model else None,
        "tools": member.tools,
        "is_required": member.is_required,
        "can_delegate": member.can_delegate,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
    }


# ════════════════════════════════════════════════════════════════
#  协作模式配置（PR-A）
# ════════════════════════════════════════════════════════════════

@router.put("/{team_id}/mode")
async def set_team_mode(
    team_id: uuid.UUID,
    req: TeamModeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """切换团队协作模式。会自动为新模式创建空配置。"""
    svc = TeamModeService(db)
    try:
        team = await svc.set_mode(team_id, req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"team_id": str(team.id), "mode": team.collaboration_mode}


@router.get("/{team_id}/mode-config")
async def get_team_mode_config(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """读取当前团队的 mode + 模式专属配置（按当前 mode 联表查）"""
    team = await db.get(__import__("app.models.team", fromlist=["Team"]).Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    svc = TeamModeService(db)
    mode = team.collaboration_mode
    out: dict = {"team_id": str(team_id), "mode": mode}
    if mode == "swarm":
        cfg = await svc.get_swarm_config(team_id)
        out["swarm"] = {
            "max_rounds": cfg.max_rounds if cfg else 10,
            "speak_strategy": cfg.speak_strategy if cfg else "auto",
            "termination_condition": cfg.termination_condition if cfg else None,
        }
    elif mode == "supervisor":
        cfg = await svc.get_supervisor_config(team_id)
        rels = await svc.get_supervisor_relations(team_id)
        out["supervisor"] = {
            "leader_member_id": str(cfg.leader_member_id) if cfg and cfg.leader_member_id else None,
            "relations": [
                {"member_id": str(r.member_id), "supervisor_member_id": str(r.supervisor_member_id)}
                for r in rels
            ],
        }
    elif mode == "langgraph":
        cfg = await svc.get_langgraph_config(team_id)
        bindings = await svc.get_node_bindings(team_id)
        workflow_name = None
        if cfg and cfg.workflow_id:
            # Fetch workflow name
            from sqlalchemy import select, cast
            from app.models.workflow import Workflow
            stmt = select(Workflow.name).where(Workflow.id == cfg.workflow_id)
            result = await db.execute(stmt)
            workflow_name = result.scalar_one_or_none()

        out["langgraph"] = {
            "workflow_id": str(cfg.workflow_id) if cfg and cfg.workflow_id else None,
            "workflow_name": workflow_name,
            "bindings": [
                {"node_key": b.node_key, "agent_id": str(b.agent_id)}
                for b in bindings
            ],
        }
    return out


# ── Swarm 配置 ──

@router.put("/{team_id}/swarm-config")
async def upsert_swarm_config(
    team_id: uuid.UUID,
    req: SwarmConfigUpsert,
    db: AsyncSession = Depends(get_db),
):
    svc = TeamModeService(db)
    try:
        cfg = await svc.upsert_swarm_config(
            team_id=team_id,
            max_rounds=req.max_rounds,
            speak_strategy=req.speak_strategy,
            termination_condition=req.termination_condition,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(cfg.id), "team_id": str(cfg.team_id),
        "max_rounds": cfg.max_rounds, "speak_strategy": cfg.speak_strategy,
        "termination_condition": cfg.termination_condition,
    }


# ── Supervisor 配置 ──

@router.put("/{team_id}/supervisor-leader")
async def set_supervisor_leader(
    team_id: uuid.UUID,
    req: SupervisorLeaderUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = TeamModeService(db)
    try:
        cfg = await svc.set_leader(team_id, req.leader_member_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(cfg.id), "team_id": str(cfg.team_id),
        "leader_member_id": str(cfg.leader_member_id) if cfg.leader_member_id else None,
    }


@router.put("/{team_id}/supervisor-relations")
async def bulk_set_supervisor_relations(
    team_id: uuid.UUID,
    req: SupervisorRelationsBulkUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = TeamModeService(db)
    try:
        count = await svc.bulk_set_supervisor_relations(
            team_id, [r.model_dump() for r in req.relations]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"team_id": str(team_id), "count": count}


# ── LangGraph 配置 ──

@router.get("/{team_id}/langgraph-workflow")
async def get_langgraph_workflow(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取团队的 LangGraph 工作流（含节点和边，供前端 DAG 渲染）。"""
    svc = TeamModeService(db)
    cfg = await svc.get_langgraph_config(team_id)
    if not cfg or not cfg.workflow_id:
        return {"workflow_id": "", "workflow_name": "", "nodes": [], "edges": []}

    from app.models.workflow import Workflow as WF, WorkflowNode, WorkflowEdge
    wf = await db.get(WF, cfg.workflow_id)
    if not wf:
        return {"workflow_id": "", "workflow_name": "", "nodes": [], "edges": []}

    nodes = (await db.execute(
        __import__('sqlalchemy').select(WorkflowNode).where(
            WorkflowNode.workflow_id == cfg.workflow_id
        )
    )).scalars().all()
    edges = (await db.execute(
        __import__('sqlalchemy').select(WorkflowEdge).where(
            WorkflowEdge.workflow_id == cfg.workflow_id
        )
    )).scalars().all()

    # 获取 agent 绑定
    bindings = await svc.get_node_bindings(team_id)
    node_agents = {b.node_key: str(b.agent_id) for b in bindings}

    # 获取 agent 详情
    from app.models.agent import Agent
    agent_ids = list(set(node_agents.values()))
    agent_map = {}
    if agent_ids:
        agents = (await db.execute(
            __import__('sqlalchemy').select(Agent).where(Agent.id.in_(
                [uuid.UUID(aid) for aid in agent_ids]
            ))
        )).scalars().all()
        agent_map = {str(a.id): a.name for a in agents}

    return {
        "workflow_id": str(cfg.workflow_id),
        "workflow_name": wf.name,
        "nodes": [
            {
                "id": str(n.id),
                "type": n.type,
                "label": n.label,
                "node_key": n.node_key,
                "config": n.config,
                "position_x": n.position_x or 0,
                "position_y": n.position_y or 0,
                "agent_id": node_agents.get(n.node_key, ""),
                "agent_name": agent_map.get(node_agents.get(n.node_key, ""), ""),
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": str(e.id),
                "source_id": str(e.source_id),
                "target_id": str(e.target_id),
                "type": e.type,
                "condition": e.condition,
            }
            for e in edges
        ],
    }


@router.put("/{team_id}/langgraph-workflow")
async def set_langgraph_workflow(
    team_id: uuid.UUID,
    req: LanggraphWorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = TeamModeService(db)
    cfg = await svc.set_workflow(team_id, req.workflow_id)
    return {
        "id": str(cfg.id), "team_id": str(cfg.team_id),
        "workflow_id": str(cfg.workflow_id) if cfg.workflow_id else None,
    }


@router.put("/{team_id}/langgraph-bindings")
async def bulk_set_langgraph_bindings(
    team_id: uuid.UUID,
    req: LanggraphBindingsBulkUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = TeamModeService(db)
    count = await svc.bulk_set_node_bindings(
        team_id, [b.model_dump() for b in req.bindings]
    )
    return {"team_id": str(team_id), "count": count}
