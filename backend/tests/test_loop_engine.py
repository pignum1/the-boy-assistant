"""Loop Engine 单元测试 — 错误分类 + 恢复策略 + Harness 集成"""

import asyncio
import pytest
from app.services.loop_engine import (
    LoopEngine, LoopContext, LoopResult, ErrorCategory,
)


class TestErrorClassification:
    """错误分类测试"""

    def test_timeout_is_transient(self):
        engine = LoopEngine()
        assert engine._classify_error("Connection timeout after 30s") == ErrorCategory.TRANSIENT
        assert engine._classify_error("Request timed out") == ErrorCategory.TRANSIENT

    def test_rate_limit_is_transient(self):
        engine = LoopEngine()
        assert engine._classify_error("Rate limit exceeded: 429") == ErrorCategory.TRANSIENT
        assert engine._classify_error("HTTP 503 Service Unavailable") == ErrorCategory.TRANSIENT

    def test_validation_is_content(self):
        engine = LoopEngine()
        assert engine._classify_error("Validation failed: missing required field") == ErrorCategory.CONTENT
        assert engine._classify_error("Schema parse error: unexpected token") == ErrorCategory.CONTENT
        assert engine._classify_error("Quality score below threshold 0.5") == ErrorCategory.CONTENT

    def test_auth_is_fatal(self):
        engine = LoopEngine()
        assert engine._classify_error("Invalid API key: authentication failed") == ErrorCategory.FATAL
        assert engine._classify_error("HTTP 401 Unauthorized") == ErrorCategory.FATAL
        assert engine._classify_error("Model not found: gpt-5") == ErrorCategory.FATAL

    def test_unknown_defaults_to_content(self):
        """未识别的错误默认为 CONTENT（安全兜底：回滚+重试 优于 直接跳过）"""
        engine = LoopEngine()
        assert engine._classify_error("Some random unexpected error") == ErrorCategory.CONTENT


class TestHandleFailure:
    """handle_failure 恢复策略测试"""

    def test_transient_error_direct_retry(self):
        """瞬时错误：直接重试，不注入 feedback"""
        engine = LoopEngine(max_retries=3)
        ctx = LoopContext(task_id="t1", agent_id="a1", session_id="s1")
        result = asyncio.run(engine.handle_failure("Timeout", ctx))
        assert result.action == "retry"
        assert result.retry_count == 1
        assert result.feedback is None

    def test_content_error_retry_with_feedback(self):
        """内容错误：回滚 + 注入 feedback + 重试"""
        engine = LoopEngine(max_retries=3)
        ctx = LoopContext(task_id="t2", agent_id="a2", session_id="s2")
        result = asyncio.run(engine.handle_failure("Validation failed", ctx))
        assert result.action == "retry_with_feedback"
        assert result.feedback is not None
        assert "修正后重新输出" in result.feedback
        assert result.retry_count == 1

    def test_fatal_error_escalates_immediately(self):
        """致命错误：立即升级 HITL，不重试"""
        engine = LoopEngine(max_retries=3)
        ctx = LoopContext(task_id="t3", agent_id="a3", session_id="s3")
        result = asyncio.run(engine.handle_failure("Invalid API key", ctx))
        assert result.action == "escalate_hitl"
        assert result.hitl_data is not None
        assert result.hitl_data["type"] == "fatal_error"
        assert result.retry_count == 0  # 不重试

    def test_max_retries_exceeded_escalates(self):
        """超过最大重试次数 → 升级 HITL"""
        engine = LoopEngine(max_retries=2)
        ctx = LoopContext(task_id="t4", agent_id="a4", session_id="s4", retry_count=2)
        result = asyncio.run(engine.handle_failure("Any error", ctx))
        assert result.action == "escalate_hitl"
        assert result.hitl_data["type"] == "retry_exhausted"

    def test_retry_count_increments(self):
        """重试计数正确递增"""
        engine = LoopEngine(max_retries=3)
        ctx = LoopContext(task_id="t5", agent_id="a5", session_id="s5")
        result = asyncio.run(engine.handle_failure("Timeout", ctx))
        assert result.retry_count == 1
        result2 = asyncio.run(engine.handle_failure("Timeout",
            LoopContext(task_id="t5", agent_id="a5", session_id="s5", retry_count=1)))
        assert result2.retry_count == 2

    def test_feedback_includes_error_history(self):
        """feedback 包含错误历史（避免重复犯错）"""
        engine = LoopEngine(max_retries=3)
        ctx = LoopContext(task_id="t6", agent_id="a6", session_id="s6")
        ctx.record_error("First error: missing field", "content")
        result = asyncio.run(engine.handle_failure("Second error: bad format", ctx))
        assert "First error" in result.feedback
        assert "Second error" in result.feedback


class TestLoopContext:
    """LoopContext 数据类测试"""

    def test_can_retry(self):
        ctx = LoopContext(task_id="t1", agent_id="a1", session_id="s1", retry_count=0, max_retries=3)
        assert ctx.can_retry is True
        ctx.retry_count = 3
        assert ctx.can_retry is False

    def test_record_error(self):
        ctx = LoopContext(task_id="t1", agent_id="a1", session_id="s1")
        ctx.record_error("test error", "content")
        assert len(ctx.errors) == 1
        assert ctx.errors[0]["error"] == "test error"
        assert ctx.errors[0]["error_type"] == "content"
        assert "timestamp" in ctx.errors[0]
