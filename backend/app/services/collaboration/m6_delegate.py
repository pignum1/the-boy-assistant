"""M6 Delegate — hierarchical delegation nodes (Route B core).

Two physical LangGraph nodes sharing _delegate_think() logic:
  m6_delegate_root_node — Leader entry (from m6_org_loader)
  m6_delegate_sub_node  — Recursive entry (from m6_delegate_push)

This avoids LangGraph's same-node recursion risk with checkpointing:
the root and sub nodes are separate in the graph but share the same
thinking logic via _delegate_think().
"""

import json
import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── Shared delegation thinking logic ──────────────────────────────

async def _delegate_think(state: CollabState) -> dict[str, Any]:
    """Shared delegation thinking logic used by both root and sub nodes.

    Determines whether the current delegation target is a leaf worker
    or a supervisor that needs to decompose the goal.

    Returns state updates including `_delegate_route`:
        "worker"         → route to m6_execute_worker
        "supervisor"     → route to m6_plan_validate (then m6_delegate_push)
        "merge_to_parent" → route to m6_collect (depth exceeded)
    """
    from .org_hierarchy import find_subordinates, find_member_info, format_org_tree_desc

    current = state.get("current_delegation", {})
    org = state.get("org_structure")
    member_id = current.get("member_id", "")
    goal = current.get("goal", "")

    # ── Check if leaf worker ──
    subordinate_ids = []
    if org:
        subordinate_ids = find_subordinates(org, member_id)

    member_info = find_member_info(org, member_id) if org else None
    can_delegate = member_info.get("can_delegate", True) if member_info else True

    # Get real agent name from org hierarchy, with Chinese name fallback
    ROLE_CN = {"pm": "产品经理", "product_manager": "产品经理", "architect": "架构师",
               "backend_dev": "后端工程师", "frontend_dev": "前端工程师",
               "tester": "测试员", "ui_designer": "UI设计师", "devops": "部署运维"}
    raw_role = current.get("role_name", "Worker")
    agent_display_name = member_info.get("agent_name") or ROLE_CN.get(raw_role, raw_role)

    if not subordinate_ids or not can_delegate:
        logger.info(f"M6 Delegate: {member_id} is a leaf worker (subordinates={len(subordinate_ids)})")
        return {
            "_delegate_route": "worker",
            "_content": f"🔧 {agent_display_name} 开始执行任务...",
            "_agent_name": agent_display_name,
        }

    # ── Dynamic depth protection ──
    depth = state.get("delegation_depth", 0)
    max_depth = state.get("max_delegation_depth", 5)

    if depth >= max_depth:
        logger.warning(
            f"M6 Delegate: depth {depth} >= max {max_depth}, "
            f"merging to parent for {member_id}"
        )
        return {
            "_delegate_route": "merge_to_parent",
            "_content": f"⚠️ 达到最大委派深度 {max_depth}，任务合并到{agent_display_name}",
            "_agent_name": agent_display_name,
        }

    # ── Supervisor: LLM decompose ──
    think_result = await _llm_decompose(state, current, subordinate_ids)
    return think_result


