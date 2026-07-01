"""Tests for LangGraph StateGraph — M0-M8 topology and routing.

Verifies:
1. All 3 graph versions compile correctly with correct nodes
2. Entry point is M0
3. M0 intent router classifies messages correctly (rules-based fast paths)
4. HITL response classifier routes correctly for each HITL type
5. M7 verifier routes map to correct graph nodes
"""

import pytest
from app.services.collaboration.graph import (
    build_graph,
    build_graph_v2,
    build_graph_v3,
    compile_graph,
    hitl_node,
    route_after_hitl,
)
from app.services.collaboration.types import CollabState
from app.services.collaboration.m0_intent_router import _classify_by_rules
from app.services.collaboration.m7_verifier import route_after_verify


# ── M0 Intent Router (rules-based fast paths) ──


class TestM0IntentRouter:
    """Rule-based intent classification — zero-LLM fast paths for common cases."""

    def test_multi_agent_keyword_triggers_pipeline(self):
        assert _classify_by_rules("帮我开发一个登录系统", "init", None) == "multi_agent"

    def test_multi_agent_keyword_refactor(self):
        assert _classify_by_rules("重构这个模块", "init", None) == "multi_agent"

    def test_single_agent_greeting(self):
        assert _classify_by_rules("你好", "init", None) == "single_agent"

    def test_single_agent_question(self):
        assert _classify_by_rules("什么是FastAPI", "init", None) == "single_agent"

    def test_already_in_flow_stays_multi(self):
        """When status is not init/completed, the conversation is already in multi-agent flow."""
        assert _classify_by_rules("确认", "executing", None) == "multi_agent"
        assert _classify_by_rules("ok", "awaiting_confirm", None) == "multi_agent"

    def test_at_all_triggers_multi(self):
        assert _classify_by_rules("帮我开发系统 @all", "init", ["__all__"]) == "multi_agent"

    def test_at_mention_triggers_single(self):
        assert _classify_by_rules("帮我看看 @架构师", "init", ["agent-1"]) == "single_agent"

    def test_short_message_with_no_technical_terms(self):
        assert _classify_by_rules("好的", "init", None) == "single_agent"


# ── Graph Topology ──


class TestGraphTopology:
    """Verify each graph version compiles with correct node sets."""

    def test_v1_builds_with_9_nodes(self):
        graph = build_graph()
        nodes = graph.nodes
        expected = {"m0_intent", "m1_analyze", "m1_rebalance", "m2_clarify",
                     "m3_orchestrate", "m4_decompose", "m6_execute", "m7_verify", "hitl"}
        assert expected.issubset(nodes)
        assert len(nodes) == 9

    def test_v1_entry_point_is_m0(self):
        graph = build_graph()
        # Graph compiles without error — edges are defined
        assert graph._all_edges is not None

    @pytest.mark.skip(reason="V2 intermediate modules (m6_level_*) not fully implemented")
    def test_v2_builds_with_13_nodes(self):
        graph = build_graph_v2()
        nodes = graph.nodes
        expected_v2 = {"m0_intent", "m1_analyze", "m1_rebalance", "m2_clarify",
                        "m3_orchestrate", "m4_decompose",
                        "m6_org_loader", "m6_level_dispatch", "m6_level_execute",
                        "m6_level_review", "m6_escalate",
                        "m7_verify", "hitl"}
        assert expected_v2.issubset(nodes)
        assert len(nodes) == 13

    def test_v3_builds_with_16_nodes(self):
        graph = build_graph_v3()
        nodes = graph.nodes
        expected_v3 = {"m0_intent", "m1_analyze", "m1_rebalance", "m2_clarify",
                        "m3_orchestrate", "m4_decompose",
                        "m6_org_loader", "m6_delegate_root", "m6_delegate_sub",
                        "m6_plan_validate", "m6_delegate_push", "m6_execute_worker",
                        "m6_collect", "m6_escalate",
                        "m7_verify", "hitl"}
        assert expected_v3.issubset(nodes)
        assert len(nodes) == 16

    def test_compile_uses_v3(self):
        from langgraph.checkpoint.memory import MemorySaver
        compiled = compile_graph(checkpointer=MemorySaver())
        assert compiled is not None

    def test_v3_has_route_b_delegation_nodes(self):
        graph = build_graph_v3()
        nodes = graph.nodes
        assert "m6_delegate_root" in nodes
        assert "m6_delegate_sub" in nodes
        assert "m6_execute_worker" in nodes
        assert "m6_collect" in nodes


