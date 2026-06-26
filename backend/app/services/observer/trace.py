"""Trace Manager：简版 OpenTelemetry Trace Span 管理

职责：
1. 创建/结束 Trace 和 Span
2. 维护 Span 层级关系（parent_span_id）
3. 查询完整调用树
4. 存储：内存 dict（MVP，后续可迁移到 DB 表）
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    """Trace Span 数据类"""
    trace_id: str
    span_id: str
    name: str
    parent_span_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attributes: dict = field(default_factory=dict)
    status: str = "active"  # active / completed / error


class TraceManager:
    """Trace 管理器"""

    def __init__(self):
        self._traces: dict[str, dict] = {}     # trace_id → {root_span_id, status, ...}
        self._spans: dict[str, TraceSpan] = {}  # span_id → TraceSpan

    def start_trace(self, task_id: str) -> str:
        """创建新的 Trace，返回 trace_id"""
        trace_id = str(uuid.uuid4())
        self._traces[trace_id] = {
            "task_id": task_id,
            "root_span_id": None,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug(f"Trace started: {trace_id} task={task_id}")
        return trace_id

    def start_span(
        self,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[dict] = None,
    ) -> str:
        """创建新的 Span，返回 span_id"""
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            name=name,
            parent_span_id=parent_span_id,
            start_time=datetime.now(timezone.utc),
            attributes=attributes or {},
        )
        self._spans[span_id] = span

        # 设置 root span
        if trace_id in self._traces and self._traces[trace_id]["root_span_id"] is None:
            self._traces[trace_id]["root_span_id"] = span_id

        logger.debug(f"Span started: {name} trace={trace_id}")
        return span_id

    def end_span(self, span_id: str, attributes: Optional[dict] = None) -> bool:
        """结束 Span"""
        span = self._spans.get(span_id)
        if not span:
            return False

        span.end_time = datetime.now(timezone.utc)
        span.status = "completed"
        if attributes:
            span.attributes.update(attributes)

        logger.debug(f"Span ended: {span.name} duration={self._span_duration_ms(span):.0f}ms")
        return True

    def end_trace(self, trace_id: str) -> bool:
        """结束 Trace"""
        if trace_id not in self._traces:
            return False

        self._traces[trace_id]["status"] = "completed"
        # 结束所有未完成的 Span
        for span in self._spans.values():
            if span.trace_id == trace_id and span.status == "active":
                span.end_time = datetime.now(timezone.utc)
                span.status = "completed"

        logger.debug(f"Trace ended: {trace_id}")
        return True

    def get_trace_tree(self, trace_id: str) -> Optional[dict]:
        """获取完整调用树"""
        if trace_id not in self._traces:
            return None

        trace_info = self._traces[trace_id]
        spans = [s for s in self._spans.values() if s.trace_id == trace_id]

        # 构建 span 树
        span_map = {s.span_id: s for s in spans}
        root_id = trace_info.get("root_span_id")

        def build_tree(span_id: str) -> dict:
            span = span_map[span_id]
            children = [
                build_tree(s.span_id)
                for s in spans
                if s.parent_span_id == span_id
            ]
            return {
                "span_id": span.span_id,
                "name": span.name,
                "status": span.status,
                "duration_ms": self._span_duration_ms(span),
                "attributes": span.attributes,
                "start_time": span.start_time.isoformat() if span.start_time else None,
                "end_time": span.end_time.isoformat() if span.end_time else None,
                **({"children": children} if children else {}),
            }

        tree = {
            "trace_id": trace_id,
            "task_id": trace_info["task_id"],
            "status": trace_info["status"],
            "total_spans": len(spans),
        }

        if root_id and root_id in span_map:
            tree["root"] = build_tree(root_id)

        return tree

    def get_trace_by_task(self, task_id: str) -> Optional[dict]:
        """通过 task_id 查找 Trace"""
        for trace_id, info in self._traces.items():
            if info["task_id"] == task_id:
                return self.get_trace_tree(trace_id)
        return None

    @staticmethod
    def _span_duration_ms(span: TraceSpan) -> float:
        if span.start_time and span.end_time:
            return (span.end_time - span.start_time).total_seconds() * 1000
        return 0.0

    @property
    def active_traces(self) -> int:
        return sum(1 for t in self._traces.values() if t["status"] == "active")

    @property
    def total_spans(self) -> int:
        return len(self._spans)
