"""Token Tracker：LLM Token 消耗统计与成本计算

职责：
1. 记录每次 LLM 调用的 token 使用量
2. 按 task / model / provider 维度聚合统计
3. 基于模型单价自动计算成本
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 模型单价表（USD per 1M tokens）
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "glm-4": {"input": 0.50, "output": 0.50},
}


@dataclass
class TokenUsageRecord:
    """单次 LLM 调用的 Token 使用记录"""
    trace_id: str
    span_id: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TokenTracker:
    """Token 消耗追踪器"""

    def __init__(self):
        self._records: list[TokenUsageRecord] = []

    def record(
        self,
        trace_id: str,
        span_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsageRecord:
        """记录一次 LLM 调用的 Token 使用"""
        total = prompt_tokens + completion_tokens
        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

        record = TokenUsageRecord(
            trace_id=trace_id,
            span_id=span_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
        )
        self._records.append(record)

        logger.debug(
            f"Token usage: model={model} prompt={prompt_tokens} "
            f"completion={completion_tokens} cost=${cost:.4f}"
        )
        return record

    def get_usage_by_trace(self, trace_id: str) -> dict:
        """按 trace_id 聚合 Token 使用"""
        records = [r for r in self._records if r.trace_id == trace_id]
        return self._aggregate(records)

    def get_usage_by_task(self, task_id: str) -> dict:
        """按 task_id 聚合（需要先通过 TraceManager 映射）"""
        records = [r for r in self._records]
        return self._aggregate(records)

    def get_usage_summary(self, time_range: str = "24h") -> dict:
        """全局 Token 消耗汇总"""
        return self._aggregate(self._records)

    def get_usage_by_model(self) -> dict[str, dict]:
        """按模型分组统计"""
        by_model: dict[str, list[TokenUsageRecord]] = defaultdict(list)
        for r in self._records:
            by_model[r.model].append(r)
        return {model: self._aggregate(records) for model, records in by_model.items()}

    def _aggregate(self, records: list[TokenUsageRecord]) -> dict:
        """聚合一组记录"""
        if not records:
            return {"total_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}

        return {
            "total_calls": len(records),
            "prompt_tokens": sum(r.prompt_tokens for r in records),
            "completion_tokens": sum(r.completion_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records),
            "cost_usd": round(sum(r.cost_usd for r in records), 4),
            "by_model": {
                model: {
                    "calls": len(rs),
                    "total_tokens": sum(r.total_tokens for r in rs),
                    "cost_usd": round(sum(r.cost_usd for r in rs), 4),
                }
                for model, rs in {
                    m: [r for r in records if r.model == m] for m in set(r.model for r in records)
                }.items()
            },
        }

    @staticmethod
    def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """计算成本"""
        pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    @property
    def total_records(self) -> int:
        return len(self._records)