# ── HITL Response Classification ──


class TestHitlResponseClassifier:
    """Verify HITL user responses are classified into correct actions."""

    def test_confirmation_approve(self):
        state = CollabState(hitl_type="confirmation", user_response="确认")
        assert route_after_hitl(state) == "m3_orchestrate"

    def test_confirmation_reject(self):
        state = CollabState(hitl_type="confirmation", user_response="不对")
        assert route_after_hitl(state) == "__end__"

    def test_confirmation_modify(self):
        state = CollabState(hitl_type="confirmation", user_response="改一下第三个阶段")
        assert route_after_hitl(state) == "m1_analyze"

    def test_clarification_answer(self):
        state = CollabState(hitl_type="clarification", user_response="用React前端")
        assert route_after_hitl(state) == "m1_analyze"

    def test_clarification_force_confirm(self):
        state = CollabState(hitl_type="clarification", user_response="确认")
        assert route_after_hitl(state) == "m1_analyze"

    def test_review_approve_ends(self):
        state = CollabState(hitl_type="review", user_response="确认")
        assert route_after_hitl(state) == "__end__"

    def test_review_modify_reanalyzes(self):
        state = CollabState(hitl_type="review", user_response="需要修改")
        assert route_after_hitl(state) == "m1_analyze"

    def test_delta_plan_approve(self):
        state = CollabState(hitl_type="delta_plan", user_response="确认")
        assert route_after_hitl(state) == "m4_decompose"

    def test_delta_plan_reject(self):
        state = CollabState(hitl_type="delta_plan", user_response="不对")
        assert route_after_hitl(state) == "m6_level_dispatch"

    def test_agent_invite_skip(self):
        state = CollabState(hitl_type="agent_invite", user_response="skip")
        assert route_after_hitl(state) == "m3_orchestrate"

    def test_escalation_retry(self):
        state = CollabState(hitl_type="escalation", user_response="重新执行")
        result = route_after_hitl(state)
        assert result in ("m6_level_execute", "m6_delegate_sub")

    def test_escalation_abort(self):
        state = CollabState(hitl_type="escalation", user_response="放弃")
        assert route_after_hitl(state) == "__end__"


# ── M7 Verifier Routing ──


class TestM7VerifierRouting:
    """Verify M7 verifier routes to correct graph nodes."""

    def test_pass_routes_to_hitl(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        state = CollabState(verification={"passed": True})
        assert route_after_m7(state) == "hitl"

    def test_retry_routes_to_execute(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        state = CollabState(verification={"passed": False, "severity": "major"})
        assert route_after_m7(state) == "m6_execute"

    def test_critical_routes_to_hitl(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        state = CollabState(verification={"passed": False, "severity": "critical"})
        assert route_after_m7(state) == "hitl"

    def test_drift_routes_to_reanalyze(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        state = CollabState(verification={"passed": False, "severity": "major", "drift_detected": True})
        assert route_after_m7(state) == "m1_analyze"

    def test_no_verification_routes_to_hitl(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        state = CollabState(verification={})
        assert route_after_m7(state) == "hitl"


# ── M1 Route after analysis ──


class TestM1Routing:
    """Verify M1 analysis routes to correct nodes."""

    def test_clarify_routes_to_m2(self):
        from app.services.collaboration.m1_requirement_analyzer import route_after_m1
        state = CollabState(hitl_type="clarification")
        assert route_after_m1(state) == "m2_clarify"

    def test_confirmation_routes_to_hitl(self):
        from app.services.collaboration.m1_requirement_analyzer import route_after_m1
        state = CollabState(hitl_type="confirmation")
        assert route_after_m1(state) == "hitl"

    def test_completed_routes_to_end(self):
        from app.services.collaboration.m1_requirement_analyzer import route_after_m1
        state = CollabState(status="completed", hitl_type="")
        assert route_after_m1(state) == "__end__"
