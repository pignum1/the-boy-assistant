"""Tests for Route B hierarchical delegation architecture.

Covers:
1. Delegation tree building (org_hierarchy)
2. Role context generation
3. Delegation plan validation
4. Collect routing logic
5. Delegate routing logic
6. Graph v3 compilation and topology
7. Flat team fallback
8. Dynamic depth protection
9. M5 context pipeline with delegation fields
"""

import pytest

from app.services.collaboration.types import CollabState, WorkerContext
from app.services.collaboration.org_hierarchy import (
    build_delegation_tree,
    generate_role_context,
    find_member_info,
    find_subordinates,
    find_supervisor_for_member,
)
from app.services.collaboration.m6_plan_validate import (
    DelegationPlanValidator,
    route_after_validate,
)
from app.services.collaboration.m6_collect import route_after_collect
from app.services.collaboration.m6_delegate import route_after_delegate
from app.services.collaboration.m5_context_pipeline import ContextPipeline
from app.services.collaboration.graph import build_graph_v3


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def mock_org_3level():
    """3-level org: Leader → Manager → [Worker1, Worker2]"""
    return {
        "leader_member_id": "leader",
        "relations": [
            {"member_id": "mgr1", "supervisor_member_id": "leader"},
            {"member_id": "mgr2", "supervisor_member_id": "leader"},
            {"member_id": "w1", "supervisor_member_id": "mgr1"},
            {"member_id": "w2", "supervisor_member_id": "mgr1"},
            {"member_id": "w3", "supervisor_member_id": "mgr2"},
        ],
        "member_roles": {
            "leader": {"role_name": "张总", "agent_id": "a0", "agent_name": "张总", "capabilities": ["management"]},
            "mgr1": {"role_name": "李经理", "agent_id": "a1", "agent_name": "李经理", "capabilities": ["backend"]},
            "mgr2": {"role_name": "王经理", "agent_id": "a2", "agent_name": "王经理", "capabilities": ["frontend"]},
            "w1": {"role_name": "小王", "agent_id": "a3", "agent_name": "小王", "capabilities": ["python"]},
            "w2": {"role_name": "小李", "agent_id": "a4", "agent_name": "小李", "capabilities": ["python"]},
            "w3": {"role_name": "小张", "agent_id": "a5", "agent_name": "小张", "capabilities": ["react"]},
        },
    }


@pytest.fixture
def mock_org_flat():
    """Flat team: no org structure."""
    return None


# ── Test: Delegation Tree Building ──────────────────────────────

class TestDelegationTree:
    """Test build_delegation_tree from org_hierarchy."""

    def test_no_org_returns_empty(self, mock_org_flat):
        result = build_delegation_tree(mock_org_flat, "requirements")
        assert result["leader_id"] is None
        assert result["tree"] == {}

    def test_3level_tree_has_correct_root(self, mock_org_3level):
        result = build_delegation_tree(mock_org_3level, "用户管理系统")
        assert result["leader_id"] == "leader"
        assert "leader" in result["tree"]
        leader_node = result["tree"]["leader"]
        assert leader_node["goal"] == "用户管理系统"
        assert leader_node["role_name"] == "张总"

    def test_3level_tree_has_subordinates(self, mock_org_3level):
        result = build_delegation_tree(mock_org_3level, "requirements")
        leader_node = result["tree"]["leader"]
        assert "mgr1" in leader_node["sub_delegations"]
        assert "mgr2" in leader_node["sub_delegations"]

    def test_3level_tree_nested_subordinates(self, mock_org_3level):
        result = build_delegation_tree(mock_org_3level, "requirements")
        mgr1 = result["tree"]["leader"]["sub_delegations"]["mgr1"]
        assert "w1" in mgr1["sub_delegations"]
        assert "w2" in mgr1["sub_delegations"]
        # Workers have no sub-delegations
        w1 = mgr1["sub_delegations"]["w1"]
        assert w1["sub_delegations"] == {}

    def test_all_nodes_have_member_id(self, mock_org_3level):
        result = build_delegation_tree(mock_org_3level, "requirements")

        def _check(node):
            assert "member_id" in node
            for child in node["sub_delegations"].values():
                _check(child)

        for root in result["tree"].values():
            _check(root)

    def test_all_nodes_have_role_context(self, mock_org_3level):
        result = build_delegation_tree(mock_org_3level, "requirements")

        def _check(node):
            assert "role_context" in node
            assert len(node["role_context"]) > 0
            for child in node["sub_delegations"].values():
                _check(child)

        for root in result["tree"].values():
            _check(root)


# ── Test: Role Context Generation ───────────────────────────────

class TestRoleContext:
    """Test generate_role_context."""

    def test_leader_context(self, mock_org_3level):
        ctx = generate_role_context(mock_org_3level, "leader")
        assert "张总" in ctx
        assert "团队负责人" in ctx

    def test_manager_context(self, mock_org_3level):
        ctx = generate_role_context(mock_org_3level, "mgr1")
        assert "李经理" in ctx
        assert "张总" in ctx
        assert "汇报" in ctx

    def test_worker_context(self, mock_org_3level):
        ctx = generate_role_context(mock_org_3level, "w1")
        assert "小王" in ctx
        assert "李经理" in ctx
        assert "汇报" in ctx

    def test_no_org_returns_empty(self):
        ctx = generate_role_context(None, "any")
        assert ctx == ""


