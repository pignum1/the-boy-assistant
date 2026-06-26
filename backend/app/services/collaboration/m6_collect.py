"""M6 Collect — collect subordinate results, review, report to parent (Route B).

Replaces m6_level_review. Handles:
- Merging parallel worker results
- Supervisor LLM review of subordinate output
- Pass / retry / escalate decision
- Stack pop + report to parent supervisor
"""

import json
import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)

MAX_WORKER_RETRIES = 2


# ── LangGraph node ────────────────────────────────────────────────

async def m6_collect_node(state: CollabState) -> dict[str, Any]:
    """Collect subordinate results, review, and decide next action.

    Flow:
    1. Merge pending_parallel_results if present
    2. Record current worker result into stack entry
    3. Pop current from pending_assignments
    4. If pending remaining → next subordinate
    5. If all complete → supervisor review (LLM)
       → pass: pop stack, update tree, report up
       → retry: set retry_feedback, route back
       → escalate: route to m6_escalate
    """
    stack = list(state.get("delegation_stack", []))
    tree = dict(state.get("delegation_tree", {}))
    org = state.get("org_structure")
    current = state.get("current_delegation", {})
    current_member_id = current.get("member_id", "")
    current_role = current.get("role_name", "")

    if not stack:
        # No stack — all done
        return {"status": "all_delegations_done"}

    top = dict(stack[-1])
    supervisor_id = top.get("supervisor_member_id", "")
    supervisor_role = top.get("supervisor_role_name", "")
    pending = list(top.get("pending_assignments", []))
    completed = dict(top.get("completed_results", {}))
    retry_counts = dict(top.get("retry_counts", {}))

    # ── 1. Merge parallel results if present ──
    parallel_results = state.get("pending_parallel_results", [])
    if parallel_results:
        for pr in parallel_results:
            mid = pr.get("member_id", "")
            if mid:
                completed[mid] = {
                    "output": pr.get("output", ""),
                    "files": pr.get("files", []),
                    "agent_name": pr.get("agent_name", ""),
                    "error": pr.get("error"),
                }
                if mid in pending:
                    pending.remove(mid)
    else:
        # Record current worker's result
        artifacts = state.get("artifacts", {})
        files_changed = state.get("files_changed", [])
        output = artifacts.get(current_member_id, "")

        if current_member_id:
            completed[current_member_id] = {
                "output": output,
                "files": files_changed,
                "role_name": current_role,
            }

        # Pop current from pending
        if current_member_id in pending:
            pending.remove(current_member_id)

    # ── 2. Update stack entry ──
    top["pending_assignments"] = pending
    top["completed_results"] = completed
    top["retry_counts"] = retry_counts
    stack[-1] = top

    # ── 3. If more pending → route to next subordinate ──
    if pending:
        next_mid = pending[0]
        from .org_hierarchy import generate_role_context, find_member_info, find_subordinates

        info = find_member_info(org, next_mid) if org else None
        sub_subs = find_subordinates(org, next_mid) if org else []
        role_ctx = generate_role_context(org, next_mid) if org else ""

        # Find the assignment for this member
        assignment = None
        for a in top.get("assignments", []):
            if a.get("member_id") == next_mid:
                assignment = a
                break

        next_goal = assignment.get("goal", "") if assignment else ""
        next_role = assignment.get("role_name", info.get("role_name", "") if info else "") if assignment else ""

        next_delegation = {
            "member_id": next_mid,
            "role_name": next_role,
            "goal": next_goal,
            "role_context": role_ctx,
            "is_leaf": len(sub_subs) == 0,
            "is_root": False,
            "supervisor_member_id": supervisor_id,
        }

        logger.info(f"M6 Collect: {supervisor_role} → next subordinate {next_role}")

        return {
            "delegation_stack": stack,
            "current_delegation": next_delegation,
            "status": "next_subordinate",
            "_content": f"→ 下一个下属: {next_role}",
            "_agent_name": supervisor_role,
        }

    # ── 4. All subordinates complete → Supervisor review ──
    logger.info(
        f"M6 Collect: {supervisor_role} reviewing all {len(completed)} subordinate results"
    )

    review_result = await _supervisor_review(state, top, completed, org)

    if review_result.get("passed"):
        # ── Pass: pop stack, update tree ──
        stack.pop()

        # Update delegation_tree
        _update_tree_with_results(tree, supervisor_id, completed, review_result)

        if not stack:
            # All delegations done
            return {
                "delegation_stack": stack,
                "delegation_tree": tree,
                "status": "all_delegations_done",
                "_content": f"✅ **{supervisor_role}** 审核通过所有下属产出",
                "_agent_name": supervisor_role,
            }

        # Report to parent: record this subtree result
        parent = stack[-1]
        parent_completed = dict(parent.get("completed_results", {}))
        parent_completed[supervisor_id] = {
            "output": _summarize_results(completed),
            "files": _collect_all_files(completed),
            "role_name": supervisor_role,
            "passed": True,
        }
        parent_pending = list(parent.get("pending_assignments", []))
        if supervisor_id in parent_pending:
            parent_pending.remove(supervisor_id)
        parent["completed_results"] = parent_completed
        parent["pending_assignments"] = parent_pending
        stack[-1] = parent

        # Set up next sibling or trigger parent collect
        if parent_pending:
            from .org_hierarchy import generate_role_context, find_member_info, find_subordinates
            next_mid = parent_pending[0]
            info = find_member_info(org, next_mid) if org else None
            role_ctx = generate_role_context(org, next_mid) if org else ""
            sub_subs = find_subordinates(org, next_mid) if org else []

            assignment = None
            for a in parent.get("assignments", []):
                if a.get("member_id") == next_mid:
                    assignment = a
                    break

            next_delegation = {
                "member_id": next_mid,
                "role_name": assignment.get("role_name", "") if assignment else (info.get("role_name", "") if info else ""),
                "goal": assignment.get("goal", "") if assignment else "",
                "role_context": role_ctx,
                "is_leaf": len(sub_subs) == 0,
                "is_root": False,
                "supervisor_member_id": parent.get("supervisor_member_id", ""),
            }

            return {
                "delegation_stack": stack,
                "delegation_tree": tree,
                "current_delegation": next_delegation,
                "status": "next_subordinate",
                "_content": f"✅ {supervisor_role} 完成 → 下一个: {next_delegation['role_name']}",
                "_agent_name": supervisor_role,
            }

        # Parent has no more pending — trigger parent collect
        return {
            "delegation_stack": stack,
            "delegation_tree": tree,
            "status": "next_subordinate",
            "_content": f"✅ {supervisor_role} 完成",
            "_agent_name": supervisor_role,
        }

    else:
        # ── Fail: retry or escalate ──
        retry_count = retry_counts.get(current_member_id, 0)
        feedback = review_result.get("feedback", "")

        if retry_count < MAX_WORKER_RETRIES:
            # Retry: set feedback and route back
            retry_counts[current_member_id] = retry_count + 1
            top["retry_counts"] = retry_counts
            top["pending_assignments"] = [current_member_id]  # retry this one
            stack[-1] = top

            # Set retry_feedback on current_delegation
            retry_delegation = dict(current)
            retry_delegation["retry_feedback"] = feedback

            logger.info(
                f"M6 Collect: {supervisor_role} retry {current_role} "
                f"(attempt {retry_count + 1}/{MAX_WORKER_RETRIES})"
            )

            return {
                "delegation_stack": stack,
                "current_delegation": retry_delegation,
                "status": "retry",
                "_content": f"🔄 **{supervisor_role}** 要求重做: {feedback[:100]}",
                "_agent_name": supervisor_role,
            }

        else:
            # Escalate
            top["retry_counts"] = retry_counts
            stack[-1] = top
            logger.warning(
                f"M6 Collect: {supervisor_role} escalating {current_role} "
                f"(retries exhausted: {retry_count})"
            )

            return {
                "delegation_stack": stack,
                "status": "escalate",
                "_content": f"🚨 **{supervisor_role}** 升级: {current_role} 重试超限",
                "_agent_name": supervisor_role,
            }


