"""M2: Clarification — generate structured clarification questions.

Bridge between M1 (analysis) and HITL (user interaction).
When clarity_score < threshold, extracts and formats clarification questions.

When clarity is sufficient, passes through to confirmation HITL directly.
"""

import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)

# Threshold: below this score, we need clarification
CLARITY_THRESHOLD = 0.7


def _format_questions(questions: list[str]) -> str:
    """Format clarification questions for display."""
    if not questions:
        return "请补充更多信息，以便我准确理解您的需求。"

    lines = ["🤔 需要确认以下信息：\n"]
    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}.** {q}")
    return "\n".join(lines)


def _build_clarification_context(state: CollabState) -> str:
    """Build context summary for the clarification message."""
    summary = state.get("analysis_summary", "")
    problem_type = state.get("problem_type", "")
    required = state.get("required_roles", [])

    parts = []
    if summary:
        parts.append(f"当前理解: {summary[:200]}")
    if problem_type:
        type_labels = {
            "feature_request": "新功能",
            "bug_fix": "Bug修复",
            "refactor": "重构",
            "question": "问题咨询",
        }
        parts.append(f"任务类型: {type_labels.get(problem_type, problem_type)}")
    if required:
        parts.append(f"涉及角色: {', '.join(required)}")

    return "\n".join(parts)


async def m2_clarify_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M2 clarification.

    Two paths:
    1. clarity_score >= threshold → skip clarification, go to confirmation HITL
    2. clarity_score < threshold  → format questions, present HITL clarification card
    """
    clarity = state.get("clarity_score", 1.0)
    hitl_message = state.get("hitl_message", "")
    hitl_type = state.get("hitl_type", "")

    # Get actual agent name from team (instead of "M2·澄清")
    team_agents = state.get("team_agents", [])
    agent_name = team_agents[0].get("name", "产品经理-Agent") if team_agents else "产品经理-Agent"

    # If M1 already decided need_confirm (not need_clarify), pass through
    if hitl_type == "confirmation" or clarity >= CLARITY_THRESHOLD:
        logger.info(f"M2: clarity sufficient ({clarity:.1f}), passing to confirmation HITL")
        return {
            "status": "awaiting_confirm",
            "hitl_type": "confirmation",
            "_agent_name": agent_name,
        }

    # Need clarification
    logger.info(f"M2: clarity insufficient ({clarity:.1f}), generating clarification")

    # Use M1's hitl_message (already formatted questions) or build our own
    message = hitl_message
    if not message:
        message = "请补充更多信息，以便我准确理解您的需求。"

    # Add context summary
    context = _build_clarification_context(state)
    if context:
        message = f"{message}\n\n---\n{context}"

    return {
        "status": "clarifying",
        "hitl_type": "clarification",
        "hitl_message": message,
        "_agent_name": agent_name,
        "hitl_options": [
            {"label": "✅ 确认并继续", "value": "approve"},
            {"label": "💬 我来回答", "value": "answer"},
            {"label": "✗ 取消", "value": "reject"},
        ],
    }


# ── Route function ──
# m2_clarify always goes to HITL (user needs to answer)
# The routing is: m2_clarify → hitl (edge, not conditional)
