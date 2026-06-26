"""Blackboard：基于 Redis Pub/Sub 的团队间通信

职责：
1. 团队内部事件广播（task_update / agent_status / hitl_notification）
2. 跨团队请求-响应（cross_team_request）
3. 全局事件通道（rate_limit_warning 等）
4. 回调注册机制

消息格式：
{
    "type": "task_update" | "agent_status" | ...,
    "source": "team_id" | "agent_id",
    "timestamp": "ISO8601",
    "payload": {...}
}
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    TASK_UPDATE = "task_update"
    NODE_UPDATE = "node_update"  # 节点状态更新事件
    AGENT_STATUS = "agent_status"
    HITL_NOTIFICATION = "hitl_notification"
    CROSS_TEAM_REQUEST = "cross_team_request"
    CROSS_TEAM_RESPONSE = "cross_team_response"
    RATE_LIMIT_WARNING = "rate_limit_warning"


@dataclass
class Event:
    """Blackboard 事件"""
    type: EventType
    source: str
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class Blackboard:
    """Redis Pub/Sub 团队通信"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._callbacks: dict[str, list[Callable[[Event], Coroutine]]] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._pending_requests: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """建立 Redis 连接"""
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url)
            self._pubsub = self._redis.pubsub()
            await self._redis.ping()
            logger.info("Blackboard: Redis connected")
        except ImportError:
            logger.warning("Blackboard: redis[hiredis] not installed, using in-memory fallback")
            self._redis = None
        except Exception as e:
            logger.warning(f"Blackboard: Redis connection failed ({e}), using in-memory fallback")
            self._redis = None

    async def disconnect(self) -> None:
        """断开 Redis 连接"""
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub:
            await self._pubsub.unsubscribe()
        if self._redis:
            await self._redis.close()
        logger.info("Blackboard: disconnected")

    def _channel(self, team_id: Optional[str] = None) -> str:
        """生成频道名"""
        if team_id:
            return f"team:{team_id}:events"
        return "global:events"

    async def pub(
        self,
        event_type: EventType,
        payload: dict,
        team_id: Optional[str] = None,
        source: str = "",
    ) -> str:
        """发布事件"""
        event = Event(
            type=event_type,
            source=source or team_id or "system",
            payload=payload,
        )
        channel = self._channel(team_id)
        message = json.dumps({
            "event_id": event.event_id,
            "type": event.type.value,
            "source": event.source,
            "timestamp": event.timestamp,
            "payload": event.payload,
        })

        if self._redis:
            await self._redis.publish(channel, message)
        else:
            # 内存模式：直接调用回调
            await self._dispatch_callbacks(channel, event)

        logger.debug(f"Blackboard pub: {event.type.value} on {channel}")
        return event.event_id

    async def sub(
        self,
        team_id: Optional[str] = None,
        callback: Optional[Callable[[Event], Coroutine]] = None,
    ) -> None:
        """订阅频道并注册回调"""
        channel = self._channel(team_id)

        if callback:
            if channel not in self._callbacks:
                self._callbacks[channel] = []
            self._callbacks[channel].append(callback)

        if self._redis and self._pubsub:
            await self._pubsub.subscribe(channel)
            if not self._listener_task:
                self._listener_task = asyncio.create_task(self._listen_loop())

        logger.info(f"Blackboard sub: {channel}")

    async def request_cross_team(
        self,
        source_team: str,
        target_team: str,
        request_type: str,
        data: dict,
        timeout: float = 30.0,
    ) -> Optional[dict]:
        """跨团队请求-响应"""
        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        payload = {
            "request_id": request_id,
            "source_team": source_team,
            "target_team": target_team,
            "request_type": request_type,
            "data": data,
        }

        await self.pub(
            event_type=EventType.CROSS_TEAM_REQUEST,
            payload=payload,
            team_id=target_team,
            source=source_team,
        )

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Cross-team request {request_id} timed out")
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def respond_cross_team(
        self,
        request_id: str,
        target_team: str,
        data: dict,
    ) -> None:
        """跨团队响应"""
        await self.pub(
            event_type=EventType.CROSS_TEAM_RESPONSE,
            payload={"request_id": request_id, "data": data},
            team_id=target_team,
        )

    async def _listen_loop(self) -> None:
        """Redis Pub/Sub 监听循环"""
        if not self._pubsub:
            return

        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                try:
                    data = json.loads(message["data"])
                    event = Event(
                        type=EventType(data["type"]),
                        source=data.get("source", ""),
                        payload=data.get("payload", {}),
                        timestamp=data.get("timestamp", ""),
                        event_id=data.get("event_id", ""),
                    )
                    await self._dispatch_callbacks(channel, event)
                except Exception as e:
                    logger.error(f"Blackboard message parse error: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Blackboard listen error: {e}")

    async def _dispatch_callbacks(self, channel: str, event: Event) -> None:
        """分发事件到注册的回调"""
        # 处理跨团队响应
        if event.type == EventType.CROSS_TEAM_RESPONSE:
            request_id = event.payload.get("request_id", "")
            future = self._pending_requests.get(request_id)
            if future and not future.done():
                future.set_result(event.payload.get("data"))
                return

        # 通知频道回调
        callbacks = self._callbacks.get(channel, [])
        for cb in callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"Blackboard callback error: {e}")

        # 全局回调
        global_callbacks = self._callbacks.get("global:events", [])
        for cb in global_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"Blackboard global callback error: {e}")

    def get_status(self) -> dict:
        """获取 Blackboard 状态"""
        return {
            "connected": self._redis is not None,
            "channels": list(self._callbacks.keys()),
            "pending_requests": len(self._pending_requests),
            "total_callbacks": sum(len(cbs) for cbs in self._callbacks.values()),
        }


# Global blackboard
blackboard = Blackboard()
