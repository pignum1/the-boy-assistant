"""LangGraph StateGraph — M0-M8 node orchestration.

Clean separation: node logic lives in m0_m8 modules,
this file only defines the graph structure and routing functions.
"""

import logging
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from .types import CollabState

logger = logging.getLogger(__name__)


# ── HITL node (shared by all modules) ──

def hitl_node(state: CollabState) -> dict:
    """HITL — pause and wait for human input via LangGraph interrupt()."""
    hitl_data = interrupt({
        "type": state.get("hitl_type", "confirmation"),
        "message": state.get("hitl_message", ""),
        "options": state.get("hitl_options", []),
    })

    resp = str(hitl_data)
    result: dict[str, Any] = {"user_response": resp}

    # If user approved on clarification, set force_confirm so M1 skips back to confirmation
    if state.get("hitl_type") == "clarification" and resp.lower() in (
        "确认", "可以", "好", "ok", "yes", "/approve", "approve", "行", "好的",
        "嗯", "sure", "go", "proceed", "fine", "alright", "cool", "great",
        "lgtm", "approved", "confirmed", "同意", "赞成", "通过",
    ):
        result["force_confirm"] = True

    return result


# ── HITL route: what happens after user responds ──

def _classify_hitl_response(state: CollabState) -> str:
    """Classify HITL user response into action.

    Returns: "approve" | "reject" | "modify" | "answer" | "invite" | "skip"

    优先读 state["user_response"]（hitl_node 写入的 LangGraph interrupt() 返回值）；
    若缺失则降级到 messages.last（兼容遗留路径）。
    """
    user_response = state.get("user_response", "") or ""
    if not user_response:
        messages = state.get("messages", [])
        if not messages:
            return "reject"
        last_msg = messages[-1]
        user_response = last_msg.get("content", "") if isinstance(last_msg, dict) else str(messages[-1])
    msg = user_response.strip().lower()
    hitl_type = state.get("hitl_type", "")

    # Confirmation HITL
    if hitl_type == "confirmation":
        if msg in ("确认", "可以", "好", "ok", "yes", "/approve", "approve", "行", "好的",
                    "嗯", "sure", "go", "proceed", "fine", "alright", "cool", "great",
                    "lgtm", "approved", "confirmed", "同意", "赞成", "通过"):
            return "approve"
        if msg in ("不对", "不行", "no", "nope", "/reject", "重来", "取消", "算了"):
            return "reject"
        return "modify"  # User typed custom feedback

    # Delta plan HITL (PR5 介入闭环)
    if hitl_type == "delta_plan":
        if msg in ("确认", "可以", "好", "ok", "yes", "/approve", "approve", "应用", "好的"):
            return "approve"
        if msg in ("不对", "no", "/reject", "撤回", "取消", "算了", "reject"):
            return "reject"
        return "modify"

    # Clarification HITL
    if hitl_type == "clarification":
        if msg in ("取消", "算了", "cancel"):
            return "reject"
        # "确认并继续" on clarification = user satisfied, force M1 to confirm
        if msg in ("确认", "可以", "好", "ok", "yes", "/approve", "approve", "行", "好的",
                    "嗯", "sure", "go", "proceed", "fine", "alright", "cool", "great",
                    "lgtm", "approved", "confirmed", "同意", "赞成", "通过"):
            return "force_confirm"
        return "answer"  # User answered questions

    # Agent invite HITL
    if hitl_type == "agent_invite":
        return msg if msg in ("invite", "create", "skip") else "skip"

    # Review HITL
    if hitl_type == "review":
        if msg in ("确认", "可以", "ok", "yes", "好的", "done", "完成"):
            return "approve"
        return "modify"

    # Escalation HITL (m6_escalate → 顶层升级)
    if hitl_type == "escalation":
        if msg in ("retry", "重新执行", "重试"):
            return "retry"
        if msg in ("force_pass", "强制通过", "忽略"):
            return "force_pass"
        if msg in ("replan", "重新规划"):
            return "replan"
        if msg in ("abort", "放弃", "取消"):
            return "reject"
        # User typed free text → treat as guidance for retry
        return "retry"

    return "modify"


