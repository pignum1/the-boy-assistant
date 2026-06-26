"""Interrupt Coordinator — 介入协调器
=========================================

为 PR5 介入闭环服务：

1. 前端通过 WS 发 `interrupt` 消息 → 写入 coordinator
2. M6 在每个 task level 之间 poll coordinator
3. 一旦发现 pending interrupt → M6 优雅退出（返回 status='interrupted'）
4. graph 路由到 m1_rebalance 节点，生成 delta_plan
5. 前端 HITL 确认 → 接续执行

设计：
- 内存级（dict）：当前单进程足够；多进程部署再换 Redis
- 按 session_id 隔离
- 软介入 vs 硬中断 仅在 M6 退出语义上不同：硬中断会立即停止 dispatch，
  软介入等当前 level 完成后再触发
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

logger = logging.getLogger(__name__)

InterruptMode = Literal["soft", "hard"]


@dataclass
class InterruptRequest:
    """单次介入请求"""
    session_id: str
    mode: InterruptMode
    message: str
    triggered_at: float = field(default_factory=time.monotonic)


class InterruptCoordinator:
    """单例：按 session_id 维护介入请求

    并发安全：Python 的 dict 操作在 GIL 下原子，足够。复杂场景再加锁。
    """

    def __init__(self) -> None:
        self._pending: dict[str, InterruptRequest] = {}
        self._paused: dict[str, bool] = {}  # session_id → paused flag (硬中断后置 True)

    # ── 写入 ──

    def request_interrupt(self, session_id: str, mode: InterruptMode, message: str) -> InterruptRequest:
        """记录用户介入请求。如果已有 pending 则覆盖（latest-wins）。"""
        req = InterruptRequest(session_id=session_id, mode=mode, message=message)
        self._pending[session_id] = req
        if mode == "hard":
            self._paused[session_id] = True
        logger.info(f"[interrupt] session={session_id[:8]} mode={mode} msg={message[:60]!r}")
        return req

    def resume(self, session_id: str) -> None:
        """硬中断后用户主动恢复：清 paused 标志"""
        self._paused[session_id] = False
        logger.info(f"[interrupt] resume session={session_id[:8]}")

    # ── 读取 / 消费 ──

    def has_pending(self, session_id: str) -> bool:
        return session_id in self._pending

    def is_paused(self, session_id: str) -> bool:
        return self._paused.get(session_id, False)

    def peek(self, session_id: str) -> Optional[InterruptRequest]:
        """只看，不消费"""
        return self._pending.get(session_id)

    def consume(self, session_id: str) -> Optional[InterruptRequest]:
        """取出并清空。一次性消费，避免重复触发"""
        req = self._pending.pop(session_id, None)
        if req:
            logger.info(f"[interrupt] consume session={session_id[:8]} mode={req.mode}")
        return req

    def clear(self, session_id: str) -> None:
        """清理（会话结束 / 撤回介入时调用）"""
        self._pending.pop(session_id, None)
        self._paused.pop(session_id, None)


# Module-level singleton
interrupt_coordinator = InterruptCoordinator()
