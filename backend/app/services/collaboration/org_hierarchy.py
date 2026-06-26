"""Organizational hierarchy utilities for supervisor mode.

Builds org tree from TeamSupervisorConfig + TeamSupervisorRelation data
and provides lookup functions for reviewer assignment and escalation.

In a flat team (no org structure configured), all functions gracefully
return None/defaults so the execution falls back to the original M6 behavior.
"""

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ── Org structure loading ──

async def load_org_structure(team_id: str) -> dict[str, Any] | None:
    """Load org hierarchy from DB into a dict suitable for CollabState.

    Queries TeamSupervisorConfig (for leader_member_id) and
    TeamSupervisorRelation (for reporting chain). Also resolves
    member_id -> {role_name, agent_id, agent_name} from TeamMember.

    Returns None if no org structure is configured (flat team).
    """
    from app.core.database import async_session
    from app.services.team_mode_service import TeamModeService
    from app.models.team_member import TeamMember
    from app.models.agent import Agent
    from sqlalchemy import select

    tid = uuid.UUID(team_id)

    async with async_session() as db:
        svc = TeamModeService(db)

        # 1. Read supervisor config → leader_member_id
        config = await svc.get_supervisor_config(tid)
        leader_id = str(config.leader_member_id) if config and config.leader_member_id else None

        # 2. Read supervisor relations
        relations = await svc.get_supervisor_relations(tid)
        relation_list = [
            {
                "member_id": str(r.member_id),
                "supervisor_member_id": str(r.supervisor_member_id),
            }
            for r in relations
        ]

        # 3. If no leader and no relations, this is a flat team
        if not leader_id and not relation_list:
            return None

        # 4. Read team members to build member_roles map
        member_ids = set()
        if leader_id:
            member_ids.add(uuid.UUID(leader_id))
        for r in relation_list:
            member_ids.add(uuid.UUID(r["member_id"]))
            member_ids.add(uuid.UUID(r["supervisor_member_id"]))

        stmt = select(TeamMember).where(TeamMember.id.in_(member_ids))
        result = await db.execute(stmt)
        members = result.scalars().all()

        # 5. Read agent info for each member
        agent_ids = {m.agent_id for m in members}
        agent_stmt = select(Agent).where(Agent.id.in_(agent_ids))
        agent_result = await db.execute(agent_stmt)
        agents = {str(a.id): a for a in agent_result.scalars().all()}

        member_roles = {}
        for m in members:
            agent = agents.get(str(m.agent_id))
            member_roles[str(m.id)] = {
                "role_name": m.role_name or "成员",
                "agent_id": str(m.agent_id),
                "agent_name": agent.name if agent else m.role_name,
                "capabilities": m.capabilities or [],
                "can_delegate": m.can_delegate,
            }

        return {
            "leader_member_id": leader_id,
            "relations": relation_list,
            "member_roles": member_roles,
        }

    return None


# ── Tree traversal utilities ──

def find_supervisor_for_member(
    org_structure: dict[str, Any],
    member_id: str,
) -> str | None:
    """Return the supervisor_member_id for a given member_id.

    Returns None if member has no supervisor (they are the leader or not in tree).
    """
    for r in org_structure.get("relations", []):
        if r["member_id"] == member_id:
            return r["supervisor_member_id"]
    return None


def find_subordinates(
    org_structure: dict[str, Any],
    member_id: str,
) -> list[str]:
    """Return all direct subordinates of a given member_id."""
    return [
        r["member_id"]
        for r in org_structure.get("relations", [])
        if r["supervisor_member_id"] == member_id
    ]


def _walk_to_root(
    org_structure: dict[str, Any],
    member_id: str,
) -> list[str]:
    """Walk from a member up to the tree root, returning the path (inclusive)."""
    path = [member_id]
    current = member_id
    while True:
        sup = find_supervisor_for_member(org_structure, current)
        if not sup:
            break
        path.append(sup)
        current = sup
    return path


def _find_lowest_common_ancestor(
    org_structure: dict[str, Any],
    member_ids: list[str],
) -> str | None:
    """Find the LCA (lowest common ancestor) of multiple members in the org tree.

    Used to determine who should review a level that has multiple workers.
    The LCA is the lowest person in the hierarchy who oversees all workers.
    """
    if not member_ids:
        return org_structure.get("leader_member_id")

    if len(member_ids) == 1:
        # Single worker → their direct supervisor is the reviewer
        return find_supervisor_for_member(org_structure, member_ids[0])

    # Build paths to root for each member
    paths = [_walk_to_root(org_structure, mid) for mid in member_ids]
    if not paths or not all(paths):
        return org_structure.get("leader_member_id")

    # Find LCA by walking from the shortest path upward
    min_len = min(len(p) for p in paths)
    for depth in range(min_len):
        # Check if all paths share the same node at this depth from root
        # (from root = from end of path, going backward)
        candidates = {p[-(depth + 1)] for p in paths}
        if len(candidates) == 1:
            return candidates.pop()

    # No common ancestor found → leader is the fallback
    return org_structure.get("leader_member_id")


