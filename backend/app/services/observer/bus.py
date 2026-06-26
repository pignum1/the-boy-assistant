"""观察者事件总线 — 异步发布/订阅

不依赖第三方消息队列，用 Python asyncio 原生实现。
支持同步和异步 handler，emit 非阻塞。
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable

from app.services.observer.events import Event, EventType

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """轻量级异步事件总线。

    使用方式：
        bus = EventBus()
        bus.subscribe(EventType.TASK_CREATED, my_handler)
        await bus.emit(event)
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._global_handlers: list[Handler] = []

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """订阅特定事件类型。"""
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """订阅所有事件（全局监听）。"""
        self._global_handlers.append(handler)

    async def emit(self, event: Event) -> None:
        """发布事件。所有 handler 异步执行，不阻塞调用方。

        创建后台 task 执行 handler，异常不会传播到调用方。
        """
        handlers = (
            self._handlers.get(event.type, []) +
            self._global_handlers
        )
        if not handlers:
            return

        async def _run_all() -> None:
            results = await asyncio.gather(
                *[h(event) for h in handlers],
                return_exceptions=True,
            )
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    type_name = event.type.value if hasattr(event.type, 'value') else str(event.type)
                    logger.warning(
                        "EventBus handler[%d] failed for %s: %s",
                        i, type_name, r,
                    )

        asyncio.create_task(_run_all())


# 全局单例
bus = EventBus()