async def _llm_decompose(
    state: CollabState,
    current: dict[str, Any],
    subordinate_ids: list[str],
) -> dict[str, Any]:
    """Call LLM to decompose current goal into delegation_plan.

    The LLM acts as the supervisor, deciding how to split the goal
    among subordinates based on their roles and capabilities.

    Returns:
        {"_delegate_route": "supervisor", "delegation_plan": {...}}
    """
    from .org_hierarchy import (
        find_member_info,
        format_org_tree_desc,
    )

    org = state.get("org_structure", {})
    goal = current.get("goal", "")
    member_id = current.get("member_id", "")
    role_name = current.get("role_name", "")
    role_context = current.get("role_context", "")
    task_dag = state.get("task_dag", {})

    # Build subordinate info for prompt
    sub_info_lines = []
    for sid in subordinate_ids:
        info = find_member_info(org, sid)
        if info:
            sub_info_lines.append(
                f"- {info['role_name']} (agent: {info['agent_name']}, "
                f"技能: {', '.join(info.get('capabilities', [])) or '通用'})"
            )

    # Reference task_dag for context (optional)
    dag_context = ""
    if task_dag and task_dag.get("phases"):
        tasks_flat = []
        for phase in task_dag["phases"]:
            for t in phase.get("tasks", []):
                tasks_flat.append(
                    f"  [{t.get('id', '?')}] {t.get('title', '')} → {t.get('assigned_role', '')}"
                )
        if tasks_flat:
            dag_context = "## 已有的任务分解参考（可调整）\n" + "\n".join(tasks_flat[:20])

    prompt = f"""你是 {role_name}，需要将以下目标分解并分配给你的下属。

{role_context}

## 上级分配给你的目标
{goal}

## 你的下属
{chr(10).join(sub_info_lines)}

{dag_context}

请分解目标并分配给下属。每个下属一个任务。
输出严格 JSON（不要 markdown 代码块）：
{{
  "assignments": [
    {{
      "member_id": "下属ID",
      "role_name": "下属角色名",
      "goal": "分配给这个下属的具体目标",
      "is_leaf": true或false
    }}
  ],
  "reasoning": "你的分解思路（一句话）"
}}

注意：
- member_id 必须是上面列出的下属 ID 之一
- goal 要具体、可执行
- is_leaf: 如果该下属没有自己的下属就填 true
"""

    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            # Use the supervisor's agent if available
            member_info = find_member_info(org, member_id)
            agent_id = member_info.get("agent_id") if member_info else None
            agent = None
            if agent_id:
                stmt = select(Agent).where(Agent.id == agent_id)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                logger.warning(f"M6 Delegate: no agent for {member_id}, using algorithmic fallback")
                return _algorithmic_decompose_fallback(goal, subordinate_ids, org)

            # Real agent name for display (mirrors the role→name resolution pattern)
            agent_display_name = (
                (agent.name if agent else "")
                or (member_info.get("agent_name") if member_info else "")
                or role_name
            )

            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=False, save_memory=False,
            )

            raw = llm_result.get("content", "")
            parsed = _parse_json_output(raw)

            # Ensure member_id field is present in each assignment
            assignments = parsed.get("assignments", [])
            for a in assignments:
                if "member_id" not in a and "id" in a:
                    a["member_id"] = a.pop("id")

            if not assignments:
                logger.warning(f"M6 Delegate: LLM returned empty assignments, using fallback")
                return _algorithmic_decompose_fallback(goal, subordinate_ids, org)

            reasoning = parsed.get("reasoning", "")
            logger.info(
                f"M6 Delegate: {role_name} decomposed into {len(assignments)} assignments"
            )

            return {
                "_delegate_route": "supervisor",
                "delegation_plan": {
                    "assignments": assignments,
                    "reasoning": reasoning,
                },
                "_content": f"📋 **{agent_display_name}** 分解目标: {reasoning or f'分配给 {len(assignments)} 个下属'}",
                "_agent_name": agent_display_name,
            }

    except Exception as e:
        logger.error(f"M6 Delegate: LLM decompose failed: {e}", exc_info=True)
        return _algorithmic_decompose_fallback(goal, subordinate_ids, org)


def _algorithmic_decompose_fallback(
    goal: str,
    subordinate_ids: list[str],
    org: dict,
) -> dict[str, Any]:
    """Fallback: evenly split goal among subordinates when LLM fails."""
    from .org_hierarchy import find_member_info, find_subordinates

    assignments = []
    for sid in subordinate_ids:
        info = find_member_info(org, sid)
        sub_subs = find_subordinates(org, sid)
        assignments.append({
            "member_id": sid,
            "role_name": info.get("role_name", "") if info else "",
            "goal": f"{goal} — {info.get('role_name', '下属') if info else '下属'} 部分",
            "is_leaf": len(sub_subs) == 0,
        })

    logger.info(f"M6 Delegate: algorithmic fallback → {len(assignments)} assignments")

    return {
        "_delegate_route": "supervisor",
        "delegation_plan": {
            "assignments": assignments,
            "reasoning": "算法分配（LLM 不可用）",
        },
        "_content": f"📋 算法分配: {len(assignments)} 个下属",
        "_agent_name": "系统",
    }


# ── JSON parsing (triple-fallback pattern) ──

