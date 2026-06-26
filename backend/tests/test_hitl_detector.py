"""HITL 检测器单元测试 — 四级检测 + 选项提取"""

import pytest
from app.services.collaboration.hitl_detector import (
    HitlDetector, HitlConfidence, HitlDetectionResult, detect_hitl,
)


class TestHitlDetector:
    """HITL 检测器测试"""

    def setup_method(self):
        self.detector = HitlDetector()

    # ── Level 1: 显式标记 ──

    def test_explicit_marker_triggers_high_confidence(self):
        result = self.detector.detect(
            "__HITL__ 请确认是否继续", "Agent A", 0, True, [],
        )
        assert result.triggered is True
        assert result.confidence == HitlConfidence.HIGH
        assert result.matched_by == "marker"

    # ── Level 2: 结构化选项 ──

    def test_structured_options_triggers_high_confidence(self):
        content = "需要用户确认：**方案A：Redis** — 高性能。**方案B：Memcached** — 简单。推荐方案A。"
        result = self.detector.detect(content, "Agent B", 0, True, [])
        assert result.triggered is True
        assert result.confidence == HitlConfidence.HIGH
        assert result.matched_by == "structured_options"
        assert len(result.options) == 2

    # ── Level 3: 语义特征 ──

    def test_semantic_features_triggers_medium_confidence(self):
        content = "请做出选择：\n1. 方案A — 高性能\n2. 方案B — 低成本\n推荐方案A"
        result = self.detector.detect(content, "Agent C", 0, True, [])
        assert result.triggered is True
        assert result.confidence == HitlConfidence.MEDIUM
        assert result.matched_by == "semantic"

    def test_vs_pattern_triggers(self):
        content = "建议使用 Redis vs Memcached，需要你决定"
        result = self.detector.detect(content, "Agent D", 0, True, [])
        assert result.triggered is True
        assert result.matched_by == "semantic"

    # ── 排除模式 ──

    def test_excluded_pattern_does_not_trigger(self):
        """假设性讨论不应触发 HITL（排除模式）"""
        content = "如果用户需要确认收货地址，取决于前端实现"
        result = self.detector.detect(content, "Agent E", 0, True, [])
        assert result.triggered is False

    def test_empty_content_does_not_trigger(self):
        result = self.detector.detect("", "Agent F", 0, True, [])
        assert result.triggered is False

    # ── 选项提取 ──

    def test_extract_options_from_marker(self):
        """**方案X** 格式提取"""
        content = "**方案A：Redis** — 高性能缓存。**方案B：Memcached** — 简单易用。"
        options = self.detector._extract_options(content)
        assert len(options) == 2

    def test_extract_options_from_numbered_list(self):
        """数字列表格式提取"""
        content = "有以下选项：\n1. 使用 PostgreSQL\n2. 使用 MySQL\n3. 使用 MongoDB\n请选择。"
        options = self.detector._extract_options(content)
        assert len(options) == 3

    def test_extract_options_from_guide_words(self):
        """'两种方案' 引导词提取"""
        content = "列出三种选项：PostgreSQL, MySQL, MongoDB 供参考"
        options = self.detector._extract_options(content)
        assert len(options) == 3

    def test_extract_options_from_vs(self):
        """vs 对比提取"""
        content = "可以在 React vs Vue 之间选择"
        options = self.detector._extract_options(content)
        assert len(options) == 2


class TestHitlConfidenceLevels:
    """置信度层级测试"""

    def test_high_trumps_medium(self):
        """显式标记 > 语义特征"""
        detector = HitlDetector()
        content = "__HITL__ 请选择 1. 方案A 2. 方案B"
        result = detector.detect(content, "Agent", 0, True, [])
        assert result.triggered is True
        assert result.confidence == HitlConfidence.HIGH  # marker wins
        assert result.matched_by == "marker"

    def test_structured_trumps_semantic(self):
        """结构化选项 > 语义特征"""
        detector = HitlDetector()
        content = "推荐**方案A：Redis** — 高性能。请确认。"
        result = detector.detect(content, "Agent", 0, True, [])
        assert result.triggered is True
        assert result.confidence == HitlConfidence.HIGH
        assert result.matched_by == "structured_options"
