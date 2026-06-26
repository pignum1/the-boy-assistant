"""M3: Agent Orchestrator — check agent availability, handle missing roles.

Verifies all required roles have available agents.
If agents are missing, triggers HITL to invite/create agents.
If all agents are ready, passes assignments to M4.
"""

import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── Role display names ──

ROLE_NAMES: dict[str, str] = {
    "pm": "产品经理",
    "architect": "架构师",
    "backend_dev": "后端工程师",
    "frontend_dev": "前端工程师",
    "tester": "测试员",
    "ui_designer": "UI设计师",
    "devops": "部署运维工程师",
}


# Role ID → Chinese name / keyword mapping for fuzzy matching
ROLE_MATCH_KEYWORDS: dict[str, list[str]] = {
    "pm": ["产品经理", "pm", "product"],
    "product_manager": ["产品经理", "pm", "product"],
    "architect": ["架构师", "architect", "架构"],
    "backend_dev": ["后端工程师", "backend", "后端"],
    "frontend_dev": ["前端工程师", "frontend", "前端"],
    "tester": ["测试员", "测试工程师", "test", "qa", "测试"],
    "ui_designer": ["UI设计师", "ui", "设计", "design"],
    "devops": ["部署运维", "运维工程师", "devops", "运维", "部署"],
}

def _role_matches(required_role: str, agent_role: str) -> bool:
    """Check if an agent's role matches the required role (fuzzy match)."""
    if not agent_role:
        return False
    r_lower = required_role.lower().strip()
    a_lower = agent_role.lower().strip()

    # Direct match
    if r_lower == a_lower:
        return True

    # Keyword match from mapping
    keywords = ROLE_MATCH_KEYWORDS.get(r_lower, [r_lower])
    for kw in keywords:
        if kw in a_lower or a_lower in kw:
            return True

    # Also try matching agent_role against required_role keywords
    for rid, kws in ROLE_MATCH_KEYWORDS.items():
        if any(kw in a_lower for kw in kws):
            if rid == r_lower:
                return True

    return False


def check_agent_availability(
    required_roles: list[str],
    team_agents: list[dict[str, Any]],
) -> tuple[dict[str, dict], list[str]]:
    """Check if all required roles have available agents.

    Args:
        required_roles: Role IDs needed (e.g., ["architect", "backend_dev"]).
        team_agents: Team members [{agent_id, name, role, status}].

    Returns:
        (assignments: {role: agent_info}, missing: [role_name, ...])
    """
    assignments: dict[str, dict] = {}
    missing: list[str] = []
    used_agents: set = set()

    for role in required_roles:
        matched = None
        for agent in team_agents:
            if agent.get("agent_id") in used_agents:
                continue
            agent_role = agent.get("role", "")
            if _role_matches(role, agent_role):
                matched = agent
                used_agents.add(agent.get("agent_id"))
                break

        if matched:
            assignments[role] = matched
        else:
            missing.append(role)

    return assignments, missing


def generate_missing_agent_message(missing_roles: list[str]) -> str:
    """Generate a human-friendly message for missing agents."""
    if not missing_roles:
        return ""

    names = [ROLE_NAMES.get(r, r) for r in missing_roles]
    roles_list = "、".join(names)

    return (
        f"当前团队缺少以下角色: {roles_list}。\n\n"
        f"你可以:\n"
        f"• 📋 从Agent库邀请已有 {roles_list}\n"
        f"• 🆕 快速创建一个新的Agent\n"
        f"• ⏭ 跳过这些角色，调整执行计划"
    )


# ── LangGraph node ──

async def m3_orchestrate_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M3 agent orchestration.

    Checks agent availability and either:
    - Assigns agents → proceed to M4
    - Missing agents → trigger HITL invite
    """
    required_roles = state.get("required_roles", [])
    team_agents = state.get("team_agents", [])

    assignments, missing = check_agent_availability(required_roles, team_agents)

    if missing:
        logger.info(f"M3: missing agents for roles: {missing}")
        return {
            "status": "clarifying",
            "agent_assignments": assignments,
            "missing_roles": missing,
            "hitl_type": "agent_invite",
            "hitl_message": generate_missing_agent_message(missing),
            "hitl_options": [
                {"label": "📋 邀请Agent", "value": "invite"},
                {"label": "🆕 创建Agent", "value": "create"},
                {"label": "⏭ 跳过缺失角色", "value": "skip"},
            ],
            "_content": generate_missing_agent_message(missing),
            "_agent_name": team_agents[0].get("name", "Supervisor") if team_agents else "Supervisor",
        }

    logger.info(f"M3: all agents available, assignments: {list(assignments.keys())}")
    return {
        "status": "executing",
        "agent_assignments": assignments,
        "missing_roles": [],
        "_content": f"✅ 已分配 {len(assignments)} 个角色，开始执行任务。",
        "_agent_name": team_agents[0].get("name", "Supervisor") if team_agents else "Supervisor",
    }


# ── Route function for graph edges ──

def route_after_m3(state: CollabState) -> str:
    """Determine next node after M3.

    Returns:
        "m4_decompose" → all agents ready
        "hitl"         → missing agents, need user action
    """
    missing = state.get("missing_roles", [])
    if missing:
        return "hitl"
    return "m4_decompose"