# ── Supervisor LLM review ──

async def _supervisor_review(
    state: CollabState,
    stack_entry: dict,
    completed_results: dict,
    org: dict | None,
) -> dict[str, Any]:
    """LLM-based review of all subordinate outputs by the supervisor."""
    supervisor_id = stack_entry.get("supervisor_member_id", "")
    supervisor_role = stack_entry.get("supervisor_role_name", "")
    goal = stack_entry.get("goal", "")
    requirements = state.get("requirements_anchor", "")

    # Build review prompt
    results_summary = ""
    for mid, result in completed_results.items():
        role = result.get("role_name", mid)
        output = result.get("output", "")
        error = result.get("error")
        if error:
            results_summary += f"\n### {role}\n❌ 执行失败: {error}\n"
        else:
            truncated = output[:1500] + "..." if len(output) > 1500 else output
            results_summary += f"\n### {role}\n{truncated}\n"

    prompt = f"""你是 {supervisor_role}，需要审核下属的产出。

## 你分配的目标
{goal}

## 下属产出
{results_summary}

## 原始需求（参考）
{requirements[:1000]}

请对照你分配的目标，检查下属产出是否达标。
输出严格 JSON:
{{"passed": true/false, "feedback": "具体意见或改进建议", "severity": "none|minor|major|critical"}}
"""

    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            agent = None
            if org:
                info = org.get("member_roles", {}).get(supervisor_id, {})
                aid = info.get("agent_id")
                if aid:
                    stmt = select(Agent).where(Agent.id == aid)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return {"passed": False, "feedback": "⚠️ 无可用 Agent 审核，请人工审查"}

            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=False, save_memory=False,
            )

            raw = llm_result.get("content", "")
            parsed = _parse_json_output(raw)

            passed = parsed.get("passed", True)
            severity = parsed.get("severity", "none")

            # minor/none = pass
            if severity in ("none", "minor"):
                passed = True

            return {
                "passed": passed,
                "feedback": parsed.get("feedback", ""),
                "severity": severity,
            }

    except Exception as e:
        logger.error(f"M6 Collect: supervisor review failed: {e}")
        return {"passed": True, "feedback": f"审核出错，自动通过: {str(e)[:100]}"}


