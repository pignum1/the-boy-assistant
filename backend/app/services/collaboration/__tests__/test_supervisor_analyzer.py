"""Tests for M1 SupervisorAnalyzer."""
import pytest
from app.services.collaboration.m1_requirement_analyzer import (
    build_analysis_prompt,
    parse_supervisor_output,
    validate_supervisor_output,
    supervisor_decision_to_state,
    SUPERVISOR_SYSTEM_PROMPT,
)


class TestParseSupervisorOutput:
    def test_parse_clean_json(self):
        raw = '{"action":"need_confirm","summary":"test","problem_type":"feature_request","complexity":"medium","required_roles":["architect"]}'
        result = parse_supervisor_output(raw)
        assert result["action"] == "need_confirm"
        assert result["required_roles"] == ["architect"]

    def test_parse_json_in_code_block(self):
        raw = '''```json
{"action": "need_clarify", "questions": ["用什么框架?"]}
```'''
        result = parse_supervisor_output(raw)
        assert result["action"] == "need_clarify"
        assert "用什么框架?" in result["questions"]

    def test_parse_json_with_markdown(self):
        raw = '''分析完成。

```json
{
  "action": "execute_task",
  "tasks": [{"id":"t1","title":"test","assigned_role":"backend_dev"}]
}
```'''
        result = parse_supervisor_output(raw)
        assert result["action"] == "execute_task"
        assert len(result["tasks"]) == 1

    def test_parse_embedded_json(self):
        raw = 'some text {"action":"done"} more text'
        result = parse_supervisor_output(raw)
        assert result["action"] == "done"

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_supervisor_output("not json at all")


class TestValidateSupervisorOutput:
    def test_need_clarify_requires_questions(self):
        errors = validate_supervisor_output({"action": "need_clarify"})
        assert len(errors) > 0

    def test_need_clarify_valid(self):
        errors = validate_supervisor_output({
            "action": "need_clarify",
            "questions": ["问题1", "问题2"],
            "clarity_score": 0.5,
        })
        assert len(errors) == 0

    def test_need_confirm_requires_all_fields(self):
        errors = validate_supervisor_output({"action": "need_confirm"})
        assert len(errors) > 0

    def test_need_confirm_valid(self):
        errors = validate_supervisor_output({
            "action": "need_confirm",
            "problem_type": "feature_request",
            "complexity": "medium",
            "summary": "登录系统",
            "required_roles": ["backend_dev"],
            "clarity_score": 0.85,
        })
        assert len(errors) == 0

    def test_execute_task_requires_tasks(self):
        errors = validate_supervisor_output({"action": "execute_task"})
        assert len(errors) > 0

    def test_execute_task_valid(self):
        errors = validate_supervisor_output({
            "action": "execute_task",
            "tasks": [{
                "id": "t1",
                "title": "任务",
                "assigned_role": "backend_dev",
            }],
        })
        assert len(errors) == 0

    def test_execute_task_missing_role(self):
        errors = validate_supervisor_output({
            "action": "execute_task",
            "tasks": [{"id": "t1", "title": "任务"}],
        })
        assert len(errors) > 0

    def test_unknown_action(self):
        errors = validate_supervisor_output({"action": "invalid_action"})
        assert len(errors) > 0

    def test_missing_action(self):
        errors = validate_supervisor_output({})
        assert len(errors) > 0


class TestDecisionToState:
    def test_clarify_sets_hitl(self):
        updates = supervisor_decision_to_state({
            "action": "need_clarify",
            "questions": ["用什么框架?"],
        })
        assert updates["status"] == "clarifying"
        assert updates["hitl_type"] == "clarification"
        assert "用什么框架?" in updates["hitl_message"]

    def test_confirm_sets_plan(self):
        updates = supervisor_decision_to_state({
            "action": "need_confirm",
            "problem_type": "feature_request",
            "complexity": "medium",
            "summary": "登录系统",
            "phases": [{"name": "实现", "role": "backend_dev", "goal": "API"}],
            "required_roles": ["backend_dev"],
        })
        assert updates["status"] == "awaiting_confirm"
        assert updates["hitl_type"] == "confirmation"
        assert len(updates["hitl_options"]) == 3  # confirm/modify/reject

    def test_low_clarity_adds_warning(self):
        updates = supervisor_decision_to_state({
            "action": "need_confirm",
            "problem_type": "feature_request",
            "complexity": "medium",
            "summary": "test",
            "required_roles": ["architect"],
            "clarity_score": 0.5,
        })
        assert "⚠️" in updates["hitl_message"]

    def test_execute_task_sets_plan(self):
        updates = supervisor_decision_to_state({
            "action": "execute_task",
            "tasks": [{
                "id": "t1",
                "title": "实现API",
                "assigned_role": "backend_dev",
                "depends_on": [],
            }],
            "guidance": "使用FastAPI",
        })
        assert updates["status"] == "executing"
        assert "task_dag" in updates
        assert updates["requirements_anchor"] == "使用FastAPI"

    def test_invite_agent_sets_hitl(self):
        updates = supervisor_decision_to_state({
            "action": "invite_agent",
            "hitl_message": "缺少测试员",
        })
        assert updates["hitl_type"] == "agent_invite"
        assert len(updates["hitl_options"]) == 3

    def test_done_sets_completed(self):
        updates = supervisor_decision_to_state({"action": "done"})
        assert updates["status"] == "completed"


class TestSystemPrompt:
    def test_prompt_contains_core_actions(self):
        prompt = SUPERVISOR_SYSTEM_PROMPT
        assert "need_clarify" in prompt
        assert "need_confirm" in prompt
        assert "analysis_report" in prompt
        assert "phases" in prompt

    def test_prompt_contains_core_principles(self):
        prompt = SUPERVISOR_SYSTEM_PROMPT
        assert "详尽优于简洁" in prompt
        assert "具体优于抽象" in prompt
        assert "需求洞察" in prompt
        assert "尽量确认而非澄清" in prompt


class TestBuildPrompt:
    def test_includes_user_message(self):
        prompt = build_analysis_prompt("做登录系统", "pm, architect", "")
        assert "做登录系统" in prompt
        assert "pm, architect" in prompt

    def test_includes_context(self):
        prompt = build_analysis_prompt("确认", "pm", "上一轮: 需求澄清")
        assert "需求澄清" in prompt
