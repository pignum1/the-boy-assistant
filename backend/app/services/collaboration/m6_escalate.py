"""M6 Escalate — walk up the org tree when a level fails review.

When a level's review fails and retries are exhausted, this node:
1. Finds the escalation target (supervisor of the current reviewer)
2. If target exists → calls LLM as that supervisor for guidance → retry with guidance
3. If no more supervisors (at top) → triggers HITL for human decision

Escalation is capped at 3 levels upward to prevent infinite chains.
"""

import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)

MAX_ESCALATION_DEPTH = 3


async def m6_escalate_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: escalate a level failure up the org hierarchy.

    Reads current state and either:
    - Routes to the supervisor's guidance (retry with new instructions)
    - Routes to HITL (no more supervisors, human must decide)
    - Routes to m1_rebalance (critical divergence, need replanning)
    """
    org_structure = state.get("org_structure")
    execution_levels = state.get("execution_levels", [])
    current_level = state.get("current_level", 0)
    level_results = state.get("level_results", [])
    escalation_history = list(state.get("escalation_history", []))
    requirements_anchor = state.get("requirements_anchor", "")

    # ── Find current reviewer ──
    from .org_hierarchy import find_reviewer_for_level, find_escalation_target

    level_tasks = execution_levels[current_level] if current_level < len(execution_levels) else []
    agent_assignments = state.get("agent_assignments", {})
    current_reviewer = find_reviewer_for_level(org_structure, level_tasks, agent_assignments)

    current_reviewer_id = current_reviewer.get("member_id") if current_reviewer else None
    current_reviewer_name = current_reviewer.get("role_name", "审核员") if current_reviewer else "审核员"

    # ── Check escalation depth ──
    if len(escalation_history) >= MAX_ESCALATION_DEPTH:
        logger.warning(
            f"M6 Escalate: max depth {MAX_ESCALATION_DEPTH} reached, routing to HITL"
        )
        return _hitl_escalation(state, current_level, current_reviewer_name, escalation_history)

    # ── Find next supervisor up the chain ──
    if current_reviewer_id:
        escalation_target = find_escalation_target(org_structure, current_reviewer_id)
    else:
        escalation_target = None

    if not escalation_target:
        # No more supervisors → HITL
        logger.info(
            f"M6 Escalate: no more supervisors above {current_reviewer_name}, routing to HITL"
        )
        return _hitl_escalation(state, current_level, current_reviewer_name, escalation_history)

    target_name = escalation_target.get("role_name", "上级")

    # ── Get current level's problem summary ──
    level_problem = ""
    for lr in level_results:
        if lr.get("level_idx") == current_level:
            errors = [
                f"  - {tid}: {tr.get('error', 'failed')}"
                for tid, tr in lr.get("task_results", {}).items()
                if tr.get("status") in ("failed", "error")
            ]
            level_problem = (
                f"Level {current_level} 执行结果: "
                f"{lr.get('error_count', 0)}/{lr.get('total_count', 0)} 个任务失败"
            )
            if errors:
                level_problem += "\n" + "\n".join(errors)
            break

    # ── Call escalated supervisor's LLM for guidance ──
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            # Try to use the escalation target's specific agent
            target_agent_id = escalation_target.get("agent_id")
            agent = None
            if target_agent_id:
                stmt = select(Agent).where(Agent.id == target_agent_id)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return _hitl_escalation(state, current_level, current_reviewer_name, escalation_history)

            guidance_prompt = f"""你是 {target_name}，你的下属 {current_reviewer_name} 负责的 Level {current_level} 任务执行遇到了问题。

## 原始需求
{requirements_anchor[:2000]}

## 问题摘要
{level_problem or "审核不通过，已达到重试上限"}

## 已升级历史
{_format_escalation_history(escalation_history)}

请以 {target_name} 的身份给出指导意见。你可以：
1. 给出具体的修改方向 → 让下属重做
2. 判断这个问题需要重新规划 → 建议 replan
3. 如果问题无法在下属层面解决 → 继续向上汇报