def find_reviewer_for_level(
    org_structure: dict[str, Any] | None,
    level_tasks: list[dict[str, Any]],
    agent_assignments: dict[str, Any],
) -> dict[str, Any] | None:
    """Determine who should review a level's output.

    Strategy:
    1. Collect member_ids for all tasks in this level (via assigned_role -> member_roles)
    2. Find each member's supervisor
    3. Find the LCA in the org tree
    4. Return {member_id, role_name, agent_id, agent_name} for the reviewer
    5. If no supervisor found, return the team leader
    6. If no leader either, return None (skip review)

    Returns None when review should be skipped.
    """
    if not org_structure:
        return None

    member_roles = org_structure.get("member_roles", {})
    relations = org_structure.get("relations", [])

    # No org relations configured → skip review
    if not relations and not org_structure.get("leader_member_id"):
        return None

    # Collect member_ids of workers in this level
    worker_member_ids = []
    for task in level_tasks:
        assigned_role = task.get("assigned_role", "")
        agent_info = agent_assignments.get(assigned_role, {})
        agent_id = agent_info.get("agent_id", "")

        # Find which member has this agent_id
        for mid, info in member_roles.items():
            if info.get("agent_id") == agent_id:
                worker_member_ids.append(mid)
                break

    if not worker_member_ids:
        # No matching members found → use leader if available
        leader_id = org_structure.get("leader_member_id")
        if leader_id and leader_id in member_roles:
            return {
                "member_id": leader_id,
                "role_name": member_roles[leader_id]["role_name"],
                "agent_id": member_roles[leader_id]["agent_id"],
                "agent_name": member_roles[leader_id]["agent_name"],
            }
        return None

    # Find the reviewer via LCA
    reviewer_id = _find_lowest_common_ancestor(org_structure, worker_member_ids)

    if not reviewer_id:
        leader_id = org_structure.get("leader_member_id")
        if leader_id and leader_id in member_roles:
            return {
                "member_id": leader_id,
                "role_name": member_roles[leader_id]["role_name"],
                "agent_id": member_roles[leader_id]["agent_id"],
                "agent_name": member_roles[leader_id]["agent_name"],
            }
        return None

    if reviewer_id not in member_roles:
        return None

    return {
        "member_id": reviewer_id,
        "role_name": member_roles[reviewer_id]["role_name"],
        "agent_id": member_roles[reviewer_id]["agent_id"],
        "agent_name": member_roles[reviewer_id]["agent_name"],
    }


def find_escalation_target(
    org_structure: dict[str, Any] | None,
    current_reviewer_member_id: str,
) -> dict[str, Any] | None:
    """Find who to escalate to above the current reviewer.

    Walks up the org tree. Returns None if already at the top
    (meaning escalation should go to HITL).

    Cap: max 3 levels of escalation upward.
    """
    if not org_structure:
        return None

    member_roles = org_structure.get("member_roles", {})

    # Walk up from current reviewer
    target_id = find_supervisor_for_member(org_structure, current_reviewer_member_id)

    if not target_id:
        # Current reviewer has no supervisor → check if they're the leader
        leader_id = org_structure.get("leader_member_id")
        if current_reviewer_member_id == leader_id:
            # Already at the top → escalate to HITL
            return None
        # Not at leader → escalate to leader
        target_id = leader_id

    if not target_id or target_id not in member_roles:
        return None

    return {
        "member_id": target_id,
        "role_name": member_roles[target_id]["role_name"],
        "agent_id": member_roles[target_id]["agent_id"],
        "agent_name": member_roles[target_id]["agent_name"],
    }


def format_org_tree_desc(
    org_structure: dict[str, Any] | None,
) -> str:
    """Format org structure as a human-readable tree for LLM prompts.

    Returns empty string if no org structure.
    """
    if not org_structure:
        return ""

    member_roles = org_structure.get("member_roles", {})
    leader_id = org_structure.get("leader_member_id")
    relations = org_structure.get("relations", [])

    if not leader_id and not relations:
        return ""

    # Build a child map: {parent_id: [child_ids]}
    children: dict[str, list[str]] = {}
    all_members = set()
    if leader_id:
        all_members.add(leader_id)
    for r in relations:
        sup_id = r["supervisor_member_id"]
        mem_id = r["member_id"]
        all_members.add(sup_id)
        all_members.add(mem_id)
        if sup_id not in children:
            children[sup_id] = []
        children[sup_id].append(mem_id)

    # Find roots: members who are not children of anyone
    child_ids = set(children.keys())
    for c_list in children.values():
        child_ids.update(c_list)
    parent_ids = set()
    for r in relations:
        parent_ids.add(r["supervisor_member_id"])
    roots = [m for m in all_members if m not in {r["member_id"] for r in relations}]
    # Alternatively, use leader_id as the explicit root
    if leader_id:
        roots = [leader_id]
    elif not roots:
        roots = [r["supervisor_member_id"] for r in relations if r["supervisor_member_id"] not in child_ids]

    def _format_node(mid: str, indent: int = 0) -> str:
        info = member_roles.get(mid, {})
        name = info.get("role_name", "未知")
        agent_name = info.get("agent_name", "")
        prefix = "  " * indent + ("├─ " if indent > 0 else "")
        label = f"{name}" + (f" ({agent_name})" if agent_name and agent_name != name else "")
        lines = [prefix + label]
        for child_id in children.get(mid, []):
            lines.append(_format_node(child_id, indent + 1))
        return "\n".join(lines)

    lines = []
    for root in roots:
        lines.append(_format_node(root))
    return "\n".join(lines)