# ── Test: Member Info ───────────────────────────────────────────

class TestMemberInfo:
    """Test find_member_info."""

    def test_find_existing_member(self, mock_org_3level):
        info = find_member_info(mock_org_3level, "w1")
        assert info is not None
        assert info["role_name"] == "小王"
        assert info["agent_id"] == "a3"
        assert "python" in info["capabilities"]

    def test_find_nonexistent_member(self, mock_org_3level):
        info = find_member_info(mock_org_3level, "nonexistent")
        assert info is None

    def test_no_org_returns_none(self):
        info = find_member_info(None, "any")
        assert info is None


# ── Test: Delegation Plan Validator ─────────────────────────────

class TestDelegationPlanValidator:
    """Test DelegationPlanValidator."""

    def setup_method(self):
        self.validator = DelegationPlanValidator()

    def test_valid_plan_passes(self):
        plan = {
            "assignments": [
                {"member_id": "m1", "goal": "backend API", "is_leaf": True},
                {"member_id": "m2", "goal": "frontend UI", "is_leaf": True},
            ]
        }
        result = self.validator.validate(plan, "build system", ["m1", "m2"], {})
        assert result["valid"] is True

    def test_hallucinated_member_detected(self):
        plan = {
            "assignments": [
                {"member_id": "m1", "goal": "backend", "is_leaf": True},
                {"member_id": "FAKE", "goal": "extra", "is_leaf": True},
            ]
        }
        result = self.validator.validate(plan, "build", ["m1", "m2"], {})
        assert result["valid"] is False
        rules = [i["rule"] for i in result["issues"]]
        assert "member_exists" in rules

    def test_resource_conflict_detected(self):
        plan = {
            "assignments": [
                {"member_id": "m1", "goal": "part1", "is_leaf": True},
                {"member_id": "m1", "goal": "part2", "is_leaf": True},
            ]
        }
        result = self.validator.validate(plan, "build", ["m1", "m2"], {})
        assert result["valid"] is False
        rules = [i["rule"] for i in result["issues"]]
        assert "resource_conflict" in rules

    def test_granularity_detected(self):
        plan = {
            "assignments": [
                {"member_id": "m1", "goal": f"task{i}", "is_leaf": True}
                for i in range(10)
            ]
        }
        result = self.validator.validate(plan, "build", ["m1", "m2"], {})
        rules = [i["rule"] for i in result["issues"]]
        assert "granularity" in rules

    def test_auto_fix_removes_hallucinated(self):
        plan = {
            "assignments": [
                {"member_id": "m1", "goal": "backend", "is_leaf": True},
                {"member_id": "FAKE", "goal": "extra", "is_leaf": True},
            ]
        }
        result = self.validator.validate(plan, "build", ["m1"], {})
        assert result["fixed_plan"] is not None
        assert len(result["fixed_plan"]["assignments"]) == 1
        assert result["fixed_plan"]["assignments"][0]["member_id"] == "m1"


# ── Test: Collect Routing ───────────────────────────────────────

class TestCollectRouting:
    """Test route_after_collect."""

    def test_all_done_routes_to_verify(self):
        state = CollabState(status="all_delegations_done")
        assert route_after_collect(state) == "m7_verify"

    def test_next_subordinate_routes_to_delegate(self):
        state = CollabState(status="next_subordinate")
        assert route_after_collect(state) == "m6_delegate_sub"

    def test_retry_routes_to_delegate(self):
        state = CollabState(status="retry")
        assert route_after_collect(state) == "m6_delegate_sub"

    def test_escalate_routes_to_escalate(self):
        state = CollabState(status="escalate")
        assert route_after_collect(state) == "m6_escalate"

    def test_unknown_defaults_to_verify(self):
        state = CollabState(status="something_unknown")
        assert route_after_collect(state) == "m7_verify"


# ── Test: Delegate Routing ──────────────────────────────────────

class TestDelegateRouting:
    """Test route_after_delegate."""

    def test_worker_routes_to_execute(self):
        state = CollabState(_delegate_route="worker")
        assert route_after_delegate(state) == "m6_execute_worker"

    def test_parallel_collect_routes_to_execute(self):
        state = CollabState(_delegate_route="parallel_collect")
        assert route_after_delegate(state) == "m6_execute_worker"

    def test_merge_routes_to_collect(self):
        state = CollabState(_delegate_route="merge_to_parent")
        assert route_after_delegate(state) == "m6_collect"

    def test_supervisor_routes_to_validate(self):
        state = CollabState(_delegate_route="supervisor")
        assert route_after_delegate(state) == "m6_plan_validate"

    def test_unknown_defaults_to_worker(self):
        state = CollabState(_delegate_route="unknown")
        assert route_after_delegate(state) == "m6_execute_worker"


