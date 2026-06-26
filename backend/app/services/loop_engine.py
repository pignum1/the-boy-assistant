"""Loop Engine — Agent 执行失败时的自动错误恢复引擎

工作流程：
  1. Agent 执行失败（LLM 超时 / 验证不通过 / 格式错误）
  2. Loop Engine 检查错误类型 → 分类（瞬时/内容/致命）
  3. 瞬时错误 → 直接重试
  4. 内容错误 → 回滚 workspace 快照 + 注入 feedback + 重试
  5. 致命错误 → 升级 HITL（人工介入）
  6. 超过最大重试次数 → 升级 HITL

与 Harness 的关系：
  Harness.after_execution → 验证失败 → LoopEngine.handle_failure()
  → LoopResult → Harness 根据结果决定重试或升级
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """错误分类。"""
    TRANSIENT = "transient"  # 瞬时错误：网络超时、API 限流 → 直接重试
    CONTENT = "content"      # 内容错误：验证失败、格式错误 → 回滚 + feedback + 重试
    FATAL = "fatal"          # 致命错误：模型不可用、配置错误 → 升级 HITL


@dataclass
class LoopContext:
    """Loop Engine 执行上下文。"""
    task_id: str
    agent_id: str
    session_id: str
    retry_count: int = 0
    max_retries: int = 3
    errors: list[dict] = field(default_factory=list)  # [{error, error_type, timestamp}]

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def record_error(self, error: str, error_type: str) -> None:
        from datetime import datetime, timezone
        self.errors.append({
            "error": str(error)[:500],
            "error_type": error_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


@dataclass
class LoopResult:
    """错误恢复结果。"""
    recovered: bool
    action: str = ""                      # "retry" | "retry_with_feedback" | "escalate_hitl" | "fail"
    feedback: Optional[str] = None        # 注入给 Agent 的修正指导
    hitl_data: Optional[dict] = None      # 升级 HITL 时附带的信息
    final_error: Optional[str] = None     # 最终失败原因
    retry_count: int = 0                  # 当前重试次数


class LoopEngine:
    """错误恢复引擎。

    使用方式：
        engine = LoopEngine()
        result = await engine.handle_failure(error, ctx, workspace_manager)
        if result.action == "retry":
            # 重新执行 Agent
        elif result.action == "retry_with_feedback":
            # 回滚 + 注入 feedback + 重试
        elif result.action == "escalate_hitl":
            # 升级人工介入
    """

    DEFAULT_MAX_RETRIES = 3

    # ── 错误分类关键词 ──

    _TRANSIENT_KEYWORDS: frozenset[str] = frozenset({
        "timeout", "timed out", "rate limit", "rate_limit", "ratelimit",
        "429", "503", "502", "504",
        "connection", "connect", "network", "unreachable", "refused",
        "temporary", "retry", "try again",
    })

    _CONTENT_KEYWORDS: frozenset[str] = frozenset({
        "validation", "validate", "validator",
        "format", "schema", "parse", "parsing",
        "quality", "score", "threshold",
        "incomplete", "missing", "empty", "blank",
        "不符合", "格式错误", "验证失败", "质量不足",
        "hallucination",
    })

    _FATAL_KEYWORDS: frozenset[str] = frozenset({
        "unauthorized", "forbidden", "401", "403",
        "not found", "404",
        "model not available", "model_not_found",
        "invalid api key", "authentication",
        "quota exceeded", "billing",
        "configuration", "config error",
    })

    # ═══════════════════════════════════════════

    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES):
        self.max_retries = max_retries

    async def handle_failure(
        self,
        error: Union[str, Exception],
        ctx: LoopContext,
    ) -> LoopResult:
        """处理执行失败。检查重试次数 → 分类错误 → 执行恢复策略。

        Args:
            error: 错误信息（字符串或异常对象）
            ctx: 执行上下文（含重试计数）

        Returns:
            LoopResult 指示下一步动作
        """
        error_str = str(error)

        # 0. 检查重试次数
        if ctx.retry_count >= self.max_retries:
            ctx.record_error(error_str, "max_retries_exceeded")
            logger.warning(
                f"LoopEngine: max retries ({self.max_retries}) exceeded "
                f"for task={ctx.task_id[:8]} agent={ctx.agent_id[:8]}"
            )
            return LoopResult(
                recovered=False,
                action="escalate_hitl",
                hitl_data={
                    "type": "retry_exhausted",
                    "task_id": ctx.task_id,
                    "agent_id": ctx.agent_id,
                    "error": error_str[:200],
                    "retry_count": ctx.retry_count,
                    "error_history": ctx.errors[-3:],
                },
                final_error=f"超过最大重试次数 ({self.max_retries})：{error_str[:200]}",
                retry_count=ctx.retry_count,
            )

        # 1. 分类错误
        category = self._classify_error(error_str)
        ctx.record_error(error_str, category.value)

        logger.info(
            f"LoopEngine: error={category.value} task={ctx.task_id[:8]} "
            f"retry={ctx.retry_count}/{self.max_retries}"
        )

        # 2. 按类型处理
        if category == ErrorCategory.TRANSIENT:
            return await self._handle_transient(ctx)

        elif category == ErrorCategory.CONTENT:
            return await self._handle_content(error_str, ctx)

        else:  # FATAL
            return await self._handle_fatal(error_str, ctx)

    def _classify_error(self, error_str: str) -> ErrorCategory:
        """判断错误类型。"""
        lowered = error_str.lower()

        # 致命错误优先（一旦匹配立即返回）
        for kw in self._FATAL_KEYWORDS:
            if kw in lowered:
                return ErrorCategory.FATAL

        # 瞬时错误
        for kw in self._TRANSIENT_KEYWORDS:
            if kw in lowered:
                return ErrorCategory.TRANSIENT

        # 内容错误
        for kw in self._CONTENT_KEYWORDS:
            if kw in lowered:
                return ErrorCategory.CONTENT

        # 兜底：HTTP 5xx → 瞬时, 4xx → 致命
        if any(code in lowered for code in ["500", "502", "503", "504"]):
            return ErrorCategory.TRANSIENT
        if any(code in lowered for code in ["400", "401", "403", "404"]):
            return ErrorCategory.FATAL

        # 默认：内容错误
        return ErrorCategory.CONTENT

    async def _handle_transient(self, ctx: LoopContext) -> LoopResult:
        """瞬时错误：直接重试，不回滚不注入 feedback。"""
        ctx.retry_count += 1
        return LoopResult(
            recovered=False,
            action="retry",
            retry_count=ctx.retry_count,
        )

    async def _handle_content(self, error_str: str, ctx: LoopContext) -> LoopResult:
        """内容错误：回滚 + 注入 feedback + 重试。"""
        ctx.retry_count += 1
        feedback = self._build_feedback(error_str, ctx)
        return LoopResult(
            recovered=False,
            action="retry_with_feedback",
            feedback=feedback,
            retry_count=ctx.retry_count,
        )

    async def _handle_fatal(self, error_str: str, ctx: LoopContext) -> LoopResult:
        """致命错误：立即升级 HITL，不重试。"""
        return LoopResult(
            recovered=False,
            action="escalate_hitl",
            hitl_data={
                "type": "fatal_error",
                "task_id": ctx.task_id,
                "agent_id": ctx.agent_id,
                "error": error_str[:200],
                "suggestion": "致命错误无法自动恢复，请人工介入处理",
            },
            final_error=error_str[:200],
            retry_count=ctx.retry_count,
        )

    def _build_feedback(self, error_str: str, ctx: LoopContext) -> str:
        """构建给 Agent 的修正反馈。包含错误详情 + 历史记录（避免重复犯错）。"""
        parts = [
            f"⚠️ 上次执行出现以下问题，请修正后重新输出：",
            f"",
            f"**错误详情**：{error_str[:300]}",
            f"",
            f"**修正要求**：",
            f"1. 仔细检查输出格式是否符合要求",
            f"2. 确保内容完整、逻辑正确",
            f"3. 如果是代码，确保语法无误、可以运行",
        ]

        if ctx.errors and len(ctx.errors) > 1:
            parts.append(f"")
            parts.append(f"**历史错误**（共 {len(ctx.errors)} 次）：")
            for i, e in enumerate(ctx.errors[-3:]):
                parts.append(f"- 第 {i + 1} 次：{e['error'][:100]}")

        return "\n".join(parts)