请简短回答，输出 JSON:
{{"action": "retry_with_guidance" | "replan" | "escalate_again",
 "guidance": "你的具体指导意见",
 "reason": "做出此决策的原因"}}"""

            llm_result = await agent_chat(
                db=db, agent=agent, message=guidance_prompt,
                return_reasoning=False, save_memory=False,
            )

            raw = llm_result.get("content", "")
            decision = _parse_escalation_decision(raw)

            action = decision.get("action", "retry_with_guidance")
            guidance = decision.get("guidance", "")
            reason = decision.get("reason", "")

            logger.info(
                f"M6 Escalate: {current_reviewer_name} → {target_name} — "
                f"action={action}"
            )

            escalation_history.append({
                "level_idx": current_level,
                "from_member_id": current_reviewer_id,
                "to_member_id": escalation_target["member_id"],
                "from_name": current_reviewer_name,
                "to_name": target_name,
                "guidance": guidance,
                "action": action,
            })

    except Exception as e:
        logger.error(f"M6 Escalate: LLM call failed: {e}")
        return _hitl_escalation(state, current_level, current_reviewer_name, escalation_history)

    # ── Route based on decision ──
    if action == "replan":
        return {
            "escalation_history": escalation_history,
            "interrupt_message": f"Level {current_level} 升级至 {target_name}，决定: 需要重新规划 — {reason}",
            "interrupt_mode": "soft",
            "status": "replan",
            "_content": f"📢 **升级至 {target_name}**: 决定重新规划 — {reason}",
            "_agent_name": "升级处理",
        }

    if action == "escalate_again":
        return {
            "escalation_history": escalation_history,
            "status": "escalate_again",
            "_content": f"📢 **{target_name}** 决定: 继续向上汇报 — {reason}",
            "_agent_name": "升级处理",
        }

    # Default: retry with guidance
    return {
        "escalation_history": escalation_history,
        "status": "retry_with_guidance",
        "_content": f"📢 **升级至 {target_name}**: {guidance or '请重试当前阶段'}",
        "_agent_name": "升级处理",
    }


# ── Routing ──

def route_after_escalate(state: CollabState) -> str:
    """Route after escalation based on the decision.

    Returns:
        "m6_level_execute" — retry with supervisor guidance
        "m1_rebalance" — critical divergence, need replanning
        "hitl" — no more supervisors, human must decide
    """
    status = state.get("status", "")

    if status == "replan":
        return "m1_rebalance"

    if status == "escalate_again":
        # Try to escalate again (will re-enter m6_escalate which will find next supervisor)
        # But first check depth to prevent infinite loops
        escalation_history = state.get("escalation_history", [])
        if len(escalation_history) >= MAX_ESCALATION_DEPTH:
            return "hitl"
        return "m6_escalate"

    # retry_with_guidance or unknown → re-enter delegation
    return "m6_delegate_sub"


# ── Helpers ──

def _parse_escalation_decision(raw: str) -> dict[str, Any]:
    """Parse escalation supervisor LLM output."""
    import json

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
        except json.JSONDecodeError:
            pass

    # Braces
    if "{" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    # Fallback: try to infer from text
    raw_lower = raw.lower()
    if "replan" in raw_lower or "重新规划" in raw_lower:
        return {"action": "replan", "guidance": raw[:500], "reason": ""}
    if "escalate" in raw_lower or "升级" in raw_lower or "上报" in raw_lower:
        return {"action": "escalate_again", "guidance": raw[:500], "reason": ""}

    return {"action": "retry_with_guidance", "guidance": raw[:500], "reason": ""}


def _hitl_escalation(
    state: CollabState,
    current_level: int,
    reviewer_name: str,
    escalation_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate HITL escalation when no more supervisors are available."""
    return {
        "escalation_history": escalation_history,
        "hitl_type": "escalation",
        "hitl_message": (
            f"🚨 **Level {current_level + 1} 执行遇到问题，已升级至顶层**\n\n"
            f"审核人: {reviewer_name}\n"
            f"升级链: {_format_escalation_history(escalation_history) or '(无)'}\n\n"
            f"请做出决策："
        ),
        "hitl_options": [
            {"label": "🔄 重新执行当前阶段", "value": "retry"},
            {"label": "✅ 强制通过（忽略问题）", "value": "force_pass"},
            {"label": "🔧 重新规划", "value": "replan"},
            {"label": "✗ 放弃任务", "value": "abort"},
        ],
        "status": "blocked",
        "_content": (
            f"🚨 **升级至顶层**: 需要人工决策 Level {current_level + 1} 的处理方式"
        ),
        "_agent_name": "升级处理",
    }


def _format_escalation_history(history: list[dict[str, Any]]) -> str:
    """Format escalation history for display."""
    if not history:
        return ""
    lines = []
    for h in history:
        from_name = h.get("from_name", "?")
        to_name = h.get("to_name", "?")
        guidance = h.get("guidance", "")[:100]
        lines.append(f"  {from_name} → {to_name}: {guidance}")
    return "\n".join(lines)
