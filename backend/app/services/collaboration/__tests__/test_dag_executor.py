"""Tests for M6 DAGExecutor and M7 IndependentVerifier."""
import pytest
from app.services.collaboration.dag_executor import DAGExecutor
from app.services.collaboration.independent_verifier import (
    parse_verification_result,
    route_after_verify,
    build_verification_prompt,
    VERIFIER_SYSTEM_PROMPT,
)


class TestDAGExecutor:
    def test_executor_initializes(self):
        executor = DAGExecutor()
        assert executor is not None
        assert executor.context_pipeline is not None

    @pytest.mark.asyncio
    async def test_execute_empty_plan(self):
        async def mock_chat(agent_role, prompt):
            return "ok"

        executor = DAGExecutor()
        result = await executor.execute_plan(
            plan={"phases": []},
            requirements="test",
            agent_chat_fn=mock_chat,
        )
        assert result["artifacts"] == {}
        assert result["files_changed"] == []
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_execute_plan_with_cycle(self):
        async def mock_chat(agent_role, prompt):
            return "ok"

        executor = DAGExecutor()
        result = await executor.execute_plan(
            plan={
                "phases": [{
                    "id": "p1",
                    "tasks": [
                        {"id": "a", "title": "A", "depends_on": ["b"]},
                        {"id": "b", "title": "B", "depends_on": ["a"]},
                    ],
                }],
            },
            requirements="test",
            agent_chat_fn=mock_chat,
        )
        assert len(result["errors"]) > 0  # Cycle detected

    @pytest.mark.asyncio
    async def test_single_task_executes(self):
        called_with = []

        async def mock_chat(agent_role, prompt):
            called_with.append((agent_role, prompt))
            return {"output": "done", "files": [{"name": "out.py", "status": "created", "meta": "+10"}]}

        executor = DAGExecutor()
        result = await executor.execute_plan(
            plan={
                "phases": [{
                    "id": "p1",
                    "tasks": [{
                        "id": "t1",
                        "title": "一个任务",
                        "description": "做某事",
                        "assigned_role": "backend_dev",
                        "depends_on": [],
                    }],
                }],
            },
            requirements="测试需求",
            agent_chat_fn=mock_chat,
        )
        assert len(called_with) == 1
        assert result["artifacts"].get("t1") == "done"
        assert len(result["files_changed"]) == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_parallel_tasks_executed_concurrently(self):
        import asyncio
        started = []

        async def mock_chat(agent_role, prompt):
            started.append(agent_role)
            await asyncio.sleep(0.001)
            return {"output": agent_role}

        executor = DAGExecutor()
        result = await executor.execute_plan(
            plan={
                "phases": [{
                    "id": "p1",
                    "tasks": [
                        {"id": "t1", "title": "A", "assigned_role": "backend_dev", "depends_on": []},
                        {"id": "t2", "title": "B", "assigned_role": "frontend_dev", "depends_on": []},
                    ],
                }],
            },
            requirements="test",
            agent_chat_fn=mock_chat,
        )
        assert len(started) == 2
        assert result["errors"] == []


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
        assert route_after_verify({"passed": True}) == "complete"

    def test_route_critical_to_escalate(self):
        assert route_after_verify({"passed": False, "severity": "critical"}) == "escalate"

    def test_route_major_to_retry(self):
        assert route_after_verify({"passed": False, "severity": "major"}) == "retry"

    def test_route_minor_to_complete(self):
        assert route_after_verify({"passed": False, "severity": "minor"}) == "complete"

    def test_verification_prompt_excludes_reasoning(self):
        prompt = build_verification_prompt("登录系统需求", {"task_1": "代码..."})
        assert "登录系统需求" in prompt
        assert "任务" not in prompt.lower()  # No reasoning info
        assert "思考" not in prompt

    def test_system_prompt_enforces_blind_review(self):
        assert "你看不到" in VERIFIER_SYSTEM_PROMPT
        assert "确认偏差" in VERIFIER_SYSTEM_PROMPT