def route_after_hitl(state: CollabState) -> str:
    """Route after HITL user response.

    Maps HITL response to the next module:
    - approve (confirmation) → m3 (agent orchestration)
    - approve (review)       → END (task complete)
    - approve (delta_plan)   → m4 (re-decompose with delta applied)
    - reject (delta_plan)    → m6 (resume original plan)
    - reject (其它)           → END (user cancelled)
    - modify                 → m1 (re-analyze with feedback)
    - answer (clarification) → m1 (re-analyze with new info)
    - invite/skip            → m3 (proceed with available agents)
    """
    hitl_type = state.get("hitl_type", "")
    action = _classify_hitl_response(state)

    logger.info(f"HITL response: type={hitl_type}, action={action}")

    # ── delta_plan HITL (PR5 介入闭环) ──
    if hitl_type == "delta_plan":
        if action == "approve":
            return "m4_decompose"  # 应用 delta → 重新分解 → 续跑
        if action == "reject":
            return "m6_level_dispatch"  # 撤回介入 → 继续原计划
        return "m1_rebalance"  # 用户补充 → 再走一次 rebalance

    if action == "approve":
        if hitl_type == "review":
            return "__end__"  # Review approved → done
        return "m3_orchestrate"  # Confirmation approved → orchestrate

    if action == "reject":
        return "__end__"  # User cancelled

    if action in ("modify", "answer"):
        return "m1_analyze"  # Re-analyze with new input

    if action in ("invite", "skip"):
        return "m3_orchestrate"  # Proceed after agent invite/skip

    # ── escalation HITL ──
    if hitl_type == "escalation":
        if action == "retry":
            return "m6_level_execute"  # Re-execute current level
        if action == "force_pass":
            return "m6_level_dispatch"  # Skip this level, advance to next
        if action == "replan":
            return "m1_rebalance"  # Full replanning
        if action == "reject":
            return "__end__"  # Abort

    return "m1_analyze"


# ── Graph construction ──

def build_graph() -> StateGraph:
    """Build the M0-M8 collaboration StateGraph."""
    from .m0_intent_router import m0_intent_node, route_after_m0
    from .m1_requirement_analyzer import m1_analyze_node, route_after_m1
    from .m1_rebalance import m1_rebalance_node
    from .m2_clarification import m2_clarify_node
    from .m3_agent_orchestrator import m3_orchestrate_node, route_after_m3
    from .m4_task_decomposer import m4_decompose_node, route_after_m4
    from .m6_dag_executor import m6_execute_node, route_after_m6
    from .m7_verifier import m7_verify_node, route_after_m7

    workflow = StateGraph(CollabState)

    # ── Register nodes ──
    workflow.add_node("m0_intent", m0_intent_node)
    workflow.add_node("m1_analyze", m1_analyze_node)
    workflow.add_node("m1_rebalance", m1_rebalance_node)
    workflow.add_node("m2_clarify", m2_clarify_node)
    workflow.add_node("m3_orchestrate", m3_orchestrate_node)
    workflow.add_node("m4_decompose", m4_decompose_node)
    workflow.add_node("m6_execute", m6_execute_node)
    workflow.add_node("m7_verify", m7_verify_node)
    workflow.add_node("hitl", hitl_node)

    # ── Entry point ──
    workflow.set_entry_point("m0_intent")

    # ── Edges ──

    # M0: single → END, multi → M1
    workflow.add_conditional_edges("m0_intent", route_after_m0)

    # M1: clarify → M2, confirm → HITL
    workflow.add_conditional_edges("m1_analyze", route_after_m1)

    # M2: always → HITL (wait for user answers)
    workflow.add_edge("m2_clarify", "hitl")

    # HITL: route based on user response
    workflow.add_conditional_edges("hitl", route_after_hitl)

    # M3: agents ready → M4, agents missing → HITL
    workflow.add_conditional_edges("m3_orchestrate", route_after_m3)

    # M4: decompose → M6 execute
    workflow.add_conditional_edges("m4_decompose", route_after_m4)

    # M6: execute → M7 verify / HITL review / M1' rebalance（介入时）
    workflow.add_conditional_edges("m6_execute", route_after_m6)

    # M1' rebalance → HITL（等用户确认 delta_plan）
    workflow.add_edge("m1_rebalance", "hitl")

    # M7: verify → pass(HITL) / retry(M6) / reanalyze(M1) / escalate(HITL)
    workflow.add_conditional_edges("m7_verify", route_after_m7)

    return workflow