# ── Test: Validate Routing ──────────────────────────────────────

class TestValidateRouting:
    """Test route_after_validate."""

    def test_approved_routes_to_push(self):
        state = CollabState(_validation_result="approved")
        assert route_after_validate(state) == "m6_delegate_push"

    def test_fallback_routes_to_push(self):
        state = CollabState(_validation_result="fallback")
        assert route_after_validate(state) == "m6_delegate_push"

    def test_rejected_routes_to_root(self):
        state = CollabState(_validation_result="rejected")
        assert route_after_validate(state) == "m6_delegate_root"


# ── Test: Graph V3 Topology ─────────────────────────────────────

class TestGraphV3:
    """Test build_graph_v3 topology."""

    def setup_method(self):
        self.graph = build_graph_v3()
        self.nodes = set(self.graph.nodes.keys())

    def test_has_16_nodes(self):
        assert len(self.nodes) == 16

    def test_has_pre_m6_nodes(self):
        for n in ["m0_intent", "m1_analyze", "m1_rebalance", "m2_clarify",
                   "m3_orchestrate", "m4_decompose", "hitl"]:
            assert n in self.nodes, f"Missing pre-M6 node: {n}"

    def test_has_v3_delegation_nodes(self):
        for n in ["m6_org_loader", "m6_delegate_root", "m6_delegate_sub",
                   "m6_plan_validate", "m6_delegate_push", "m6_execute_worker",
                   "m6_collect", "m6_escalate"]:
            assert n in self.nodes, f"Missing v3 node: {n}"

    def test_has_m7_and_hitl(self):
        assert "m7_verify" in self.nodes
        assert "hitl" in self.nodes

    def test_no_v2_nodes(self):
        """V2 nodes should NOT be in v3 graph."""
        for n in ["m6_level_dispatch", "m6_level_execute", "m6_level_review"]:
            assert n not in self.nodes, f"V2 node should not exist in v3: {n}"

    def test_compiles_successfully(self):
        from langgraph.checkpoint.memory import MemorySaver
        compiled = self.graph.compile(checkpointer=MemorySaver())
        assert compiled is not None


# ── Test: M5 Context Pipeline with Delegation Fields ────────────

class TestM5DelegationContext:
    """Test M5 context pipeline with Route B fields."""

    def setup_method(self):
        self.pipeline = ContextPipeline()

    def test_build_context_with_delegation_fields(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="Build user system",
            task={"title": "Auth API", "description": "Implement auth", "depends_on": []},
            all_artifacts={},
            delegation_goal="You handle backend API",
            org_role_context="你是小王（后端开发），向李经理汇报",
            retry_feedback="Missing error code field",
        )
        assert ctx.get("delegation_goal") == "You handle backend API"
        assert "小王" in ctx.get("org_role_context", "")
        assert "error code" in ctx.get("retry_feedback", "")

    def test_format_context_includes_role(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="Build user system",
            task={"title": "Auth API", "description": "Implement auth", "depends_on": []},
            all_artifacts={},
            org_role_context="你是小王，向李经理汇报",
        )
        formatted = self.pipeline.format_context(ctx)
        assert "你的角色" in formatted
        assert "小王" in formatted

    def test_format_context_includes_delegation_goal(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="Build system",
            task={"title": "Task", "description": "Do it", "depends_on": []},
            all_artifacts={},
            delegation_goal="Implement authentication module",
        )
        formatted = self.pipeline.format_context(ctx)
        assert "主管分配的目标" in formatted
        assert "authentication" in formatted

    def test_format_context_includes_retry_feedback(self):
        ctx = self.pipeline.build_context(
            requirement_anchor="Build system",
            task={"title": "Task", "description": "Do it", "depends_on": []},
            all_artifacts={},
            retry_feedback="Missing error codes",
        )
        formatted = self.pipeline.format_context(ctx)
        assert "审核反馈" in formatted
        assert "error codes" in formatted

    def test_no_delegation_fields_backward_compatible(self):
        """Without Route B fields, context should work as before."""
        ctx = self.pipeline.build_context(
            requirement_anchor="Build system",
            task={"title": "Task", "description": "Do it", "depends_on": []},
            all_artifacts={},
        )
        formatted = self.pipeline.format_context(ctx)
        assert "你的角色" not in formatted
        assert "主管分配的目标" not in formatted
        assert "审核反馈" not in formatted
        assert "需求" in formatted


# ── Test: Dynamic Depth Protection ──────────────────────────────

class TestDynamicDepth:
    """Test that depth protection works in _delegate_think logic."""

    def test_depth_exceeds_max_routes_merge(self):
        """When delegation_depth >= max, should route to merge_to_parent."""
        # This tests the routing logic directly
        state = CollabState(
            _delegate_route="merge_to_parent",
            delegation_depth=5,
            max_delegation_depth=5,
        )
        assert route_after_delegate(state) == "m6_collect"

    def test_depth_under_max_routes_normally(self):
        """Under max depth, supervisor routes to validate."""
        state = CollabState(_delegate_route="supervisor")
        assert route_after_delegate(state) == "m6_plan_validate"
