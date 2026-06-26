"""M6 Org Loader — loads organizational hierarchy and initializes delegation tree.

This node runs once after M4 (task decomposition), before any delegation.
It does three things:
1. Loads org_structure from DB (team_id → supervisor config + relations)
2. Builds delegation_tree from org_structure (Route B)
3. Broadcasts the task_dag to the frontend
"""

import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


async def m6_org_loader_node(state: CollabState) -> dict[str, Any]:
    """Load org structure and initialize delegation tree.

    Route B: builds delegation_tree instead of execution_levels.
    The leader's initial delegation will be set up by m6_delegate_root.
    """
    task_dag = state.get("task_dag", {})
    team_id = state.get("team_id", "")
    session_id = state.get("session_id", "")
    requirements_anchor = state.get("requirements_anchor", "")

    phases = task_dag.get("phases", [])
    if not phases:
        return {
            "status": "completed",
            "artifacts": {},
            "files_changed": [],
            "delegation_tree": {"leader_id": None, "leader_name": "", "tree": {}},
            "delegation_stack": [],
            "current_delegation": None,
            "delegation_depth": 0,
            "max_delegation_depth": 5,
            "escalation_history": [],
            "_content": "⚠️ 没有可执行的任务",
            "_agent_name": "调度器",
        }

    # ── 1. Load org structure ──
    org_structure = None
    try:
        from .org_hierarchy import load_org_structure
        org_structure = await load_org_structure(team_id)
        if org_structure:
            logger.info(
                f"M6 OrgLoader: loaded org structure — leader={org_structure.get('leader_member_id')}, "
                f"relations={len(org_structure.get('relations', []))}, "
                f"members={len(org_structure.get('member_roles', {}))}"
            )
        else:
            logger.info("M6 OrgLoader: no org structure configured — flat team mode")
    except Exception as e:
        logger.warning(f"M6 OrgLoader: failed to load org structure: {e}")

    # ── 2. Build delegation tree (Route B) ──
    from .org_hierarchy import build_delegation_tree
    delegation_tree = build_delegation_tree(org_structure, requirements_anchor or "")
    logger.info(
        f"M6 OrgLoader: built delegation tree — "
        f"leader={delegation_tree.get('leader_id')}, "
        f"has_org={org_structure is not None}"
    )

    # ── 3. Broadcast task_dag to frontend ──
    try:
        from app.services.ws_broadcaster import manager
        from datetime import datetime

        normalized_phases = []
        total_tasks = 0
        for phase_idx, phase in enumerate(phases):
            ph_id = phase.get("id") or f"phase-{phase_idx + 1}"
            tasks_norm = []
            for t in phase.get("tasks", []):
                tasks_norm.append({
                    "id": t.get("id", ""),
                    "name": t.get("title") or t.get("name") or t.get("description", ""),
                    "agent_id": t.get("assigned_to") or t.get("agent_id") or t.get("assigned_role", ""),
                    "agent_name": t.get("agent_name") or t.get("assigned_role", "Worker"),
                    "agent_emoji": t.get("agent_emoji", "🤖"),
                    "depends_on": t.get("depends_on", []),
                })
                total_tasks += 1
            normalized_phases.append({
                "id": ph_id,
                "name": phase.get("name", ""),
                "tasks": tasks_norm,
            })

        await manager.broadcast_to_session(session_id, {
            "type": "task_dag",
            "source": "m6_org_loader",
            "timestamp": datetime.now().isoformat(),
            "payload": {"phases": normalized_phases, "total_tasks": total_tasks},
        })
        logger.info(f"M6 OrgLoader: broadcast task_dag — {len(phases)} phases, {total_tasks} tasks")

        # Persist the task_dag to SessionTask so a page refresh can restore the
        # task tree (the live WS task_dag event is never re-sent on reload).
        try:
            import uuid as _uuid
            from app.core.database import async_session
            from app.models.session_task import SessionTask
            from sqlalchemy import delete

            async def _persist():
                async with async_session() as db:
                    sid = _uuid.UUID(session_id)
                    # Replace any prior tasks for this session (re-decomposition)
                    await db.execute(delete(SessionTask).where(SessionTask.session_id == sid))
                    for phase in normalized_phases:
                        for t in phase.get("tasks", []):
                            db.add(SessionTask(
                                session_id=sid,
                                title=t.get("name", "")[:200],
                                status="pending",
                                assigned_agent_name=t.get("agent_name", ""),
                            ))
                    await db.commit()
            import asyncio
            asyncio.create_task(_persist())
        except Exception as e:
            logger.warning(f"M6 OrgLoader: persist task_dag failed: {e}")
    except Exception as e:
        logger.warning(f"M6 OrgLoader: task_dag broadcast failed: {e}")

    task_count = sum(len(p.get("tasks", [])) for p in phases)
    org_desc = f"，组织架构含 {len(org_structure.get('relations', []))} 条汇报关系" if org_structure else "（扁平模式）"

    return {
        "org_structure": org_structure,
        "delegation_tree": delegation_tree,
        "delegation_stack": [],
        "current_delegation": None,
        "delegation_depth": 0,
        "max_delegation_depth": 5,
        "escalation_history": [],
        "status": "executing",
        "_content": f"📋 已构建委派树，共 **{task_count}** 个任务" + org_desc,
        "_agent_name": "调度器",
    }