def build_graph_v2() -> StateGraph:
    """Build the M0-M8 collaboration StateGraph with hierarchical execution.

    Replaces the monolithic m6_execute node with 5 decomposed nodes:
    m6_org_loader → m6_level_dispatch → m6_level_execute → m6_level_review → m6_escalate

    This allows per-level checkpointing, org-hierarchy-based review,
    and proper escalation through LangGraph state transitions.
    """
    from .m0_intent_router import m0_intent_node, route_after_m0
    from .m1_requirement_analyzer import m1_analyze_node, route_after_m1
    from .m1_rebalance import m1_rebalance_node
    from .m2_clarification import m2_clarify_node
    from .m3_agent_orchestrator import m3_orchestrate_node, route_after_m3
    from .m4_task_decomposer import m4_decompose_node
    from .m6_org_loader import m6_org_loader_node
    from .m6_level_dispatch import m6_level_dispatch_node, route_after_level_dispatch
    from .m6_level_execute import m6_level_execute_node, route_after_level_execute
    from .m6_level_review import m6_level_review_node, route_after_level_review
    from .m6_escalate import m6_escalate_node, route_after_escalate
    from .m7_verifier import m7_verify_node

    workflow = StateGraph(CollabState)

    # ── V2-specific M7 route (retry → m6_level_dispatch) ──
    def route_after_m7_v2(state: CollabState) -> str:
        """M7 routing for v2: retry → re-enter the execution loop via dispatch."""
        verification = state.get("verification", {})
        if not verification:
            return "hitl"
        from .m7_verifier import route_after_verify
        decision = route_after_verify(verification)
        if decision == "pass":
            return "hitl"
        elif decision == "retry":
            return "m6_level_dispatch"  # Re-enter level execution loop
        else:
            return "hitl"

    # ── Register nodes ──
    workflow.add_node("m0_intent", m0_intent_node)
    workflow.add_node("m1_analyze", m1_analyze_node)
    workflow.add_node("m1_rebalance", m1_rebalance_node)
    workflow.add_node("m2_clarify", m2_clarify_node)
    workflow.add_node("m3_orchestrate", m3_orchestrate_node)
    workflow.add_node("m4_decompose", m4_decompose_node)
    # ── New: decomposed M6 nodes ──
    workflow.add_node("m6_org_loader", m6_org_loader_node)
    workflow.add_node("m6_level_dispatch", m6_level_dispatch_node)
    workflow.add_node("m6_level_execute", m6_level_execute_node)
    workflow.add_node("m6_level_review", m6_level_review_node)
    workflow.add_node("m6_escalate", m6_escalate_node)
    # ── M7 + HITL ──
    workflow.add_node("m7_verify", m7_verify_node)
    workflow.add_node("hitl", hitl_node)

    # ── Entry point ──
    workflow.set_entry_point("m0_intent")

    # ── Edges (v2 topology) ──

    # M0: single → END, multi → M1
    workflow.add_conditional_edges("m0_intent", route_after_m0)

    # M1: clarify → M2, confirm → HITL
    workflow.add_conditional_edges("m1_analyze", route_after_m1)

    # M2: always → HITL (wait for user answers)
    workflow.add_edge("m2_clarify", "hitl")

    # HITL: route based on user response (includes escalation routing)
    workflow.add_conditional_edges("hitl", route_after_hitl)

    # M3: agents ready → M4, agents missing → HITL
    workflow.add_conditional_edges("m3_orchestrate", route_after_m3)

    # M4: decompose → m6_org_loader (start hierarchical execution)
    workflow.add_edge("m4_decompose", "m6_org_loader")

    # m6_org_loader: always → m6_level_dispatch
    workflow.add_edge("m6_org_loader", "m6_level_dispatch")

    # m6_level_dispatch: has_level → execute | interrupted → rebalance | all_done → verify
    workflow.add_conditional_edges("m6_level_dispatch", route_after_level_dispatch)

    # m6_level_execute: has_org → review | no_org → dispatch (skip review)
    workflow.add_conditional_edges("m6_level_execute", route_after_level_execute)

    # m6_level_review: pass → dispatch(next level) | retry → execute | escalate → escalation
    workflow.add_conditional_edges("m6_level_review", route_after_level_review)

    # m6_escalate: retry → execute | replan → rebalance | hitl → HITL
    workflow.add_conditional_edges("m6_escalate", route_after_escalate)

    # M1' rebalance → HITL（等用户确认 delta_plan）
    workflow.add_edge("m1_rebalance", "hitl")

    # M7: verify → pass(HITL) / retry(dispatch) / escalate(HITL)
    workflow.add_conditional_edges("m7_verify", route_after_m7_v2)

    return workflow


