"""组织层级树 — 基于 DB 配置的多级委派、审核和升级链

根据系统架构 v5.0：
- 组织层级从 DB (team_supervisor_configs + team_supervisor_relations) 加载
- 委派树：Leader → Managers → Workers（递归）
- 审核链：沿树上升 → LCA (Lowest Common Ancestor) 审核
- 升级链：沿树上升 → find_escalation_target

数据结构:
    org_structure = {
        "leader_member_id": "leader",
        "relations": [
            {"member_id": "mgr1", "supervisor_member_id": "leader"},
            ...
        ],
        "member_roles": {
            "leader": {"role_name": "张总", "agent_id": "a0", "agent_name": "张总",
                       "capabilities": ["management"]},
            ...
        },
    }

    delegation_tree = {
        "leader_id": "leader",
        "tree": {
            "leader": {
                "member_id": "leader", "role_name": "张总",
                "goal": "...", "role_context": "你是张总...",
                "sub_delegations": {...},
            },
        },
    }
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 1. DB 加载
# ═══════════════════════════════════════════

async def load_org_structure(team_id: str) -> Optional[dict]:
    """从 DB 加载团队的组织层级结构。

    Args:
        team_id: 团队 UUID 字符串

    Returns:
        org_structure dict，无配置则返回 None（扁平模式）
    """
    import uuid as _uuid
    from sqlalchemy import select as _sel

    try:
        from app.core.database import async_session
        from app.models.team_mode_configs import TeamSupervisorConfig, TeamSupervisorRelation
        from app.models.team_member import TeamMember

        tid = _uuid.UUID(team_id)

        async with async_session() as db:
            # 1. 加载 Supervisor 配置
            cfg_result = await db.execute(
                _sel(TeamSupervisorConfig).where(TeamSupervisorConfig.team_id == tid)
            )
            cfg = cfg_result.scalar_one_or_none()
            if not cfg:
                return None  # 无配置 → 扁平模式

            # 2. 加载委派关系
            rel_result = await db.execute(
                _sel(TeamSupervisorRelation).where(TeamSupervisorRelation.team_id == tid)
            )
            relations = []
            for r in rel_result.scalars().all():
                relations.append({
                    "member_id": str(r.member_id),
                    "supervisor_member_id": str(r.supervisor_member_id),
                })

            # 3. 加载成员信息（从 team_members）
            member_result = await db.execute(
                _sel(TeamMember).where(TeamMember.team_id == tid)
            )
            member_roles = {}
            for m in member_result.scalars().all():
                mid = str(m.id)
                member_roles[mid] = {
                    "role_name": m.role_name or "成员",
                    "agent_id": str(m.agent_id) if m.agent_id else "",
                    "agent_name": m.role_name or "成员",
                    "capabilities": list(m.capabilities) if m.capabilities else [],
                }

            if not member_roles:
                return None

            leader_id = str(cfg.leader_member_id) if cfg.leader_member_id else None
            return {
                "leader_member_id": leader_id,
                "relations": relations,
                "member_roles": member_roles,
            }

    except Exception as e:
        logger.warning(f"OrgHierarchy: failed to load org structure: {e}")
        return None


# ═══════════════════════════════════════════
# 2. 委派树构建
# ═══════════════════════════════════════════

def build_delegation_tree(
    org_structure: Optional[dict],
    requirements_anchor: str,
) -> dict:
    """从 org_structure 构建委派树（Route B）。

    Args:
        org_structure: load_org_structure 返回值（None = 扁平模式）
        requirements_anchor: 顶层需求描述

    Returns:
        delegation_tree = {
            "leader_id": str | None,
            "tree": {member_id: tree_node, ...}  (root nodes)
        }
    """
    if not org_structure:
        return {"leader_id": None, "tree": {}}

    leader_id = org_structure.get("leader_member_id")
    member_roles = org_structure.get("member_roles", {})
    relations = org_structure.get("relations", [])

    # 构建 supervisor → [subordinates] 映射
    children_map: dict[str, list[str]] = {}
    for r in relations:
        sup = r["supervisor_member_id"]
        mem = r["member_id"]
        children_map.setdefault(sup, []).append(mem)

    def _build_node(member_id: str, goal: str, depth: int = 0) -> dict:
        """递归构建树节点。"""
        info = member_roles.get(member_id, {})
        role_name = info.get("role_name", "成员")

        node = {
            "member_id": member_id,
            "role_name": role_name,
            "agent_id": info.get("agent_id", ""),
            "agent_name": info.get("agent_name", role_name),
            "capabilities": info.get("capabilities", []),
            "goal": goal,
            "depth": depth,
            "role_context": generate_role_context(org_structure, member_id),
            "sub_delegations": {},
        }

        children = children_map.get(member_id, [])
        child_goal = (
            f"完成 '{role_name}' 委派给你的子任务。"
            f"根据你的角色职责分解并执行。"
        )

        for child_id in children:
            child_node = _build_node(child_id, child_goal, depth + 1)
            node["sub_delegations"][child_id] = child_node

        return node

    tree = {}
    if leader_id and leader_id in member_roles:
        tree[leader_id] = _build_node(leader_id, requirements_anchor)
    else:
        # 无 Leader → 找到所有顶层成员（没有 supervisor 的成员）
        supervised = {r["member_id"] for r in relations}
        roots = [mid for mid in member_roles if mid not in supervised]
        for root_id in roots:
            tree[root_id] = _build_node(root_id, requirements_anchor)

    return {
        "leader_id": leader_id,
        "tree": tree,
    }


# ═══════════════════════════════════════════
# 3. 成员查询
# ═══════════════════════════════════════════

def find_member_info(org_structure: Optional[dict], member_id: str) -> dict:
    """查找成员的详细信息。

    Returns:
        {role_name, agent_id, agent_name, capabilities} 或空 dict
    """
    if not org_structure:
        return None
    return org_structure.get("member_roles", {}).get(member_id) or None


def find_subordinates(org_structure: Optional[dict], member_id: str) -> list[str]:
    """查找直属下属的 member_id 列表。"""
    if not org_structure:
        return []
    relations = org_structure.get("relations", [])
    return [r["member_id"] for r in relations if r["supervisor_member_id"] == member_id]


def find_supervisor_for_member(org_structure: Optional[dict], member_id: str) -> Optional[str]:
    """查找直属上级的 member_id。"""
    if not org_structure:
        return None
    relations = org_structure.get("relations", [])
    for r in relations:
        if r["member_id"] == member_id:
            return r["supervisor_member_id"]
    return None


def _find_chain_to_root(org_structure: dict, member_id: str) -> list[str]:
    """查找从 member_id 到 root (leader) 的完整监督链（含自身）。"""
    chain = [member_id]
    current = member_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        sup = find_supervisor_for_member(org_structure, current)
        if sup:
            chain.append(sup)
            current = sup
        else:
            break
    return chain


def _find_lca(org_structure: dict, member_a: str, member_b: str) -> Optional[str]:
    """找到两个成员在组织树中的最低公共祖先 (Lowest Common Ancestor)。"""
    chain_a = _find_chain_to_root(org_structure, member_a)
    chain_b = set(_find_chain_to_root(org_structure, member_b))
    for mid in chain_a:
        if mid in chain_b:
            return mid
    return None


# ═══════════════════════════════════════════
# 4. 角色上下文生成
# ═══════════════════════════════════════════

def generate_role_context(org_structure: Optional[dict], member_id: str) -> str:
    """为指定成员生成角色上下文描述。

    用于注入到 Agent 的 Prompt 中，告知其在组织中的位置。
    """
    if not org_structure:
        return ""

    info = find_member_info(org_structure, member_id)
    role_name = info.get("role_name", "成员")
    capabilities = info.get("capabilities", [])
    cap_text = "、".join(capabilities) if capabilities else "通用任务"

    # 下属信息
    subs = find_subordinates(org_structure, member_id)
    sub_names = []
    for sid in subs:
        si = find_member_info(org_structure, sid)
        sub_names.append(si.get("role_name", sid))

    # 上级信息
    supervisor_id = find_supervisor_for_member(org_structure, member_id)
    sup_name = ""
    if supervisor_id:
        si = find_member_info(org_structure, supervisor_id)
        sup_name = si.get("role_name", "")

    parts = [f"你是 **{role_name}**，负责 **{cap_text}** 相关任务。"]

    if sup_name:
        parts.append(f"你的上级是 **{sup_name}**，需要向 TA 汇报工作进展。")

    if sub_names:
        if len(sub_names) == 1:
            parts.append(f"你的下属是 **{sub_names[0]}**，可以向 TA 分配子任务。")
        else:
            names = "、".join(sub_names)
            parts.append(f"你的下属包括 **{names}**，可以向他们分配子任务。")

    # 是否是 Leader
    leader_id = org_structure.get("leader_member_id")
    if member_id == leader_id:
        parts.append("你是团队负责人，拥有最终决策权。")

    return " ".join(parts)


# ═══════════════════════════════════════════
# 5. 审核 & 升级
# ═══════════════════════════════════════════

def find_reviewer_for_level(
    org_structure: Optional[dict],
    member_id: str,
    level: int = 1,
) -> Optional[str]:
    """为指定成员找到第 N 级审核人。

    level=1: 直属上级审核
    level=2: 上级的上级审核（LCA）
    """
    if not org_structure:
        return None

    current = member_id
    for _ in range(level):
        sup = find_supervisor_for_member(org_structure, current)
        if not sup:
            return None
        current = sup
    return current


def find_escalation_target(
    org_structure: Optional[dict],
    member_id: str,
) -> Optional[dict]:
    """沿组织树向上查找升级目标。

    Returns:
        {target_id, target_name, level} or None
    """
    if not org_structure:
        return None

    sup_id = find_supervisor_for_member(org_structure, member_id)
    if not sup_id:
        # 已经是顶层 → 升级到 Leader（如果自己是 Leader 则返回 None）
        leader_id = org_structure.get("leader_member_id")
        if leader_id and leader_id != member_id:
            info = find_member_info(org_structure, leader_id)
            return {
                "target_id": leader_id,
                "target_name": info.get("role_name", "Leader"),
                "level": 1,
            }
        return None

    info = find_member_info(org_structure, sup_id)
    return {
        "target_id": sup_id,
        "target_name": info.get("role_name", "上级"),
        "level": 1,
    }


# ═══════════════════════════════════════════
# 6. 格式化输出
# ═══════════════════════════════════════════

def format_org_tree_desc(org_structure: Optional[dict]) -> str:
    """将组织树格式化为文本描述，用于注入 Prompt。"""
    if not org_structure:
        return "扁平团队（无层级结构）"

    leader_id = org_structure.get("leader_member_id")
    member_roles = org_structure.get("member_roles", {})
    relations = org_structure.get("relations", [])

    # 构建 supervisor → [subordinates] 映射
    children_map: dict[str, list[str]] = {}
    for r in relations:
        sup = r["supervisor_member_id"]
        mem = r["member_id"]
        children_map.setdefault(sup, []).append(mem)

    lines = []
    _indent = "  "

    def _render(member_id: str, indent: int = 0):
        info = member_roles.get(member_id, {})
        role_name = info.get("role_name", "成员")
        cap = info.get("capabilities", [])
        cap_str = f" ({', '.join(cap)})" if cap else ""
        prefix = _indent * indent
        lines.append(f"{prefix}- {role_name}{cap_str}")
        for child_id in children_map.get(member_id, []):
            _render(child_id, indent + 1)

    if leader_id and leader_id in member_roles:
        _render(leader_id)
    else:
        # 找顶层成员
        supervised = {r["member_id"] for r in relations}
        roots = [mid for mid in member_roles if mid not in supervised]
        for root_id in roots:
            _render(root_id)

    return "\n".join(lines)
