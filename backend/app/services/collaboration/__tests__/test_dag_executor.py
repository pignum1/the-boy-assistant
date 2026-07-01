"""Tests for M6 DAGExecutor and M7 IndependentVerifier.

NOTE: DAGExecutor class removed during M0-M8 refactoring.
DAG execution now flows through m6_dag_executor (routing) + m6_execute_worker.
M7 verifier tests are preserved below.
"""
import pytest
from app.services.collaboration.m7_verifier import (
    parse_verification_result,
    route_after_verify,
    build_verification_prompt,
    VERIFIER_SYSTEM_PROMPT,
)


class TestDAGExecutor:
    @pytest.mark.skip(reason="DAGExecutor class removed in M0-M8 refactoring")
    def test_executor_initializes(self):
        pass

    @pytest.mark.skip(reason="DAGExecutor class removed in M0-M8 refactoring")
    @pytest.mark.asyncio
    async def test_execute_empty_plan(self):
        pass

    @pytest.mark.skip(reason="DAGExecutor class removed in M0-M8 refactoring")
    @pytest.mark.asyncio
    async def test_execute_plan_with_cycle(self):
        pass

    @pytest.mark.skip(reason="DAGExecutor class removed in M0-M8 refactoring")
    @pytest.mark.asyncio
    async def test_single_task_executes(self):
        pass

    @pytest.mark.skip(reason="DAGExecutor class removed in M0-M8 refactoring")
    @pytest.mark.asyncio
    async def test_parallel_tasks_executed_concurrently(self):
        pass


class TestIndependentVerifier:
    def test_parse_clean_json(self):
        raw = '{"passed":true,"severity":"none"}'
        r = parse_verification_result(raw)
        assert r["passed"] is True

    def test_parse_json_in_markdown(self):
        raw = '''分析完成
```json
{"passed":false,"feedback":"JWT过期设置错误","severity":"major","drift_detected":true}
```'''
        r = parse_verification_result(raw)
        assert r["passed"] is False
        assert r["severity"] == "major"

    def test_fallback_to_raw(self):
        r = parse_verification_result("not json at all")
        assert r["passed"] is False

    def test_route_pass_to_complete(self):
        assert route_after_verify({"passed": True}) == "pass"

    def test_route_critical_to_escalate(self):
        assert route_after_verify({"passed": False, "severity": "critical"}) == "escalate"

    def test_route_major_to_retry(self):
        assert route_after_verify({"passed": False, "severity": "major"}) == "retry"

    def test_route_minor_to_pass(self):
        assert route_after_verify({"passed": False, "severity": "minor"}) == "pass"

    def test_verification_prompt_excludes_reasoning(self):
        prompt = build_verification_prompt("登录系统需求", {"task_1": "代码..."})
        assert "登录系统需求" in prompt
        assert "思考过程" not in prompt  # No worker reasoning info
        assert "推理" not in prompt
        assert "为什么" not in prompt

    def test_system_prompt_enforces_blind_review(self):
        assert "你看不到" in VERIFIER_SYSTEM_PROMPT
        assert "确认偏差" in VERIFIER_SYSTEM_PROMPT