# ── Route B: 委派树构建 + 角色上下文 ─────────────────────────


def build_delegation_tree(
    org_structure: dict[str, Any] | None,
    requirements_anchor: str,
) -> dict[str, Any]:
    """从 org_structure 构建初始委派树。

    Returns:
        {"leader_id": str | None, "leader_name": str, "tree": {member_id: TreeNode}}
        无 org_structure 时返回 {"leader_id": None, "leader_name": "", "tree": {}}

    TreeNode 结构:
        {member_id, role_name, agent_id, goal, role_context,
         artifact_refs: [], review_result: None, sub_delegations: {child_id: TreeNode}}
    """
    if not org_structure:
        return {"leader_id": None, "leader_name": "", "tree": {}}

    member_roles = org_structure.get("member_roles", {})
    relations = org_structure.get("relations", [])
    leader_id = org_structure.get("leader_member_id")

    # 构建 children map
    children_map: dict[str, list[str]] = {}
    for r in relations:
        sup_id = r["supervisor_member_id"]
        mem_id = r["member_id"]
        if sup_id not in children_map:
            children_map[sup_id] = []
        children_map[sup_id].append(mem_id)

    # 递归构建树节点
    def _build_node(mid: str, goal: str = "") -> dict[str, Any]:
        info = member_roles.get(mid, {})
        role_ctx = generate_role_context(org_structure, mid)
        node: dict[str, Any] = {
            "member_id": mid,
            "role_name": info.get("role_name", ""),
            "agent_id": info.get("agent_id"),
            "goal": goal,
            "role_context": role_ctx,
            "artifact_refs": [],
            "review_result": None,
            "sub_delegations": {},
        }
        for child_id in children_map.get(mid, []):
            child_info = member_roles.get(child_id, {})
            child_goal = ""  # goal 在 m6_delegate LLM 分解时填入
            node["sub_delegations"][child_id] = _build_node(child_id, child_goal)
        return node

    leader_info = member_roles.get(leader_id, {}) if leader_id else {}
    tree: dict[str, Any] = {}
    if leader_id:
        tree[leader_id] = _build_node(leader_id, goal=requirements_anchor)

    return {
        "leader_id": leader_id,
        "leader_name": leader_info.get("role_name", "Leader"),
        "tree": tree,
    }


def generate_role_context(
    org_structure: dict[str, Any],
    member_id: str,
) -> str:
    """生成角色上下文字符串，用于 Worker/Supervisor prompt。

    Examples:
        Leader: "你是张总，团队负责人"
        Supervisor: "你是李经理（后端主管），向张总（团队负责人）汇报"
        Worker: "你是小王（后端开发），向李经理（后端主管）汇报"
    """
    if not org_structure:
        return ""

    member_roles = org_structure.get("member_roles", {})
    leader_id = org_structure.get("leader_member_id")

    info = member_roles.get(member_id, {})
    role_name = info.get("role_name", "成员")
    agent_name = info.get("agent_name", role_name)

    is_leader = member_id == leader_id

    if is_leader:
        return f"你是{role_name}，团队负责人"

    # 查上级
    supervisor_id = find_supervisor_for_member(org_structure, member_id)
    sup_info = member_roles.get(supervisor_id, {}) if supervisor_id else {}
    sup_role = sup_info.get("role_name", "上级")

    display = role_name if role_name == agent_name else f"{role_name}（{agent_name}）"
    return f"你是{display}，向{sup_role}汇报"


def find_member_info(
    org_structure: dict[str, Any],
    member_id: str,
) -> dict[str, Any] | None:
    """查找成员信息。

    Returns:
        {role_name, agent_id, agent_name, capabilities, can_delegate} 或 None
    """
    if not org_structure:
        return None

    member_roles = org_structure.get("member_roles", {})
    info = member_roles.get(member_id)
    if not info:
        return None

    return {
        "role_name": info.get("role_name", ""),
        "agent_id": info.get("agent_id"),
        "agent_name": info.get("agent_name", ""),
        "capabilities": info.get("capabilities", []),
        "can_delegate": info.get("can_delegate", True),
    }
