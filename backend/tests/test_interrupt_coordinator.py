"""PR5 · interrupt_coordinator + m1_rebalance 测试"""

import pytest

from app.services.collaboration.interrupt_coordinator import InterruptCoordinator
from app.services.collaboration.m1_rebalance import (
    apply_delta_to_task_dag,
    _heuristic_delta,
    _extract_json,
)


class TestInterruptCoordinator:
    """InterruptCoordinator 介入协调器"""

    def test_request_and_consume(self):
        c = InterruptCoordinator()
        sid = "sess-1"
        assert not c.has_pending(sid)
        c.request_interrupt(sid, "soft", "改用 MySQL")
        assert c.has_pending(sid)
        req = c.consume(sid)
        assert req is not None
        assert req.mode == "soft"
        assert req.message == "改用 MySQL"
        # 消费后清空
        assert not c.has_pending(sid)
        assert c.consume(sid) is None

    def test_latest_wins(self):
        c = InterruptCoordinator()
        sid = "sess-2"
        c.request_interrupt(sid, "soft", "第一次")
        c.request_interrupt(sid, "hard", "第二次")
        req = c.peek(sid)
        assert req.mode == "hard"
        assert req.message == "第二次"

    def test_hard_sets_paused(self):
        c = InterruptCoordinator()
        sid = "sess-3"
        c.request_interrupt(sid, "hard", "")
        assert c.is_paused(sid) is True
        c.resume(sid)
        assert c.is_paused(sid) is False

    def test_soft_does_not_pause(self):
        c = InterruptCoordinator()
        sid = "sess-4"
        c.request_interrupt(sid, "soft", "改改")
        assert c.is_paused(sid) is False

    def test_session_isolation(self):
        c = InterruptCoordinator()
        c.request_interrupt("a", "soft", "msg-a")
        c.request_interrupt("b", "hard", "msg-b")
        assert c.peek("a").mode == "soft"
        assert c.peek("b").mode == "hard"
        c.consume("a")
        assert not c.has_pending("a")
        assert c.has_pending("b")

    def test_clear(self):
        c = InterruptCoordinator()
        sid = "sess-5"
        c.request_interrupt(sid, "hard", "x")
        c.clear(sid)
        assert not c.has_pending(sid)
        assert not c.is_paused(sid)


class TestApplyDeltaToTaskDag:
    """delta_plan 应用到 task_dag 的纯函数"""

    @pytest.fixture
    def base_dag(self):
        return {
            "phases": [
                {
                    "id": "p1",
                    "name": "PRD",
                    "tasks": [
                        {"id": "T1.1", "title": "故事", "assigned_role": "pm", "version": 1},
                        {"id": "T1.2", "title": "验收", "assigned_role": "pm", "version": 1},
                    ],
                },
                {
                    "id": "p2",
                    "name": "架构",
                    "tasks": [
                        {"id": "T2.1", "title": "schema", "assigned_role": "arch", "version": 1},
                    ],
                },
            ],
        }

    def test_keep_untouched(self, base_dag):
        delta = {"keep": ["T1.1"], "modify": [], "add": [], "cancel": []}
        new_dag = apply_delta_to_task_dag(base_dag, delta)
        t1 = new_dag["phases"][0]["tasks"][0]
        assert t1["id"] == "T1.1"
        assert "status" not in t1 or t1["status"] not in ("modified", "cancelled")

    def test_modify_bumps_version(self, base_dag):
        delta = {
            "keep": ["T1.1"],
            "modify": [{"task_id": "T2.1", "reason": "MySQL", "new_version": 2}],
            "add": [],
            "cancel": [],
        }
        new_dag = apply_delta_to_task_dag(base_dag, delta)
        t = new_dag["phases"][1]["tasks"][0]
        assert t["status"] == "modified"
        assert t["version"] == 2
        assert t["modify_reason"] == "MySQL"

    def test_cancel_marks_cancelled(self, base_dag):
        delta = {
            "keep": [],
            "modify": [],
            "add": [],
            "cancel": [{"task_id": "T1.2", "reason": "已不需要"}],
        }
        new_dag = apply_delta_to_task_dag(base_dag, delta)
        t = new_dag["phases"][0]["tasks"][1]
        assert t["status"] == "cancelled"
        assert "已不需要" in t["cancel_reason"]

    def test_add_to_existing_phase(self, base_dag):
        delta = {
            "keep": [],
            "modify": [],
            "add": [{"id": "T2.2", "phase_id": "p2", "name": "新增任务", "assigned_role": "arch"}],
            "cancel": [],
        }
        new_dag = apply_delta_to_task_dag(base_dag, delta)
        p2_tasks = new_dag["phases"][1]["tasks"]
        assert len(p2_tasks) == 2
        new_task = p2_tasks[-1]
        assert new_task["id"] == "T2.2"
        assert new_task["status"] == "new"

    def test_add_creates_new_phase_if_not_exists(self, base_dag):
        delta = {
            "keep": [],
            "modify": [],
            "add": [{"id": "T_extra", "phase_id": "p99", "name": "ghost", "assigned_role": "x"}],
            "cancel": [],
        }
        new_dag = apply_delta_to_task_dag(base_dag, delta)
        # 原 phases 数量 + 1
        assert len(new_dag["phases"]) == 3
        new_phase = new_dag["phases"][-1]
        assert new_phase["id"] == "p99"
        assert new_phase["tasks"][0]["id"] == "T_extra"

    def test_does_not_mutate_input(self, base_dag):
        before = str(base_dag)
        apply_delta_to_task_dag(base_dag, {"keep": [], "modify": [{"task_id": "T1.1", "reason": "x", "new_version": 9}], "add": [], "cancel": []})
        assert str(base_dag) == before


class TestHeuristicDelta:
    """LLM 失败时的兜底逻辑"""

    def test_keeps_completed_marks_pending_modify(self):
        delta = _heuristic_delta(
            interrupt_message="changes",
            completed=[{"id": "T1.1"}, {"id": "T1.2"}],
            pending=[{"id": "T2.1"}],
        )
        assert delta["keep"] == ["T1.1", "T1.2"]
        assert len(delta["modify"]) == 1
        assert delta["modify"][0]["task_id"] == "T2.1"
        assert delta["add"] == []
        assert delta["cancel"] == []
        assert "changes" in delta["summary"] or delta["summary"]


class TestExtractJson:
    """LLM 输出 JSON 提取"""

    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_with_code_fence(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_with_prefix_suffix(self):
        text = '这是 delta：\n{"keep": [], "add": []}\n以上'
        result = _extract_json(text)
        assert result == {"keep": [], "add": []}

    def test_invalid_returns_none(self):
        assert _extract_json("not json at all") is None
        assert _extract_json("") is None