def _parse_json_output(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output with triple fallback."""
    # Direct JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Code block
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Braces
    if "{" in raw and "}" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        try:
            return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

    return {"assignments": [], "reasoning": raw[:200]}


# ── LangGraph nodes ───────────────────────────────────────────────

async def m6_delegate_root_node(state: CollabState) -> dict[str, Any]:
    """Leader entry: initialize delegation from tree root.

    Reads delegation_tree built by m6_org_loader, sets up the
    initial current_delegation for the leader, then delegates.
    """
    tree_data = state.get("delegation_tree", {})
    leader_id = tree_data.get("leader_id")
    leader_name = tree_data.get("leader_name", "Leader")
    org = state.get("org_structure")
    requirements = state.get("requirements_anchor", "")

    # ── Flat team fallback (no org structure) ──
    if not leader_id or not org:
        logger.info("M6 DelegateRoot: no org structure, flat team mode")
        return {
            "current_delegation": {
                "member_id": "flat_worker",
                "role_name": "Worker",
                "goal": requirements,
                "is_leaf": True,
                "is_root": True,
            },
            "delegation_stack": [],
            "delegation_depth": 0,
            "max_delegation_depth": 5,
            "_delegate_route": "worker",
            "status": "executing",
            "_content": "🔧 无组织架构，直接执行...",
            "_agent_name": "调度器",
        }

    # ── Initialize leader delegation ──
    from .org_hierarchy import generate_role_context

    role_ctx = generate_role_context(org, leader_id)

    current_delegation = {
        "member_id": leader_id,
        "role_name": leader_name,
        "goal": requirements,
        "role_context": role_ctx,
        "is_leaf": False,
        "is_root": True,
    }

    # Merge with _delegate_think result
    state_with_current = {**state, "current_delegation": current_delegation}
    think_result = await _delegate_think(state_with_current)

    return {
        "current_delegation": current_delegation,
        "delegation_stack": [],
        "delegation_depth": 0,
        "max_delegation_depth": 5,
        "status": "executing",
        **think_result,
    }


async def m6_delegate_sub_node(state: CollabState) -> dict[str, Any]:
    """Recursive entry: process current_delegation from stack top.

    Called after m6_delegate_push sets up current_delegation for
    the next subordinate in the DFS traversal.
    """
    # ── Check for interrupt ──
    from .interrupt_coordinator import interrupt_coordinator
    session_id = state.get("session_id", "")
    if interrupt_coordinator.has_pending(session_id):
        req = interrupt_coordinator.consume(session_id)
        msg = req.message if req else ""
        mode = req.mode if req else "soft"
        return {
            "status": "interrupted",
            "interrupt_message": msg,
            "interrupt_mode": mode,
            "_content": f"⏸️ 收到中断请求: {msg}",
            "_agent_name": "调度器",
        }

    # ── Check parallel workers ──
    current = state.get("current_delegation", {})
    member_id = current.get("member_id", "")

    think_result = await _delegate_think(state)

    # ── If this is a leaf worker and we have multiple pending, try parallel ──
    if think_result.get("_delegate_route") == "worker":
        stack = state.get("delegation_stack", [])
        if stack:
            top = stack[-1]
            pending = top.get("pending_assignments", [])
            # If there are multiple pending leaf workers, mark for parallel
            if len(pending) > 1 and all(
                _is_leaf_member(state, pid) for pid in pending
            ):
                think_result["_delegate_route"] = "worker"  # stays worker, parallel handled in execute
                think_result["_parallel_pending"] = pending

    logger.info(
        f"M6 DelegateSub: {member_id} → route={think_result.get('_delegate_route', '?')}"
    )

    return think_result


def _is_leaf_member(state: CollabState, member_id: str) -> bool:
    """Check if a member is a leaf (has no subordinates)."""
    from .org_hierarchy import find_subordinates
    org = state.get("org_structure")
    if not org:
        return True
    return len(find_subordinates(org, member_id)) == 0


# ── Routing ──────────────────────────────────────────────────────

def route_after_delegate(state: CollabState) -> str:
    """Route after m6_delegate_root or m6_delegate_sub.

    Returns:
        "m6_execute_worker"  — leaf worker or parallel workers
        "m6_collect"         — merge to parent (depth exceeded)
        "m6_plan_validate"   — supervisor, validate the delegation plan
    """
    route = state.get("_delegate_route", "")

    if route in ("worker", "parallel_collect"):
        return "m6_execute_worker"
    if route == "merge_to_parent":
        return "m6_collect"
    if route == "supervisor":
        return "m6_plan_validate"

    # Default: treat as worker
    logger.warning(f"M6 Delegate: unknown route '{route}', defaulting to worker")
    return "m6_execute_worker"
