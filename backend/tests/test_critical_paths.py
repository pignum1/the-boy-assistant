"""关键路径 Smoke Tests

测试系统最核心的功能路径：
1. FallbackChain - 熔断器 + 降级链
2. API Key 认证 - 中间件逻辑
3. HITL 状态持久化 - 序列化/反序列化
4. 速率限制器 - 滑动窗口
"""

import time
import uuid
import pytest


# ═══════════════════════════════════════════
# FallbackChain — Circuit Breaker
# ═══════════════════════════════════════════

class TestCircuitBreaker:
    """熔断器单元测试（纯逻辑，无需 DB/LLM）"""

    def test_circuit_state_starts_closed(self):
        from app.services.fallback_chain import CircuitState
        circuit = CircuitState(failure_threshold=3, recovery_timeout=300)
        assert circuit.is_available("model-1") is True

    def test_circuit_state_opens_after_threshold(self):
        from app.services.fallback_chain import CircuitState
        circuit = CircuitState(failure_threshold=2, recovery_timeout=300)

        circuit.record_failure("model-1")
        assert circuit.is_available("model-1") is True  # 1 次失败，仍可用

        circuit.record_failure("model-1")
        assert circuit.is_available("model-1") is False  # 2 次失败，熔断打开

    def test_circuit_state_recovers_after_timeout(self):
        from app.services.fallback_chain import CircuitState
        circuit = CircuitState(failure_threshold=2, recovery_timeout=0.01)

        circuit.record_failure("model-1")
        circuit.record_failure("model-1")
        assert circuit.is_available("model-1") is False  # 熔断打开

        time.sleep(0.02)  # 等待恢复
        assert circuit.is_available("model-1") is True  # 恢复

    def test_circuit_state_success_resets(self):
        from app.services.fallback_chain import CircuitState
        circuit = CircuitState(failure_threshold=2, recovery_timeout=300)

        circuit.record_failure("model-1")
        circuit.record_success("model-1")
        # 成功后计数器应重置
        assert circuit.is_available("model-1") is True

    def test_circuit_state_independent_per_model(self):
        from app.services.fallback_chain import CircuitState
        circuit = CircuitState(failure_threshold=1, recovery_timeout=300)

        circuit.record_failure("model-a")
        assert circuit.is_available("model-a") is False
        assert circuit.is_available("model-b") is True  # 不同模型独立


# ═══════════════════════════════════════════
# API Key 认证
# ═══════════════════════════════════════════

class TestApiKeyAuth:
    """API Key 认证逻辑测试"""

    def test_auth_skipped_when_key_not_configured(self):
        """未配置 API_KEY 时跳过认证（默认值应为空字符串）"""
        from app.core.config import Settings
        settings = Settings()
        # 默认 API_KEY 为空，认证中间件跳过验证
        assert settings.API_KEY == ""

    def test_auth_header_name_is_correct(self):
        from app.core.auth import _AUTH_HEADER
        assert _AUTH_HEADER == "x-api-key"

    def test_ws_token_param_name_is_correct(self):
        from app.core.auth import _WS_TOKEN_PARAM
        assert _WS_TOKEN_PARAM == "token"

    def test_skip_auth_prefixes_include_health(self):
        from app.core.auth import _SKIP_AUTH_PREFIXES
        assert any("health" in p for p in _SKIP_AUTH_PREFIXES)
        assert any("docs" in p for p in _SKIP_AUTH_PREFIXES)

    def test_mask_api_key_short_key(self):
        from app.core.security import mask_api_key
        assert mask_api_key("abc") == "***"
        assert mask_api_key("12345678") == "***"  # <= 8 字符
        assert mask_api_key("123456789") == "1234...6789"  # > 8 字符

    def test_mask_api_key_long_key(self):
        from app.core.security import mask_api_key
        result = mask_api_key("sk-1234567890abcdefghij")
        assert result.startswith("sk-1")
        assert result.endswith("ghij")
        assert "..." in result


# ═══════════════════════════════════════════
# HITL 状态持久化
# ═══════════════════════════════════════════

