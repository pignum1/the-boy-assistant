"""Observer 模块单元测试：TraceManager + TokenTracker"""

import pytest

from app.services.observer.trace import TraceManager
from app.services.observer.token_tracker import TokenTracker


# ── TraceManager 测试 ──────────────────────────────────────

class TestTraceManager:
    def setup_method(self):
        self.tm = TraceManager()

    def test_start_trace_returns_id(self):
        trace_id = self.tm.start_trace("task-001")
        assert trace_id
        assert isinstance(trace_id, str)

    def test_start_span_returns_id(self):
        trace_id = self.tm.start_trace("task-002")
        span_id = self.tm.start_span(trace_id, name="node-1")
        assert span_id
        assert isinstance(span_id, str)

    def test_end_span(self):
        trace_id = self.tm.start_trace("task-003")
        span_id = self.tm.start_span(trace_id, name="node-1")
        assert self.tm.end_span(span_id) is True

    def test_end_span_not_found(self):
        assert self.tm.end_span("nonexistent") is False

    def test_end_trace(self):
        trace_id = self.tm.start_trace("task-004")
        assert self.tm.end_trace(trace_id) is True

    def test_end_trace_not_found(self):
        assert self.tm.end_trace("nonexistent") is False

    def test_get_trace_tree(self):
        trace_id = self.tm.start_trace("task-005")
        span1 = self.tm.start_span(trace_id, name="root")
        span2 = self.tm.start_span(trace_id, name="child", parent_span_id=span1)
        self.tm.end_span(span2)
        self.tm.end_span(span1)
        self.tm.end_trace(trace_id)

        tree = self.tm.get_trace_tree(trace_id)
        assert tree is not None
        assert tree["trace_id"] == trace_id
        assert tree["status"] == "completed"
        assert "root" in tree
        assert tree["root"]["name"] == "root"
        assert "children" in tree["root"]
        assert tree["root"]["children"][0]["name"] == "child"

    def test_get_trace_by_task(self):
        trace_id = self.tm.start_trace("task-006")
        self.tm.end_trace(trace_id)
        found = self.tm.get_trace_by_task("task-006")
        assert found is not None
        assert found["trace_id"] == trace_id

    def test_get_trace_not_found(self):
        assert self.tm.get_trace_tree("nonexistent") is None
        assert self.tm.get_trace_by_task("nonexistent") is None

    def test_span_hierarchy(self):
        trace_id = self.tm.start_trace("task-007")
        s1 = self.tm.start_span(trace_id, name="level1")
        s2 = self.tm.start_span(trace_id, name="level2", parent_span_id=s1)
        s3 = self.tm.start_span(trace_id, name="level3", parent_span_id=s2)
        self.tm.end_span(s3)
        self.tm.end_span(s2)
        self.tm.end_span(s1)
        self.tm.end_trace(trace_id)

        tree = self.tm.get_trace_tree(trace_id)
        assert tree["root"]["name"] == "level1"
        assert tree["root"]["children"][0]["name"] == "level2"
        assert tree["root"]["children"][0]["children"][0]["name"] == "level3"

    def test_active_traces_count(self):
        self.tm.start_trace("task-a")
        self.tm.start_trace("task-b")
        assert self.tm.active_traces == 2

    def test_total_spans_count(self):
        trace_id = self.tm.start_trace("task-008")
        self.tm.start_span(trace_id, name="s1")
        self.tm.start_span(trace_id, name="s2")
        assert self.tm.total_spans == 2

    def test_end_trace_closes_active_spans(self):
        trace_id = self.tm.start_trace("task-009")
        span_id = self.tm.start_span(trace_id, name="orphan")
        self.tm.end_trace(trace_id)
        tree = self.tm.get_trace_tree(trace_id)
        assert tree["root"]["status"] == "completed"


# ── TokenTracker 测试 ──────────────────────────────────────

class TestTokenTracker:
    def setup_method(self):
        self.tt = TokenTracker()

    def test_record_usage(self):
        record = self.tt.record(
            trace_id="tr-001",
            span_id="sp-001",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert record.total_tokens == 150
        assert record.cost_usd > 0

    def test_get_usage_by_trace(self):
        self.tt.record("tr-002", "sp-1", "gpt-4o", "openai", 100, 50)
        self.tt.record("tr-002", "sp-2", "gpt-4o", "openai", 200, 100)
        result = self.tt.get_usage_by_trace("tr-002")
        assert result["total_calls"] == 2
        assert result["total_tokens"] == 450

    def test_get_usage_summary(self):
        self.tt.record("tr-003", "sp-1", "gpt-4o", "openai", 100, 50)
        self.tt.record("tr-003", "sp-2", "claude-sonnet-4-6", "anthropic", 200, 100)
        summary = self.tt.get_usage_summary()
        assert summary["total_tokens"] == 450
        assert summary["cost_usd"] > 0
        assert len(summary["by_model"]) == 2

    def test_get_usage_by_model(self):
        self.tt.record("tr-004", "sp-1", "gpt-4o", "openai", 100, 50)
        self.tt.record("tr-004", "sp-2", "gpt-4o", "openai", 200, 100)
        self.tt.record("tr-004", "sp-3", "deepseek-chat", "deepseek", 300, 150)
        by_model = self.tt.get_usage_by_model()
        assert "gpt-4o" in by_model
        assert by_model["gpt-4o"]["total_tokens"] == 450
        assert "deepseek-chat" in by_model

    def test_cost_calculation(self):
        record = self.tt.record("tr-005", "sp-1", "gpt-4o", "openai", 1000, 500)
        # gpt-4o: $2.5/1M input, $10/1M output
        expected_input_cost = 1000 * 2.5 / 1_000_000
        expected_output_cost = 500 * 10 / 1_000_000
        assert abs(record.cost_usd - (expected_input_cost + expected_output_cost)) < 0.0001

    def test_empty_summary(self):
        summary = self.tt.get_usage_summary()
        assert summary["total_calls"] == 0
        assert summary["total_tokens"] == 0

    def test_total_records(self):
        self.tt.record("tr-006", "sp-1", "gpt-4o", "openai", 10, 10)
        assert self.tt.total_records == 1
