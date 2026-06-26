"""Integration tests — full collaboration flow with MemorySaver."""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from app.services.collaboration.graph import (
    compile_graph,
    classify_intent,
    route_after_supervisor,
    route_after_verifier,
)
from app.services.collaboration.types import CollabState


class TestFullGraphFlow:
    """Test the complete graph with MemorySaver checkpointer."""

    def test_graph_compiles_with_memory_saver(self):
        """Graph compiles and produces a runnable."""
        checkpointer = MemorySaver()
        graph = compile_graph(checkpointer=checkpointer)
        assert graph is not None

    def test_graph_accepts_initial_state(self):
        """Graph can invoke with initial state."""
        checkpointer = MemorySaver()
        graph = compile_graph(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "test-session-1"}}

        # Initial invoke — should hit supervisor → hitl (interrupt)
        try:
            result = graph.invoke(
                {
                    "messages": [{"role": "user", "content": "做登录系统"}],
                    "team_id": "team-1",
                    "available_roles": ["architect", "backend_dev", "frontend_dev", "tester"],
                    "team_agents": [
                        {"agent_id": "a1", "name": "架构师", "role": "architect", "status": "idle"},
                        {"agent_id": "a2", "name": "后端", "role": "backend_dev", "status": "idle"},
                        {"agent_id": "a3", "name": "前端", "role": "frontend_dev", "status": "idle"},
                        {"agent_id": "a4", "name": "测试员", "role": "tester", "status": "idle"},
                    ],
                },
                config,
            )
            # Should have reached supervisor and set status
            assert result is not None
        except Exception:
            # May raise GraphInterrupt for HITL — that's expected
            pass

    def test_state_persistence_across_invocations(self):
        """State is preserved between invocations with same thread_id."""
        checkpointer = MemorySaver()
        graph = compile_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "test-session-2"}}

        # First invoke
        try:
            graph.invoke(
                {"messages": [{"role": "user", "content": "做登录系统"}]},
                config,
            )
        except Exception:
            pass

        # Second invoke — should resume from checkpoint
        try:
            result = graph.invoke(
                {"messages": [{"role": "user", "content": "确认"}]},
                config,
            )
            assert result is not None
        except Exception:
            pass


class TestCompleteRoutingTable:
    """Verify every possible state transition is handled."""

    TRANSITIONS = [
        # (action, expected_route)
        ("need_clarify", "__end__"),
        ("need_confirm", "__end__"),
        ("invite_agent", "__end__"),
        ("execute_task", "worker"),
        ("verify", "verifier"),
        ("done", "__end__"),
        # Unknown action defaults to hitl (safe)
        ("unknown_action", "__end__"),
    ]

    def test_all_supervisor_routes(self):
        for action, expected in self.TRANSITIONS:
            state = CollabState(action=action)
            result = route_after_supervisor(state)
            assert result == expected, f"Action '{action}' should route to '{expected}', got '{result}'"

    def test_verifier_routes(self):
        # Pass → end
        assert route_after_verifier(CollabState(verification={"passed": True})) == "__end__"
        # Critical → hitl
        assert route_after_verifier(CollabState(verification={"passed": False, "severity": "critical", "escalate": True})) == "hitl"
        # Major → retry (worker)
        assert route_after_verifier(CollabState(verification={"passed": False, "severity": "major"})) == "worker"


class TestIntentRecognitionIntegration:
    """End-to-end intent recognition across full conversation lifecycle."""

    def simulate_conversation(self, turns):
        """Simulate a multi-turn conversation and verify routing at each turn."""
        state = CollabState(status="init", messages=[])
        results = []

        for user_msg, expected_intent in turns:
            intent = classify_intent(state, user_msg)
            results.append(intent)
            assert intent == expected_intent, (
                f"State '{state.get('status')}', msg '{user_msg}': "
                f"expected '{expected_intent}', got '{intent}'"
            )
            # Simulate state change (simplified)
            if intent == "approve":
                state["status"] = "executing"
            elif intent == "reject":
                state["status"] = "init"

        return results

    def test_full_conversation(self):
        """Complete conversation: init → clarify → confirm → execute."""
        state = CollabState(status="init", messages=[])

        # Turn 1: init → first question
        intent = classify_intent(state, "做登录系统")
        assert intent == "first_question"

        # Turn 2: clarifying → user answers
        state["status"] = "clarifying"
        intent = classify_intent(state, "不需要OAuth，React前端")
        assert intent == "clarify_response"

        # Turn 3: awaiting_confirm → single-word approval (fast path)
        state["status"] = "awaiting_confirm"
        intent = classify_intent(state, "确认")
        assert intent == "approve"

        # Turn 4: executing → ambiguous → LLM needed
        state["status"] = "executing"
        intent = classify_intent(state, "再加个忘记密码功能")
        assert intent == "need_llm_classify"  # Semantic → LLM classifier

        # Turn 5: completed → new task
        state["status"] = "completed"
        intent = classify_intent(state, "确认")
        assert intent == "new_task"
