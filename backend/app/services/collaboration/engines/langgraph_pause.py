"""LangGraph HITL 暂停/恢复状态管理

提供：
- _paused 内存缓存（快速路径）
- _persist_paused_state() → workflow_instances.state JSONB 持久化
- _load_paused_state() → 从 DB 恢复（服务重启后）
- has_paused() / cancel_paused() 公共接口
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)

# 暂停执行存储（HITL 节点暂停时保存状态，resume 时恢复）
# key = session_id, value = resume state dict
# 同时持久化到 workflow_instances.state，服务重启不丢失
_paused: dict[str, dict] = {}


async def _persist_paused_state(session_id: str, state: dict) -> None:
    """将暂停状态持久化到 workflow_instances.state JSONB。

    同时保留内存副本 _paused[session_id] 作为缓存层。
    序列化策略：非 JSON 兼容对象（模型实例/set）转为基本类型。
    """
    from app.core.database import async_session
    from app.models.workflow_instance import WorkflowInstance

    # 序列化：WorkflowNode 对象 → dict
    serializable: dict[str, Any] = {}
    for k, v in state.items():
        if k == "team":
            serializable["team_id"] = str(v.id)
        elif k == "node_by_id":
            serializable["node_by_id"] = {
                nid: {
                    "id": str(node.id),
                    "type": node.type,
                    "label": getattr(node, "label", ""),
                    "node_key": getattr(node, "node_key", ""),
                    "config": getattr(node, "config", {}) if isinstance(getattr(node, "config", None), dict) else {},
                    "workflow_id": str(getattr(node, "workflow_id", "")),
                }
                for nid, node in v.items()
            }
        elif k == "active_nodes":
            serializable["active_nodes"] = list(v) if isinstance(v, set) else v
        elif k == "adj":
            serializable["adj"] = dict(v)
        elif k == "edges_by_source":
            # 序列化 SQLAlchemy WorkflowEdge 对象为 dict
            serializable["edges_by_source"] = {
                sid: [
                    {
                        "id": str(e.id) if hasattr(e, "id") else str(e.get("id", "")),
                        "type": e.type if hasattr(e, "type") else e.get("type", "forward"),
                        "source_id": str(e.source_id) if hasattr(e, "source_id") else str(e.get("source_id", "")),
                        "target_id": str(e.target_id) if hasattr(e, "target_id") else str(e.get("target_id", "")),
                    }
                    for e in edges
                ]
                for sid, edges in v.items()
            }
        elif k in ("node_to_agent",):
            serializable["node_to_agent"] = {
                nid: str(a.id) if hasattr(a, "id") else str(a)
                for nid, a in v.items()
            }
        elif k == "visit_count":
            serializable["visit_count"] = dict(v) if hasattr(v, "items") else v
        elif k == "execution_order":
            serializable["execution_order"] = list(v) if isinstance(v, list) else v
        else:
            serializable[k] = v

    try:
        async with async_session() as db:
            result = await db.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.session_id == uuid.UUID(session_id)
                ).order_by(WorkflowInstance.created_at.desc()).limit(1)
            )
            instance = result.scalar()
            if instance:
                instance.state = serializable
                instance.status = "paused"
                instance.hitl_pending = True
                pause_nid = state.get("pause_nid") or state.get("hitl_nid")
                instance.hitl_node_id = (
                    uuid.UUID(pause_nid) if pause_nid else None
                )
                instance.last_activity_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(
                    "Persisted HITL state for session %s to instance %s",
                    session_id, instance.id,
                )
            else:
                # 不存在则创建 WorkflowInstance
                from app.models.workflow import Workflow
                wf_result = await db.execute(select(Workflow).limit(1))
                wf = wf_result.scalar()
                if wf:
                    pnid = state.get("pause_nid") or state.get("hitl_nid")
                    instance = WorkflowInstance(
                        id=uuid.uuid4(),
                        workflow_id=wf.id,
                        session_id=uuid.UUID(session_id),
                        status="paused",
                        state=serializable,
                        hitl_pending=True,
                        hitl_node_id=uuid.UUID(pnid) if pnid else None,
                        started_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(instance)
                    await db.commit()
                    logger.info(
                        "Created WorkflowInstance + persisted HITL state for session %s",
                        session_id,
                    )
    except Exception:
        logger.exception("Failed to persist HITL state for session %s", session_id)


async def _load_paused_state(session_id: str) -> dict | None:
    """从数据库加载持久化的暂停状态。内存缓存优先。

    Returns:
        恢复所需的 state dict，或 None 如果没有暂停状态。
    """
    # 内存缓存优先（最新状态）
    if session_id in _paused:
        return _paused.pop(session_id)

    # 从数据库恢复
    from app.core.database import async_session
    from app.models.workflow_instance import WorkflowInstance
    from app.models.workflow import WorkflowNode
    from app.models.team import Team
    from app.models.team_member import TeamMember
    from app.models.agent import Agent

    try:
        async with async_session() as db:
            result = await db.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.session_id == uuid.UUID(session_id)
                ).order_by(WorkflowInstance.created_at.desc()).limit(1)
            )
            instance = result.scalar()
            if not instance or not instance.state:
                return None

            saved = instance.state
            team_id = saved.get("team_id")

            # 从 DB 重建 team
            team = None
            team_agents: list[dict] = []
            available_roles: list[str] = []
            if team_id:
                team_result = await db.execute(
                    select(Team).where(Team.id == uuid.UUID(team_id))
                )
                team = team_result.scalar()
                if team:
                    members_result = await db.execute(
                        select(TeamMember).where(TeamMember.team_id == team.id)
                    )
                    members = list(members_result.scalars().all())
                    agent_ids = [m.agent_id for m in members if m.agent_id]
                    available_roles = [m.role_name for m in members if m.role_name]
                    if agent_ids:
                        agents_result = await db.execute(
                            select(Agent).where(Agent.id.in_(agent_ids))
                        )
                        agents_list = list(agents_result.scalars().all())
                        team_agents = [
                            {"id": str(a.id), "name": a.name}
                            for a in agents_list
                        ]

            # 反序列化 node_by_id
            node_by_id: dict = {}
            saved_nodes: dict[str, dict] = saved.get("node_by_id", {})
            for nid, ndata in saved_nodes.items():
                node = WorkflowNode()
                node.id = uuid.UUID(ndata["id"])
                node.type = ndata.get("type", "")
                node.label = ndata.get("label", "")
                node.node_key = ndata.get("node_key", "")
                node.config = ndata.get("config", {})
                node.workflow_id = uuid.UUID(ndata["workflow_id"]) if ndata.get("workflow_id") else None
                node_by_id[nid] = node

            # 反序列化 node_to_agent（通过 agent_id 查找）
            node_to_agent: dict = {}
            saved_agent_ids: dict[str, str] = saved.get("node_to_agent", {})
            if saved_agent_ids and team_agents:
                agent_lookup = {a["id"]: a for a in team_agents}
                for nid, aid in saved_agent_ids.items():
                    if aid in agent_lookup:
                        node_to_agent[nid] = agent_lookup[aid]

            # 恢复 edges_by_source（dict → SimpleNamespace 支持属性访问）
            from types import SimpleNamespace
            edges_by_source: dict[str, list] = {}
            saved_edges: dict[str, list] = saved.get("edges_by_source", {})
            for sid, elist in saved_edges.items():
                edge_objs = []
                for ed in elist:
                    if isinstance(ed, dict):
                        edge_objs.append(SimpleNamespace(
                            id=ed.get("id", ""),
                            type=ed.get("type", "forward"),
                            source_id=ed.get("source_id", ""),
                            target_id=ed.get("target_id", ""),
                        ))
                    else:
                        edge_objs.append(ed)
                edges_by_source[sid] = edge_objs

            # 恢复 adj
            adj = saved.get("adj", {})
            if isinstance(adj, list):
                adj = {str(i): v for i, v in enumerate(adj)}

            # 恢复 visit_count
            visit_count = saved.get("visit_count", {})
            if isinstance(visit_count, list):
                visit_count = {}

            # 恢复状态 — 兼容新旧两种格式
            state = {
                "team": team,
                "user_message": saved.get("user_message", ""),
                "team_agents": team_agents,
                "available_roles": saved.get("available_roles", available_roles),
                # 新格式字段
                "pause_nid": saved.get("pause_nid", saved.get("hitl_nid", "")),
                "artifacts": saved.get("artifacts", {}),
                "node_by_id": node_by_id,
                "node_to_agent": node_to_agent,
                "nkey_to_nid": saved.get("nkey_to_nid", {}),
                "edges_by_source": edges_by_source,
                "adj": adj,
                "visit_count": visit_count,
                "execution_order": saved.get("execution_order", []),
                "ws_path": saved.get("ws_path", ""),
                # 旧格式兼容（回退用）
                "hitl_nid": saved.get("hitl_nid", saved.get("pause_nid", "")),
                "hitl_node_key": saved.get("hitl_node_key", ""),
                "hitl_label": saved.get("hitl_label", ""),
                "levels": saved.get("levels", []),
                "level_idx": saved.get("level_idx", 0),
                "node_deps": saved.get("node_deps", {}),
                "active_nodes": set(saved.get("active_nodes", [])),
                "pending_hitl_nids": saved.get("pending_hitl_nids", []),
            }

            # 清除持久化标记
            instance.hitl_pending = False
            instance.state = None
            await db.commit()

            logger.info("Restored HITL state from DB for session %s", session_id)
            return state
    except Exception:
        logger.exception("Failed to load HITL state from DB for session %s", session_id)
        return None


def has_paused(session_id: str) -> bool:
    """检查指定会话是否有 HITL 暂停的工作流（内存 + 数据库）。"""
    if session_id in _paused:
        return True
    # 数据库检查在事件循环运行中不可用，仅检查内存
    return False


def cancel_paused(session_id: str) -> bool:
    """取消指定会话的 HITL 暂停工作流。返回 True 表示成功取消。"""
    from app.core.database import async_session as _async_session
    from app.models.workflow_instance import WorkflowInstance

    cancelled = _paused.pop(session_id, None) is not None

    # 同时清理数据库中的暂停状态
    async def _clear_db():
        try:
            async with _async_session() as db:
                result = await db.execute(
                    select(WorkflowInstance).where(
                        WorkflowInstance.session_id == uuid.UUID(session_id)
                    ).order_by(WorkflowInstance.created_at.desc()).limit(1)
                )
                instance = result.scalar()
                if instance:
                    instance.hitl_pending = False
                    instance.state = None
                    instance.status = "cancelled"
                    await db.commit()
        except Exception:
            logger.exception("Failed to clear HITL state from DB for session %s", session_id)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_clear_db())
    except RuntimeError:
        pass

    return cancelled
