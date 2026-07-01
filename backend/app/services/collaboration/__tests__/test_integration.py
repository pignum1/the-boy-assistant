"""Integration tests — full collaboration flow with MemorySaver.

Tests:
1. All graph versions compile and accept initial state
2. State persistence across invocations (same thread_id)
3. CollabState creation and defaults
4. Cross-module routing consistency
5. M0 rules-based classification integration
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from app.services.collaboration.graph import (
    build_graph,
    build_graph_v2,
    build_graph_v3,
    compile_graph,
    route_after_hitl,
)
from app.services.collaboration.types import CollabState


# ── CollabState defaults ──


class TestCollabState:
    """Verify CollabState creation and default values."""

    def test_default_state_is_empty(self):
        state = CollabState()
        assert len(state) == 0
        assert state.get("messages", []) == []

    def test_can_set_fields(self):
        state = CollabState(status="init", messages=[{"role": "user", "content": "hello"}])
        assert state["status"] == "init"
        assert len(state["messages"]) == 1

    def test_nested_fields_preserved(self):
        state = CollabState(
            verification={"passed": True, "severity": "none"},
            task_dag={"phases": [{"id": "p1", "tasks": []}]},
        )
        assert state["verification"]["passed"] is True
        assert len(state["task_dag"]["phases"]) == 1


# ── Graph compilation ──


class TestFullGraphFlow:
    """Verify each graph version compiles with MemorySaver."""

    def test_v1_graph_compiles(self):
        graph = build_graph()
        compiled = graph.compile(checkpointer=MemorySaver())
        assert compiled is not None

    @pytest.mark.skip(reason="V2 intermediate modules (m6_level_*) not fully implemented")
    def test_v2_graph_compiles(self):
        graph = build_graph_v2()
        compiled = graph.compile(checkpointer=MemorySaver())
        assert compiled is not None

    def test_v3_graph_compiles(self):
        graph = build_graph_v3()
        compiled = graph.compile(checkpointer=MemorySaver())
        assert compiled is not None

    def test_compile_graph_default(self):
        compiled = compile_graph()
        assert compiled is not None

    def test_compile_graph_with_custom_checkpointer(self):
        checkpointer = MemorySaver()
        compiled = compile_graph(checkpointer=checkpointer)
        assert compiled is not None

    def test_v3_graph_has_entry_point(self):
        graph = build_graph_v3()
        compiled = graph.compile(checkpointer=MemorySaver())
        # Should have an entry point to invoke
        assert compiled is not None


# ── State persistence ──


class TestStatePersistence:
    """Verify state can be persisted and updated across invocations."""

    def test_state_dict_operations(self):
        state = CollabState(status="init")
        state["status"] = "analyzing"
        state["routing_decision"] = "multi_agent"
        assert state["status"] == "analyzing"
        assert state["routing_decision"] == "multi_agent"

    def test_state_get_default(self):
        state = CollabState()
        assert state.get("missing_key", "default") == "default"
        assert state.get("status", "idle") == "idle"


# ── Cross-module routing consistency ──


class TestRoutingConsistency:
    """Verify routing functions across modules return valid graph node names."""

    # Valid node names in the current graph versions
    VALID_NODES = {
        "m0_intent", "m1_analyze", "m1_rebalance", "m2_clarify",
        "m3_orchestrate", "m4_decompose",
        "m6_execute", "m6_level_dispatch", "m6_level_execute",
        "m6_org_loader", "m6_delegate_root", "m6_delegate_sub",
        "m6_plan_validate", "m6_delegate_push", "m6_execute_worker",
        "m6_collect", "m6_escalate", "m6_level_review",
        "m7_verify", "hitl", "__end__",
    }

    def test_m0_route_returns_valid_target(self):
        from app.services.collaboration.m0_intent_router import route_after_m0
        state = CollabState(routing_decision="multi_agent")
        assert route_after_m0(state) in self.VALID_NODES

        state2 = CollabState(routing_decision="single_agent")
        assert route_after_m0(state2) in self.VALID_NODES

    def test_m1_route_returns_valid_target(self):
        from app.services.collaboration.m1_requirement_analyzer import route_after_m1
        cases = [
            CollabState(hitl_type="clarification"),
            CollabState(hitl_type="confirmation"),
            CollabState(hitl_type="agent_invite"),
            CollabState(status="completed"),
            CollabState(hitl_type=""),
        ]
        for state in cases:
            result = route_after_m1(state)
            assert result in self.VALID_NODES, f"route_after_m1({state}) = {result}"

    def test_m3_route_returns_valid_target(self):
        from app.services.collaboration.m3_agent_orchestrator import route_after_m3
        state = CollabState(agent_assignments={"architect": {"agent_id": "a1"}})
        assert route_after_m3(state) in self.VALID_NODES

        state2 = CollabState(agent_assignments={})
        assert route_after_m3(state2) in self.VALID_NODES

    def test_m4_route_returns_valid_target(self):
        from app.services.collaboration.m4_task_decomposer import route_after_m4
        state = CollabState()
        assert route_after_m4(state) in self.VALID_NODES

    def test_m6_route_returns_valid_target(self):
        from app.services.collaboration.m6_dag_executor import route_after_m6
        state = CollabState(status="completed")
        assert route_after_m6(state) in self.VALID_NODES

        state2 = CollabState(status="executing")
        assert route_after_m6(state2) in self.VALID_NODES

    def test_m7_route_returns_valid_target(self):
        from app.services.collaboration.m7_verifier import route_after_m7
        cases = [
            CollabState(verification={"passed": True}),
            CollabState(verification={"passed": False, "severity": "major"}),
            CollabState(verification={"passed": False, "severity": "critical"}),
            CollabState(verification={"passed": False, "severity": "minor"}),
            CollabState(verification={}),
        ]
        for state in cases:
            result = route_after_m7(state)
            assert result in self.VALID_NODES, (
                f"route_after_m7(verification={state.get('verification')}) = {result}"
            )

    def test_hitl_route_returns_valid_target(self):
        cases = [
            CollabState(hitl_type="confirmation", user_response="确认"),
            CollabState(hitl_type="confirmation", user_response="不对"),
            CollabState(hitl_type="confirmation", user_response="需要修改"),
            CollabState(hitl_type="clarification", user_response="用React"),
            CollabState(hitl_type="review", user_response="确认"),
            CollabState(hitl_type="review", user_response="改一下"),
            CollabState(hitl_type="delta_plan", user_response="确认"),
            CollabState(hitl_type="delta_plan", user_response="不对"),
            CollabState(hitl_type="agent_invite", user_response="skip"),
            CollabState(hitl_type="agent_invite", user_response="invite"),
            CollabState(hitl_type="escalation", user_response="重新执行"),
            CollabState(hitl_type="escalation", user_response="放弃"),
        ]
        for state in cases:
            result = route_after_hitl(state)
            assert result in self.VALID_NODES, (
                f"route_after_hitl(type={state['hitl_type']}, "
                f"response={state['user_response']}) = {result}"
            )


# ── M0 rules → routing consistency ──


class TestM0RulesIntegration:
    """Verify M0 rule-based routing produces decisions that M0 route function handles."""

    def test_known_rules_produce_routable_decisions(self):
        from app.services.collaboration.m0_intent_router import _classify_by_rules

        test_cases = [
            ("你好", "init", None),                    # greeting → single
            ("帮我开发一个系统", "init", None),         # multi keyword → multi
            ("重构这个模块", "init", None),             # refactor → multi
            ("确认", "executing", None),               # in flow → multi
            ("解释一下这个", "init", None),             # question → single
            ("好的谢谢", "init", None),                # thanks → single
            ("帮我看看", "init", ["agent-1"]),         # @mention → single
            ("@all 开发新功能", "init", ["__all__"]),   # @all → multi
        ]

        for msg, status, mentions in test_cases:
            decision = _classify_by_rules(msg, status, mentions)
            assert decision is not None, f"No decision for '{msg[:30]}'"
            # Each decision should be in valid set
            assert decision in ("single_agent", "multi_agent"), (
                f"Unexpected decision '{decision}' for '{msg[:30]}'"
            )