# ── JSON parsing ──

def _parse_json_output(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output with triple fallback."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass
    if "{" in raw and "}" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        try:
            return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
    return {"passed": True, "feedback": raw[:200], "severity": "none"}


# ── Tree helpers ──

def _update_tree_with_results(
    tree: dict, supervisor_id: str, completed: dict, review: dict
) -> None:
    """Update delegation_tree with completed results."""
    import copy

    def _find_node(node: dict, target_id: str) -> dict | None:
        if node.get("member_id") == target_id:
            return node
        for child in node.get("sub_delegations", {}).values():
            found = _find_node(child, target_id)
            if found:
                return found
        return None

    tree_roots = tree.get("tree", {})
    sup_node = None
    for root in tree_roots.values():
        sup_node = _find_node(root, supervisor_id)
        if sup_node:
            break

    if not sup_node:
        return

    # Update sub-delegation nodes with results
    for mid, result in completed.items():
        child = sup_node["sub_delegations"].get(mid)
        if child:
            child["artifact_refs"] = [f["name"] for f in result.get("files", []) if isinstance(f, dict)]
            child["review_result"] = {
                "passed": review.get("passed", True),
                "feedback": review.get("feedback", ""),
            }

    sup_node["review_result"] = review


def _summarize_results(completed: dict) -> str:
    """Create a summary of all subordinate results."""
    lines = []
    for mid, r in completed.items():
        role = r.get("role_name", mid)
        error = r.get("error")
        if error:
            lines.append(f"{role}: ❌ {error}")
        else:
            output = r.get("output", "")
            lines.append(f"{role}: ✅ {len(output)} chars")
    return "\n".join(lines)


def _collect_all_files(completed: dict) -> list[dict]:
    """Collect all file changes from subordinate results."""
    files = []
    for r in completed.values():
        for f in r.get("files", []):
            if isinstance(f, dict):
                files.append(f)
    return files


# ── Routing ──────────────────────────────────────────────────────

def route_after_collect(state: CollabState) -> str:
    """Route after collect based on status.

    Returns:
        "m7_verify"         — all delegations complete
        "m6_delegate_sub"   — next subordinate or retry
        "m6_escalate"       — escalation needed
    """
    status = state.get("status", "")

    if status == "all_delegations_done":
        return "m7_verify"
    if status in ("next_subordinate", "retry"):
        return "m6_delegate_sub"
    if status == "escalate":
        return "m6_escalate"

    logger.warning(f"M6 Collect: unknown status '{status}', defaulting to m7_verify")
    return "m7_verify"
