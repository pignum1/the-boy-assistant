"""M6 Plan Validate — validates LLM delegation plans before execution.

Safety net: catches member hallucination, resource conflicts,
skill mismatches, task fragmentation, goal coverage gaps.

Also contains m6_delegate_push_node (pure routing, no LLM/DB).
"""

import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── Delegation Plan Validator ─────────────────────────────────────

class DelegationPlanValidator:
    """Validates delegation plans produced by supervisor LLM.

    Five validation rules:
    1. member_exists  — assignment targets are real subordinates
    2. goal_coverage  — assignments cover the original goal keywords
    3. skill_match    — assignments match member capabilities
    4. resource_conflict — no duplicate member assignments
    5. granularity    — not too many micro-tasks
    """

    MAX_VALIDATION_RETRIES = 2

    def validate(
        self,
        plan: dict[str, Any],
        goal: str,
        subordinate_ids: list[str],
        org_structure: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate a delegation plan.

        Returns:
            {"valid": bool, "issues": [...], "fixed_plan": dict | None}
        """
        assignments = plan.get("assignments", [])
        issues = []
        valid_sub_ids = set(subordinate_ids)

        # ── 0. Normalize member_id: LLM 常用角色名(architect/pm)而非真实 UUID ──
        # 建立角色名/角色ID → 真实 member_id 的映射，提前修正，避免误判为非法成员。
        from .org_hierarchy import find_member_info
        role_to_id: dict[str, str] = {}
        for sid in subordinate_ids:
            info = find_member_info(org_structure, sid) or {}
            for key in ("role_name", "role_id", "agent_name"):
                val = (info.get(key) or "").strip()
                if val:
                    role_to_id[val.lower()] = sid
        for a in assignments:
            mid = (a.get("member_id") or "").strip()
            if mid and mid not in valid_sub_ids:
                resolved = role_to_id.get(mid.lower())
                if resolved:
                    a["member_id"] = resolved
                    if "role_name" not in a:
                        a["role_name"] = (find_member_info(org_structure, resolved) or {}).get("role_name", mid)

        # 1. Member existence check
        for a in assignments:
            mid = a.get("member_id", "")
            if mid and mid not in valid_sub_ids:
                issues.append({
                    "rule": "member_exists",
                    "severity": "critical",
                    "detail": f"成员 {mid} 不在下属列表 {valid_sub_ids} 中",
                })

        # 2. Goal coverage check (keyword overlap)
        goal_kw = set(self._extract_keywords(goal))
        covered_kw = set()
        for a in assignments:
            covered_kw.update(self._extract_keywords(a.get("goal", "")))
        uncovered = goal_kw - covered_kw
        if uncovered and len(assignments) > 1:
            issues.append({
                "rule": "goal_coverage",
                "severity": "major",
                "detail": f"以下目标关键词未被覆盖: {uncovered}",
            })

        # 3. Skill match (minor warning)
        from .org_hierarchy import find_member_info
        for a in assignments:
            mid = a.get("member_id", "")
            if mid in valid_sub_ids:
                info = find_member_info(org_structure, mid)
                if info and info.get("capabilities"):
                    caps = [c.lower() for c in info["capabilities"]]
                    goal_text = a.get("goal", "").lower()
                    if not any(c in goal_text for c in caps if len(c) > 1):
                        issues.append({
                            "rule": "skill_match",
                            "severity": "minor",
                            "detail": f"{mid} 的技能 {info['capabilities']} 可能不匹配: {a.get('goal', '')[:50]}",
                        })

        # 4. Resource conflict (same member assigned twice)
        member_counts: dict[str, int] = {}
        for a in assignments:
            mid = a.get("member_id", "")
            member_counts[mid] = member_counts.get(mid, 0) + 1
        for mid, count in member_counts.items():
            if count > 1:
                issues.append({
                    "rule": "resource_conflict",
                    "severity": "critical",
                    "detail": f"成员 {mid} 被分配了 {count} 个并行任务",
                })

        # 5. Granularity check
        if len(assignments) > len(subordinate_ids) * 2:
            issues.append({
                "rule": "granularity",
                "severity": "minor",
                "detail": f"任务数 ({len(assignments)}) 远超下属数 ({len(subordinate_ids)})",
            })

        critical = [i for i in issues if i["severity"] == "critical"]
        fixed = self._try_auto_fix(plan, issues) if critical else None

        return {
            "valid": len(critical) == 0,
            "issues": issues,
            "fixed_plan": fixed,
        }

    def _try_auto_fix(self, plan: dict, issues: list[dict]) -> dict | None:
        """Try to auto-fix critical issues (remove hallucinated members)."""
        # Collect bad member_ids directly from assignments not in valid set
        bad_members = set()
        for i in issues:
            if i["rule"] == "member_exists":
                # Extract from detail format: "成员 {mid} 不在下属列表 ..."
                detail = i.get("detail", "")
                # Pattern: "成员 XXX 不在" — find the word after "成员"
                parts = detail.split()
                for idx, word in enumerate(parts):
                    if word == "成员" and idx + 1 < len(parts):
                        bad_members.add(parts[idx + 1])
                    elif word.startswith("成员") and len(word) > 2:
                        # Handle no-space case: "成员FAKE"
                        bad_members.add(word[2:])

        if not bad_members:
            return None

        fixed_assignments = [
            a for a in plan.get("assignments", [])
            if a.get("member_id", "") not in bad_members
        ]

        if not fixed_assignments:
            return None

        return {"assignments": fixed_assignments, "reasoning": plan.get("reasoning", "")}

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text (simple approach)."""
        # Remove common stop words and short chars
        stop = {"的", "了", "在", "是", "和", "与", "或", "及", "等", "中",
                "对", "将", "于", "从", "到", "为", "以", "及", "并", "其",
                "a", "an", "the", "is", "are", "was", "in", "on", "at",
                "to", "for", "of", "with", "and", "or", "but"}
        words = text.replace(",", " ").replace("。", " ").replace(".", " ").split()
        return [w for w in words if len(w) > 1 and w not in stop]


# ── Singleton validator ──
_validator = DelegationPlanValidator()

# Track validation retry count per delegation
_validation_retry_counts: dict[str, int] = {}


# ── LangGraph node ────────────────────────────────────────────────

async def m6_plan_validate_node(state: CollabState) -> dict[str, Any]:
    """Validate delegation_plan from m6_delegate.

    Checks:
    1. All assigned members exist in org tree
    2. Goal is covered by assignments
    3. No resource conflicts
    4. Auto-fixes if possible

    Routes:
    - approved → m6_delegate_push
    - rejected → m6_delegate_root (retry with feedback)
    - fallback → m6_delegate_push (algorithmic plan)
    """
    plan = state.get("delegation_plan", {})
    current = state.get("current_delegation", {})
    org = state.get("org_structure")
    member_id = current.get("member_id", "")
    goal = current.get("goal", "")

    from .org_hierarchy import find_subordinates

    subordinate_ids = find_subordinates(org, member_id) if org else []
    assignments = plan.get("assignments", [])

    # ── Empty plan ──
    if not assignments:
        logger.warning(f"M6 PlanValidate: empty plan from {member_id}")
        return _fallback_plan(state, goal, subordinate_ids, org)

    # ── Validate ──
    result = _validator.validate(plan, goal, subordinate_ids, org or {})

    if result["valid"]:
        logger.info(f"M6 PlanValidate: plan approved ({len(assignments)} assignments)")
        _validation_retry_counts.pop(member_id, None)  # reset
        return {
            "_validation_result": "approved",
            "_validation_issues": result.get("issues", []),
            "_content": f"✅ 委派计划已通过验证",
            "_agent_name": current.get("role_name", "Supervisor"),
        }

    # ── Try auto-fix ──
    if result.get("fixed_plan"):
        logger.info(f"M6 PlanValidate: auto-fixed plan for {member_id}")
        _validation_retry_counts.pop(member_id, None)
        return {
            "_validation_result": "approved",
            "delegation_plan": result["fixed_plan"],
            "_validation_issues": result.get("issues", []),
            "_content": f"⚠️ 委派计划已自动修复",
            "_agent_name": current.get("role_name", "Supervisor"),
        }

    # ── Retry or fallback ──
    retry_count = _validation_retry_counts.get(member_id, 0) + 1
    _validation_retry_counts[member_id] = retry_count

    if retry_count >= _validator.MAX_VALIDATION_RETRIES:
        logger.warning(
            f"M6 PlanValidate: max retries ({retry_count}) for {member_id}, "
            f"using algorithmic fallback"
        )
        _validation_retry_counts.pop(member_id, None)
        return _fallback_plan(state, goal, subordinate_ids, org)

    issues_detail = "; ".join(i["detail"] for i in result.get("issues", []))
    logger.info(f"M6 PlanValidate: rejected (retry {retry_count}): {issues_detail}")

    return {
        "_validation_result": "rejected",
        "_validation_issues": result.get("issues", []),
        "_content": f"⚠️ 委派计划验证失败 (重试 {retry_count}/{_validator.MAX_VALIDATION_RETRIES}): {issues_detail}",
        "_agent_name": "委派验证",
    }


def _fallback_plan(
    state: CollabState,
    goal: str,
    subordinate_ids: list[str],
    org: dict | None,
) -> dict[str, Any]:
    """Generate algorithmic fallback plan."""
    from .m6_delegate import _algorithmic_decompose_fallback

    result = _algorithmic_decompose_fallback(goal, subordinate_ids, org or {})
    return {
        "_validation_result": "approved",
        "delegation_plan": result.get("delegation_plan", {}),
        "_content": result.get("_content", "📋 算法分配"),
        "_agent_name": "系统",
    }


# ── Delegate Push node (pure routing, no LLM/DB) ─────────────────

def m6_delegate_push_node(state: CollabState) -> dict[str, Any]:
    """Push delegation plan onto stack and set up next subordinate.

    Pure routing node — no LLM calls, no DB queries.
    Reads the validated delegation_plan, creates a DelegationEntry,
    pushes onto delegation_stack, and sets current_delegation.
    """
    plan = state.get("delegation_plan", {})
    current = state.get("current_delegation", {})
    stack = list(state.get("delegation_stack", []))
    tree = state.get("delegation_tree", {})
    org = state.get("org_structure")

    assignments = plan.get("assignments", [])
    if not assignments:
        logger.warning("M6 DelegatePush: no assignments in plan")
        return {
            "status": "blocked",
            "_content": "❌ 委派计划为空",
            "_agent_name": "调度器",
        }

    supervisor_member_id = current.get("member_id", "")
    supervisor_role_name = current.get("role_name", "")
    goal = current.get("goal", "")

    # ── Build pending_assignments list ──
    pending_ids = [a["member_id"] for a in assignments]

    # ── Create DelegationEntry ──
    entry = {
        "supervisor_member_id": supervisor_member_id,
        "supervisor_role_name": supervisor_role_name,
        "goal": goal,
        "assignments": assignments,
        "pending_assignments": pending_ids,
        "completed_results": {},
        "retry_counts": {},
    }

    stack.append(entry)

    # ── Update delegation_tree sub_delegations ──
    tree_updated = _deep_copy_tree(tree)
    _update_tree_sub_delegations(tree_updated, supervisor_member_id, assignments, org)

    # ── Set current_delegation to first pending ──
    first_assignment = assignments[0]
    from .org_hierarchy import generate_role_context, find_member_info

    role_ctx = generate_role_context(org, first_assignment["member_id"]) if org else ""
    info = find_member_info(org, first_assignment["member_id"]) if org else None

    new_current = {
        "member_id": first_assignment["member_id"],
        "role_name": first_assignment.get("role_name", info.get("role_name", "") if info else ""),
        "goal": first_assignment.get("goal", ""),
        "role_context": role_ctx,
        "is_leaf": first_assignment.get("is_leaf", True),
        "is_root": False,
        "supervisor_member_id": supervisor_member_id,
    }

    logger.info(
        f"M6 DelegatePush: {supervisor_role_name} → "
        f"{len(assignments)} subordinates, first: {first_assignment.get('role_name', '?')}"
    )

    return {
        "delegation_stack": stack,
        "delegation_tree": tree_updated,
        "current_delegation": new_current,
        "delegation_depth": len(stack),
        "delegation_plan": None,  # consumed
        "_content": f"📤 压栈: {supervisor_role_name} 委派给 {len(assignments)} 个下属",
        "_agent_name": supervisor_role_name,
    }


def _deep_copy_tree(tree: dict) -> dict:
    """Deep copy delegation tree to avoid mutating state."""
    import copy
    return copy.deepcopy(tree)


def _update_tree_sub_delegations(
    tree: dict,
    supervisor_member_id: str,
    assignments: list[dict],
    org: dict | None,
) -> None:
    """Update delegation_tree with new sub_delegations for a supervisor."""
    from .org_hierarchy import find_member_info, find_subordinates

    # Find the supervisor node in tree
    def _find_node(node: dict, target_id: str) -> dict | None:
        if node.get("member_id") == target_id:
            return node
        for child in node.get("sub_delegations", {}).values():
            found = _find_node(child, target_id)
            if found:
                return found
        return None

    # Search in all tree roots
    tree_roots = tree.get("tree", {})
    supervisor_node = None
    for root in tree_roots.values():
        supervisor_node = _find_node(root, supervisor_member_id)
        if supervisor_node:
            break

    if not supervisor_node:
        logger.warning(f"M6 DelegatePush: could not find node for {supervisor_member_id}")
        return

    # Add sub_delegations
    for a in assignments:
        mid = a.get("member_id", "")
        info = find_member_info(org, mid) if org else None
        sub_subs = find_subordinates(org, mid) if org else []

        supervisor_node["sub_delegations"][mid] = {
            "member_id": mid,
            "role_name": a.get("role_name", info.get("role_name", "") if info else ""),
            "agent_id": info.get("agent_id") if info else None,
            "goal": a.get("goal", ""),
            "role_context": "",
            "artifact_refs": [],
            "review_result": None,
            "sub_delegations": {},
        }


# ── Routing ──────────────────────────────────────────────────────

def route_after_validate(state: CollabState) -> str:
    """Route after plan validation.

    Returns:
        "m6_delegate_push" — approved/fallback, push plan onto stack
        "m6_delegate_root" — rejected, retry decomposition
    """
    result = state.get("_validation_result", "")

    if result in ("approved", "fallback"):
        return "m6_delegate_push"

    # rejected → retry (re-enter delegate_root which re-thinks)
    return "m6_delegate_root"