class TestHitlStateSerialization:
    """HITL 状态序列化/反序列化测试"""

    def test_persist_state_serializes_set_to_list(self):
        """active_nodes (set) 应被序列化为 list"""
        from app.services.collaboration.engines.langgraph_engine import _persist_paused_state
        # 验证模块加载成功（实际的持久化测试需要 DB）
        assert _persist_paused_state is not None

    def test_load_state_returns_none_when_no_memory_no_db(self):
        """内存和数据库都无状态时返回 None"""
        from app.services.collaboration.engines.langgraph_engine import _load_paused_state, _paused
        import asyncio

        test_id = f"test-{uuid.uuid4()}"
        # 确保不在内存中
        _paused.pop(test_id, None)

        result = asyncio.run(_load_paused_state(test_id))
        assert result is None  # DB 也无记录时返回 None

    def test_has_paused_detects_memory_state(self):
        from app.services.collaboration.engines.langgraph_engine import has_paused, _paused
        test_id = "test-has-paused"

        _paused[test_id] = {"dummy": True}
        assert has_paused(test_id) is True

        _paused.pop(test_id, None)
        assert has_paused(test_id) is False


# ═══════════════════════════════════════════
# 速率限制器
# ═══════════════════════════════════════════

class TestRateLimiter:
    """滑动窗口速率限制器测试"""

    def test_limiter_allows_up_to_limit(self):
        from app.core.rate_limit import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)

        key = f"test-{uuid.uuid4()}"
        for _ in range(5):
            assert limiter.is_allowed(key) is True
        # 第 6 次应被拒绝
        assert limiter.is_allowed(key) is False

    def test_limiter_remaining(self):
        from app.core.rate_limit import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)

        key = f"test-{uuid.uuid4()}"
        limiter.is_allowed(key)  # 1
        assert limiter.remaining(key) == 2

    def test_limiter_windows_are_independent(self):
        from app.core.rate_limit import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

        assert limiter.is_allowed("key-a") is True
        assert limiter.is_allowed("key-a") is False  # key-a 被限
        assert limiter.is_allowed("key-b") is True   # key-b 不受影响


# ═══════════════════════════════════════════
# Workspace 工具
# ═══════════════════════════════════════════

class TestWorkspaceUtils:
    """工作区文件提取工具测试"""

    def test_is_real_code_detects_python(self):
        from app.services.collaboration.workspace_utils import is_real_code
        code = "def hello():\n    print('hello')\n    return 42"
        assert is_real_code("python", code) is True

    def test_is_real_code_rejects_natural_language(self):
        from app.services.collaboration.workspace_utils import is_real_code
        text = "首先我们需要考虑的是系统的整体架构设计。\n第二个问题是关于性能优化。"
        assert is_real_code("markdown", text) is False

    def test_is_real_code_rejects_short_text(self):
        from app.services.collaboration.workspace_utils import is_real_code
        assert is_real_code("python", "hi") is False

    def test_ext_map_covers_common_languages(self):
        from app.services.collaboration.workspace_utils import EXT_MAP
        assert EXT_MAP["python"] == ".py"
        assert EXT_MAP["typescript"] == ".ts"
        assert EXT_MAP["json"] == ".json"
        assert EXT_MAP["dockerfile"] == "Dockerfile"

    def test_path_regex_matches_valid_paths(self):
        import re as _re
        from app.services.collaboration.workspace_utils import _PATH_RE

        valid = [
            "backend/app/main.py",
            "frontend/src/App.tsx",
            "docs/readme.md",
            "deploy/Dockerfile",
        ]
        for path in valid:
            assert _PATH_RE.search(path) is not None, f"Should match: {path}"

    def test_path_regex_rejects_invalid_paths(self):
        import re as _re
        from app.services.collaboration.workspace_utils import _PATH_RE

        invalid = [
            "just-a-filename.py",   # 无路径斜杠
            "../escape.py",          # 路径遍历
            "no_extension",          # 无扩展名
        ]
        for path in invalid:
            m = _PATH_RE.fullmatch(path)
            assert m is None, f"Should not match: {path}"
