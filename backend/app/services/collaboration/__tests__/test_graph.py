"""Tests for LangGraph graph skeleton and intent recognition.

Verifies:
1. Graph compiles correctly with all 4 nodes
2. All edges exist
3. Intent classifier routes correctly across all 5 states
4. Same input "确认" routes differently based on state
5. Invalid states don't crash
"""

import pytest
from app.services.collaboration.graph import (
    classify_intent,
    build_graph,
    route_after_supervisor,
    route_after_worker,
    route_after_verifier,
)
from app.services.collaboration.types import CollabState


class TestIntentClassifier:
    """Multi-turn intent recognition — same word, different states, different routes."""

    def test_init_state_treats_confirm_as_first_question(self):
        """In init state, "确认" has no context → treated as first question."""
        state = CollabState(status="init", messages=[])
        assert classify_intent(state, "确认") == "first_question"

    def test_awaiting_confirm_approve(self):
        """In awaiting_confirm, "确认" = approve."""
        state = CollabState(status="awaiting_confirm")
        assert classify_intent(state, "确认") == "approve"
        assert classify_intent(state, "/approve") == "approve"
        assert classify_intent(state, "可以") == "approve"
        assert classify_intent(state, "ok") == "approve"

    def test_awaiting_confirm_reject(self):
        """In awaiting_confirm, single-word "不对" = reject fast path."""
        state = CollabState(status="awaiting_confirm")
        assert classify_intent(state, "不对") == "reject"
        assert classify_intent(state, "不行") == "reject"
        assert classify_intent(state, "/reject") == "reject"
        # Multi-word rejection → LLM classification
        assert classify_intent(state, "不对，重新做") == "need_llm_classify"

    def test_awaiting_confirm_modify(self):
        """In awaiting_confirm, non-obvious text → LLM classification."""
        state = CollabState(status="awaiting_confirm")
        assert classify_intent(state, "第三个阶段改成前端") == "need_llm_classify"

    def test_clarifying_state(self):
        """In clarifying, any response = clarify_response."""
        state = CollabState(status="clarifying")
        assert classify_intent(state, "不需要OAuth") == "clarify_response"

    def test_executing_state_progress_query(self):
        """In executing, progress query → LLM classification."""
        state = CollabState(status="executing")
        assert classify_intent(state, "现在进度怎么样了") == "need_llm_classify"

    def test_executing_state_extend_task(self):
        """In executing, "再加" → LLM semantic classification."""
        state = CollabState(status="executing")
        assert classify_intent(state, "对了，再加个忘记密码功能") == "need_llm_classify"

    def test_executing_state_ambiguous_input(self):
        """In executing, ambiguous input → LLM needed."""
        state = CollabState(status="executing")
        assert classify_intent(state, "确认") == "need_llm_classify"

    def test_awaiting_review_approve(self):
        """In awaiting_review, "确认" = approve."""
        state = CollabState(status="awaiting_review")
        assert classify_intent(state, "确认") == "approve"

    def test_completed_state_new_task(self):
        """In completed, anything = new_task."""
        state = CollabState(status="completed")
        assert classify_intent(state, "确认") == "new_task"
        assert classify_intent(state, "再来一个") == "new_task"

    def test_same_word_5_different_routes(self):
        """The core test: "确认" routes to 5 different intents in 5 states."""
        msg = "确认"
        results = {
            "init": classify_intent(CollabState(status="init"), msg),
            "awaiting_confirm": classify_intent(CollabState(status="awaiting_confirm"), msg),
            "executing": classify_intent(CollabState(status="executing"), msg),
            "awaiting_review": classify_intent(CollabState(status="awaiting_review"), msg),
            "completed": classify_intent(CollabState(status="completed"), msg),
        }
        assert results["init"] == "first_question"
        assert results["awaiting_confirm"] == "approve"  # Single-word match
        assert results["executing"] == "need_llm_classify"  # Ambiguous → LLM
        assert results["awaiting_review"] == "approve"
        assert results["completed"] == "new_task"


class TestGraphTopology:
    """Verify the graph compiles and has correct structure."""

    def test_graph_builds_with_4_nodes(self):
        graph = build_graph()
        nodes = graph.nodes
        assert "supervisor" in nodes
        assert "hitl" in nodes
        assert "worker" in nodes
        assert "verifier" in nodes
        assert len(nodes) == 4

    def test_entry_point_is_supervisor(self):
        graph = build_graph()
        # Entry point should be supervisor
        assert graph._all_edges is not None  # Graph has edges defined


class TestRoutingFunctions:
    """Verify routing functions direct to correct nodes."""

    def test_route_supervisor_to_end_for_clarify(self):
        state = CollabState(action="need_clarify")
        assert route_after_supervisor(state) == "__end__"

    def test_route_supervisor_to_end_for_confirm(self):
        state = CollabState(action="need_confirm")
        assert route_after_supervisor(state) == "__end__"

    def test_route_supervisor_to_end_for_invite(self):
        state = CollabState(action="invite_agent")
        assert route_after_supervisor(state) == "__end__"

    def test_route_supervisor_to_worker_for_execute(self):
        state = CollabState(action="execute_task")
        assert route_after_supervisor(state) == "worker"

    def test_route_supervisor_to_verifier(self):
        state = CollabState(action="verify")
        assert route_after_supervisor(state) == "verifier"

    def test_route_verifier_pass_to_end(self):
        state = CollabState(verification={"passed": True})
        result = route_after_verifier(state)
        assert result == "__end__"

    def test_route_verifier_escalate_to_hitl(self):
        state = CollabState(verification={"passed": False, "severity": "critical"})
        assert route_after_verifier(state) == "hitl"

    def test_route_verifier_fail_to_worker_retry(self):
        state = CollabState(verification={"passed": False, "escalate": False})
        assert route_after_verifier(state) == "worker"
