"""观察者事件模型 — 轻量级事件定义

所有系统事件通过此模块定义，统一类型和元数据结构。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class EventType(str, Enum):
    # 任务生命周期
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_HITL_PAUSED = "task_hitl_paused"
    TASK_HITL_RESUMED = "task_hitl_resumed"

    # Agent 执行
    AGENT_EXECUTION_STARTED = "agent_execution_started"
    AGENT_EXECUTION_COMPLETED = "agent_execution_completed"
    AGENT_EXECUTION_FAILED = "agent_execution_failed"

    # LLM 调用
    LLM_CALL_STARTED = "llm_call_started"
    LLM_CALL_COMPLETED = "llm_call_completed"
    LLM_CALL_FAILED = "llm_call_failed"

    # HITL 交互
    HITL_DETECTED = "hitl_detected"
    HITL_RESOLVED = "hitl_resolved"

    # 安全
    SECURITY_BLOCKED = "security_blocked"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"

    # 系统
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


@dataclass
class Event:
    """系统事件。"""
    type: EventType
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    session_id: Optional[str] = None
    team_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    task_id: Optional[str] = None
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def make_event(
    event_type: EventType,
    *,
    source: str = "",
    session_id: Optional[str] = None,
    team_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    task_id: Optional[str] = None,
    **payload,
) -> Event:
    """便捷工厂函数。"""
    return Event(
        type=event_type,
        source=source,
        session_id=session_id,
        team_id=team_id,
        agent_id=agent_id,
        agent_name=agent_name,
        task_id=task_id,
        payload=payload,
    )
