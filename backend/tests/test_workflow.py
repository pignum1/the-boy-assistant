"""Workflow 域单元测试：TaskState / ConditionRouter / LoopController / SOPRouter / SOPNodeExecutor

纯逻辑测试，不依赖数据库。
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sop_state import TaskState
from app.services.sop_router import SOPRouter
from app.services.sop_node_executor import SOPNodeExecutor
from app.services.condition_router import ConditionRouter
from app.services.loop_controller import LoopController


# ── TaskState ──────────────────────────────────────────────

class TestTaskState:
    def test_init_defaults(self):
        state = TaskState(task_id="t1", sop_id="s1", team_id="tm1")
        assert state.status == "running"
        assert state.hitl_pending is False
        assert state.hitl_result == ""
        assert state.retry_count == 0
        assert state.validations == {"passed": False, "results": []}
        assert state.errors == []
        assert state.artifacts == []
        assert state.messages == []

    def test_to_dict_and_from_dict(self):
        state = TaskState(task_id="t1", sop_id="s1", team_id="tm1")
        state.current_node = "n2"
        state.status = "paused"
        state.hitl_pending = True
        state.hitl_result = ""
        state.hitl_data = {"node": "n3", "message": "confirm", "timeout": 300}
        state.artifacts = [{"node": "n2", "output": "test"}]
        state.errors = ["err1"]

        d = state.to_dict()
        assert d["task_id"] == "t1"
        assert d["status"] == "paused"
        assert d["hitl_pending"] is True
        assert len(d["artifacts"]) == 1

        restored = TaskState.from_dict(d)
        assert restored.task_id == "t1"
        assert restored.status == "paused"
        assert restored.hitl_pending is True
        assert restored.current_node == "n2"
        assert restored.artifacts == [{"node": "n2", "output": "test"}]

    def test_from_dict_missing_fields(self):
        d = {"task_id": "t1", "sop_id": "s1", "team_id": "tm1"}
        state = TaskState.from_dict(d)
        assert state.status == "pending"
        assert state.artifacts == []
        assert state.retry_count == 0


# ── ConditionRouter ────────────────────────────────────────

class TestConditionRouter:
    def setup_method(self):
        self.router = ConditionRouter()

    def test_equality(self):
        assert self.router.evaluate("hitl_result == approve", {"hitl_result": "approve"}) is True
        assert self.router.evaluate("hitl_result == reject", {"hitl_result": "approve"}) is False

    def test_numeric_comparison(self):
        assert self.router.evaluate("score >= 0.8", {"score": 0.9}) is True
        assert self.router.evaluate("score >= 0.8", {"score": 0.7}) is False
        assert self.router.evaluate("count > 3", {"count": 5}) is True

    def test_contains(self):
        assert self.router.evaluate("name contains 'test'", {"name": "my_test_file"}) is True
        assert self.router.evaluate("name contains 'prod'", {"name": "my_test_file"}) is False

    def test_is_empty(self):
        assert self.router.evaluate("errors is_empty", {"errors": []}) is True
        assert self.router.evaluate("errors is_empty", {"errors": ["e1"]}) is False

    def test_is_not_empty(self):
        assert self.router.evaluate("result is_not_empty", {"result": "ok"}) is True
        assert self.router.evaluate("result is_not_empty", {"result": ""}) is False

    def test_nested_variable(self):
        ctx = {"validations": {"passed": True}}
        assert self.router.evaluate("validations.passed == True", ctx) is True

    def test_boolean_values(self):
        assert self.router.evaluate("flag == true", {"flag": True}) is True
        assert self.router.evaluate("flag == false", {"flag": False}) is True

    def test_string_quoted_values(self):
        assert self.router.evaluate("status == 'running'", {"status": "running"}) is True
        assert self.router.evaluate('status == "paused"', {"status": "paused"}) is True

    def test_evaluate_all_and(self):
        ctx = {"a": 1, "b": 2}
        assert self.router.evaluate_all(["a == 1", "b == 2"], ctx, "and") is True
        assert self.router.evaluate_all(["a == 1", "b == 3"], ctx, "and") is False

    def test_evaluate_all_or(self):
        ctx = {"a": 1, "b": 2}
        assert self.router.evaluate_all(["a == 0", "b == 2"], ctx, "or") is True
        assert self.router.evaluate_all(["a == 0", "b == 0"], ctx, "or") is False

    def test_evaluate_all_empty(self):
        assert self.router.evaluate_all([], {}) is True

    def test_route_matches_first(self):
        branches = [
            {"condition": "x == 1", "target": "A"},
            {"condition": "x == 2", "target": "B"},
        ]
        assert self.router.route(branches, {"x": 1}) == "A"
        assert self.router.route(branches, {"x": 2}) == "B"

    def test_route_default(self):
        branches = [{"condition": "x == 1", "target": "A"}]
        assert self.router.route(branches, {"x": 5}, default="C") == "C"

    def test_route_empty_condition(self):
        branches = [{"condition": "", "target": "X"}]
        assert self.router.route(branches, {"x": 99}) == "X"

    def test_unparseable_expression(self):
        assert self.router.evaluate("garbage expression !!!", {}) is False


# ── LoopController ─────────────────────────────────────────

class TestLoopController:
    def test_can_continue(self):
        lc = LoopController(max_iterations=3)
        assert lc.can_continue("loop1") is True
        lc.increment("loop1")
        lc.increment("loop1")
        lc.increment("loop1")
        assert lc.can_continue("loop1") is False

    def test_backoff(self):
        lc = LoopController(max_iterations=5, backoff_base=1.0)
        lc.increment("loop1")
        assert lc.get_backoff_seconds("loop1") == 1.0
        lc.increment("loop1")
        assert lc.get_backoff_seconds("loop1") == 2.0
        lc.increment("loop1")
        assert lc.get_backoff_seconds("loop1") == 4.0

    def test_reset(self):
        lc = LoopController(max_iterations=2)
        lc.increment("loop1")
        lc.increment("loop1")
        assert lc.can_continue("loop1") is False
        lc.reset("loop1")
        assert lc.can_continue("loop1") is True

    def test_independent_loops(self):
        lc = LoopController(max_iterations=2)
        lc.increment("loop1")
        lc.increment("loop1")
        assert lc.can_continue("loop1") is False
        assert lc.can_continue("loop2") is True

    def test_get_status(self):
        lc = LoopController(max_iterations=3)
        lc.increment("loop1")
        status = lc.get_status("loop1")
        assert status["iterations"] == 1
        assert status["can_continue"] is True
        assert status["max_iterations"] == 3


# ── SOPRouter ──────────────────────────────────────────────

class TestSOPRouter:
    def setup_method(self):
        self.router = SOPRouter()

    def test_build_edge_map(self):
        edges = [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c", "condition": "x == 1"},
            {"from": "b", "to": "d", "condition": "x == 2"},
        ]
        edge_map = self.router.build_edge_map(edges)
        assert len(edge_map["a"]) == 1
        assert len(edge_map["b"]) == 2
        assert edge_map["a"][0]["to"] == "b"

    def test_build_edge_map_empty(self):
        assert self.router.build_edge_map([]) == {}

    def test_route_next_unconditional(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        edge_map = {"n1": [{"to": "n2"}]}
        assert self.router.route_next(state, "n1", edge_map) == "n2"

    def test_route_next_no_edges(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        assert self.router.route_next(state, "n1", {}) is None

    def test_route_next_conditional_hitl_approve(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.hitl_result = "approve"
        edge_map = {
            "n2": [
                {"to": "n3", "condition": "hitl_result == approve"},
                {"to": "n1", "condition": "hitl_result == reject"},
            ]
        }
        assert self.router.route_next(state, "n2", edge_map) == "n3"

    def test_route_next_conditional_hitl_reject(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.hitl_result = "reject"
        edge_map = {
            "n2": [
                {"to": "n3", "condition": "hitl_result == approve"},
                {"to": "n1", "condition": "hitl_result == reject"},
            ]
        }
        assert self.router.route_next(state, "n2", edge_map) == "n1"

    def test_route_next_not_condition(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.validations = {"passed": False, "results": []}
        edge_map = {
            "n4": [
                {"to": "n5", "condition": "validations.passed"},
                {"to": "n3", "condition": "not validations.passed"},
            ]
        }
        assert self.router.route_next(state, "n4", edge_map) == "n3"

    def test_route_next_not_condition_passed(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.validations = {"passed": True, "results": []}
        edge_map = {
            "n4": [
                {"to": "n3", "condition": "not validations.passed"},
                {"to": "n5", "condition": "validations.passed"},
            ]
        }
        assert self.router.route_next(state, "n4", edge_map) == "n5"

    def test_resolve_state_field(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.hitl_result = "approve"
        state.retry_count = 3
        state.last_confidence = 0.95
        state.validations = {"passed": True}

        assert self.router.resolve_state_field("hitl_result", state) == "approve"
        assert self.router.resolve_state_field("retry_count", state) == 3
        assert self.router.resolve_state_field("last_confidence", state) == 0.95
        assert self.router.resolve_state_field("validations.passed", state) is True
        assert self.router.resolve_state_field("unknown_field", state) is None


# ── SOPNodeExecutor ────────────────────────────────────────

class TestSOPNodeExecutor:
    def setup_method(self):
        self.executor = SOPNodeExecutor.__new__(SOPNodeExecutor)
        self.executor.db = None
        self.executor.team_mgr = None
        self.executor.router = SOPRouter()

    def test_execute_validation_node_pass(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        node = {"id": "v1", "type": "validation", "checks": ["lint", "unit_test"], "pass_threshold": 80}
        self.executor.execute_validation_node(state, node)
        assert state.validations["passed"] is True
        assert len(state.validations["results"]) == 2
        assert all(r["passed"] for r in state.validations["results"])
        assert any("Validation" in m["content"] for m in state.messages)

    def test_execute_validation_node_empty_checks(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        node = {"id": "v1", "type": "validation", "checks": [], "pass_threshold": 80}
        self.executor.execute_validation_node(state, node)
        assert state.validations["passed"] is True

    def test_execute_hitl_node_auto_approve(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        node = {"id": "h1", "type": "hitl", "message": "确认", "config": {"require_human": True}}
        result = self.executor.execute_hitl_node(state, node, auto_approve=True)
        assert result is False
        assert state.hitl_result == "approve"

    def test_execute_hitl_node_require_human_false(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        node = {
            "id": "h1", "type": "hitl", "message": "确认",
            "config": {"require_human": False, "auto_action": "approve"},
        }
        result = self.executor.execute_hitl_node(state, node, auto_approve=False)
        assert result is False
        assert state.hitl_result == "approve"

    def test_execute_hitl_node_condition_auto_approve(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.last_confidence = 0.95
        node = {
            "id": "h1", "type": "hitl", "message": "确认",
            "config": {
                "require_human": True,
                "condition": {
                    "field": "last_confidence",
                    "operator": ">=",
                    "value": 0.8,
                    "auto_action": "approve",
                },
            },
        }
        result = self.executor.execute_hitl_node(state, node, auto_approve=False)
        assert result is False
        assert state.hitl_result == "approve"

    def test_execute_hitl_node_condition_not_met(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        state.last_confidence = 0.5
        node = {
            "id": "h1", "type": "hitl", "message": "确认",
            "config": {
                "require_human": True,
                "condition": {
                    "field": "last_confidence",
                    "operator": ">=",
                    "value": 0.8,
                    "auto_action": "approve",
                },
            },
        }
        result = self.executor.execute_hitl_node(state, node, auto_approve=False)
        assert result is True
        assert state.hitl_pending is True

    def test_execute_hitl_node_human_required(self):
        state = TaskState(task_id="t", sop_id="s", team_id="tm")
        node = {
            "id": "h1", "type": "hitl", "message": "请确认方案",
            "config": {"require_human": True, "timeout": 600},
        }
        result = self.executor.execute_hitl_node(state, node, auto_approve=False)
        assert result is True
        assert state.hitl_pending is True
        assert state.hitl_data["node"] == "h1"
        assert state.hitl_data["message"] == "请确认方案"
        assert state.hitl_data["timeout"] == 600


# ── SOP Service YAML 解析（纯逻辑） ──────────────────────

class TestSOPServiceYAML:
    def test_import_valid_yaml(self):
        import yaml
        yaml_content = """
name: "测试流程"
description: "测试描述"
version: "1.0"
nodes:
  - id: n1
    type: agent_action
    role_slot: coder
  - id: n2
    type: end
edges:
  - from: n1
    to: n2
"""
        data = yaml.safe_load(yaml_content)
        assert data["name"] == "测试流程"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

    def test_import_yaml_missing_node_id(self):
        import yaml
        yaml_content = """
name: "bad"
nodes:
  - type: agent_action
    role_slot: coder
edges: []
"""
        data = yaml.safe_load(yaml_content)
        assert "id" not in data["nodes"][0]

    def test_import_yaml_invalid_type(self):
        import yaml
        yaml_content = """
name: "bad"
nodes:
  - id: n1
    type: invalid_type
edges: []
"""
        data = yaml.safe_load(yaml_content)
        valid_types = {"agent_action", "hitl", "validation", "start", "end", "condition"}
        assert data["nodes"][0]["type"] not in valid_types