def build_graph_v3() -> StateGraph:
    """Build the M0-M8 collaboration StateGraph with Route B hierarchical delegation.

    Replaces v2's m6_level_dispatch/execute/review with:
    m6_delegate_root → m6_delegate_sub → m6_plan_validate → m6_delegate_push
    → m6_execute_worker → m6_collect

    This enables true hierarchical delegation where each supervisor
    autonomously decomposes and assigns goals to subordinates.
    """
    from .m0_intent_router import m0_intent_node, route_after_m0
    from .m1_requirement_analyzer import m1_analyze_node, route_after_m1
    from .m1_rebalance import m1_rebalance_node
    from .m2_clarification import m2_clarify_node
    from .m3_agent_orchestrator import m3_orchestrate_node, route_after_m3
    from .m4_task_decomposer import m4_decompose_node
    from .m6_org_loader import m6_org_loader_node
    from .m6_delegate import (
        m6_delegate_root_node,
        m6_delegate_sub_node,
        route_after_delegate,
    )
    from .m6_plan_validate import (
        m6_plan_validate_node,
        m6_delegate_push_node,
        route_after_validate,
    )
    from .m6_execute_worker import m6_execute_worker_node
    from .m6_collect import m6_collect_node, route_after_collect
    from .m6_escalate import m6_escalate_node, route_after_escalate
    from .m7_verifier import m7_verify_node

    workflow = StateGraph(CollabState)

    # ── V3-specific routing functions ──

    def route_after_m7_v3(state: CollabState) -> str:
        """M7 routing for v3: pass→HITL, retry→delegate_root, reanalyze→M1, escalate→HITL."""
        verification = state.get("verification", {})
        if not verification:
            return "hitl"
        from .m7_verifier import route_after_verify
        decision = route_after_verify(verification)
        if decision == "pass":
            return "hitl"
        elif decision == "retry":
            return "m6_delegate_root"  # Re-enter delegation from the top
        elif decision == "reanalyze":
            return "m1_analyze"  # Back to M1: re-analyze with verification feedback
        else:
            return "hitl"

    def route_after_hitl_v3(state: CollabState) -> str:
        """HITL routing for v3 — same logic as v1 but with updated node names."""
        hitl_type = state.get("hitl_type", "")
        action = _classify_hitl_response(state)

        logger.info(f"HITL response: type={hitl_type}, action={action}")

        # ── delta_plan HITL ──
        if hitl_type == "delta_plan":
            if action == "approve":
                return "m4_decompose"
            if action == "reject":
                return "m6_delegate_root"  # Resume original delegation
            return "m1_rebalance"

        if action == "approve":
            if hitl_type == "review":
                return "__end__"
            return "m3_orchestrate"

        if action == "force_confirm":
            # User approved on clarification → go back to M1 with force_confirm flag
            state["force_confirm"] = True
            return "m1_analyze"

        if action == "reject":
            return "__end__"

        if action in ("modify", "answer"):
            return "m1_analyze"

        if action in ("invite", "skip"):
            return "m3_orchestrate"

        # ── escalation HITL ──
        if hitl_type == "escalation":
            if action == "retry":
                return "m6_delegate_sub"  # Retry current delegation
            if action == "force_pass":
                return "m6_delegate_root"  # Skip, advance
            if action == "replan":
                return "m1_rebalance"
            if action == "reject":
                return "__end__"

        return "m1_analyze"

    # ── Register nodes ──
    workflow.add_node("m0_intent", m0_intent_node)
    workflow.add_node("m1_analyze", m1_analyze_node)
    workflow.add_node("m1_rebalance", m1_rebalance_node)
    workflow.add_node("m2_clarify", m2_clarify_node)
    workflow.add_node("m3_orchestrate", m3_orchestrate_node)
    workflow.add_node("m4_decompose", m4_decompose_node)
    # ── Route B: hierarchical delegation nodes ──
    workflow.add_node("m6_org_loader", m6_org_loader_node)
    workflow.add_node("m6_delegate_root", m6_delegate_root_node)
    workflow.add_node("m6_delegate_sub", m6_delegate_sub_node)
    workflow.add_node("m6_plan_validate", m6_plan_validate_node)
    workflow.add_node("m6_delegate_push", m6_delegate_push_node)
    workflow.add_node("m6_execute_worker", m6_execute_worker_node)
    workflow.add_node("m6_collect", m6_collect_node)
    workflow.add_node("m6_escalate", m6_escalate_node)
    # ── M7 + HITL ──
    workflow.add_node("m7_verify", m7_verify_node)
    workflow.add_node("hitl", hitl_node)

    # ── Entry point ──
    workflow.set_entry_point("m0_intent")

    # ── Edges (v3 topology) ──

    # M0: single → END, multi → M1
    workflow.add_conditional_edges("m0_intent", route_after_m0)

    # M1: clarify → M2, confirm → HITL
    workflow.add_conditional_edges("m1_analyze", route_after_m1)

    # M2: always → HITL (wait for user answers)
    workflow.add_edge("m2_clarify", "hitl")

    # HITL: route based on user response (v3 node names)
    workflow.add_conditional_edges("hitl", route_after_hitl_v3)

    # M3: agents ready → M4, agents missing → HITL
    workflow.add_conditional_edges("m3_orchestrate", route_after_m3)

    # M4: decompose → m6_org_loader (start hierarchical delegation)
    workflow.add_edge("m4_decompose", "m6_org_loader")

    # m6_org_loader → m6_delegate_root (Leader entry)
    workflow.add_edge("m6_org_loader", "m6_delegate_root")

    # m6_delegate_root → worker/validate/collect
    workflow.add_conditional_edges("m6_delegate_root", route_after_delegate)

    # m6_delegate_sub → worker/validate/collect (recursive entry)
    workflow.add_conditional_edges("m6_delegate_sub", route_after_delegate)

    # m6_plan_validate → approved:push / rejected:root
    workflow.add_conditional_edges("m6_plan_validate", route_after_validate)

    # m6_delegate_push → always → m6_delegate_sub
    workflow.add_edge("m6_delegate_push", "m6_delegate_sub")

    # m6_execute_worker → always → m6_collect
    workflow.add_edge("m6_execute_worker", "m6_collect")

    # m6_collect → done:verify / next:sub / retry:sub / escalate
    workflow.add_conditional_edges("m6_collect", route_after_collect)

    # m6_escalate → retry:sub / replan:rebalance / hitl
    workflow.add_conditional_edges("m6_escalate", route_after_escalate)

    # M1' rebalance → HITL（等用户确认 delta_plan）
    workflow.add_edge("m1_rebalance", "hitl")

    # M7: verify → pass(HITL) / retry(delegate_root) / escalate(HITL)
    workflow.add_conditional_edges("m7_verify", route_after_m7_v3)

    return workflow


def compile_graph(checkpointer=None):
    """Compile graph. Use MemorySaver for dev, AsyncPostgresSaver for prod.

    Uses v3 (Route B hierarchical delegation) by default.
    v1/v2 are kept for reference only.
    """
    graph = build_graph_v3()
    return graph.compile(checkpointer=checkpointer or MemorySaver())
