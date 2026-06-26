"""WS Broadcaster：Blackboard 事件 → WebSocket 客户端广播桥接

职责：
1. 订阅 Blackboard 事件（内存模式）
2. 将事件转发给 ConnectionManager 中的 WebSocket 客户端
3. 维护 task_id → team_id 的映射（用于路由事件）
"""

import asyncio
import json
import logging
from typing import Optional

from app.services.blackboard import Blackboard, Event, EventType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器（任务 + 会话）"""

    def __init__(self):
        self._connections: dict[str, set] = {}        # task_id → set of WebSocket
        self._task_teams: dict[str, str] = {}         # task_id → team_id
        self._session_connections: dict[str, set] = {} # session_id → set of WebSocket
        self._lock = asyncio.Lock()

    # ── Task 连接 ──

    async def connect(self, task_id: str, team_id: str, websocket) -> None:
        """注册 Task WebSocket 连接"""
        async with self._lock:
            if task_id not in self._connections:
                self._connections[task_id] = set()
            self._connections[task_id].add(websocket)
            self._task_teams[task_id] = team_id
        logger.info(f"WS connected: task={task_id}")

    async def disconnect(self, task_id: str, websocket) -> None:
        """移除 Task WebSocket 连接"""
        async with self._lock:
            if task_id in self._connections:
                self._connections[task_id].discard(websocket)
                if not self._connections[task_id]:
                    del self._connections[task_id]
                    self._task_teams.pop(task_id, None)
        logger.info(f"WS disconnected: task={task_id}")

    async def broadcast_to_task(self, task_id: str, message: dict) -> int:
        """向订阅某任务的所有客户端广播消息"""
        connections = self._connections.get(task_id, set())
        disconnected = []

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(task_id, ws)

        return len(connections) - len(disconnected)

    # ── Session 连接 ──

    async def connect_session(self, session_id: str, websocket) -> None:
        """注册 Session WebSocket 连接"""
        async with self._lock:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(websocket)
        logger.info(f"WS session connected: session={session_id}")

    async def disconnect_session(self, session_id: str, websocket) -> None:
        """移除 Session WebSocket 连接"""
        async with self._lock:
            if session_id in self._session_connections:
                self._session_connections[session_id].discard(websocket)
                if not self._session_connections[session_id]:
                    del self._session_connections[session_id]
        logger.info(f"WS session disconnected: session={session_id}")

    async def broadcast_to_session(self, session_id: str, message: dict) -> int:
        """向订阅某会话的所有客户端广播消息"""
        connections = self._session_connections.get(session_id, set())
        disconnected = []

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect_session(session_id, ws)

        return len(connections) - len(disconnected)

    # ── 通用 ──

    async def broadcast_to_team(self, team_id: str, message: dict) -> int:
        """向某团队的所有任务客户端广播"""
        sent = 0
        for task_id, tid in self._task_teams.items():
            if tid == team_id:
                sent += await self.broadcast_to_task(task_id, message)
        return sent

    def get_task_team(self, task_id: str) -> Optional[str]:
        return self._task_teams.get(task_id)

    @property
    def active_connections(self) -> int:
        task_conns = sum(len(conns) for conns in self._connections.values())
        session_conns = sum(len(conns) for conns in self._session_connections.values())
        return task_conns + session_conns

    @property
    def active_tasks(self) -> int:
        return len(self._connections)


# Global connection manager
manager = ConnectionManager()


class WSBroadcaster:
    """Blackboard → WebSocket 事件桥接"""

    def __init__(self, blackboard: Blackboard, conn_manager: ConnectionManager):
        self._blackboard = blackboard
        self._manager = conn_manager

    async def start(self) -> None:
        """订阅 Blackboard 事件并注册回调"""
        # 订阅全局事件
        await self._blackboard.sub(callback=self._on_event)

        # 订阅所有团队频道（动态添加的团队需要重新订阅）
        await self._blackboard.sub(team_id="__global__", callback=self._on_event)

        logger.info("WSBroadcaster started")

    async def _on_event(self, event: Event) -> None:
        """处理 Blackboard 事件并转发"""
        message = {
            "type": event.type.value,
            "source": event.source,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }

        # 根据事件类型路由
        task_id = event.payload.get("task_id")

        if task_id:
            await self._manager.broadcast_to_task(task_id, message)
        elif event.source:
            # 按 team 广播
            await self._manager.broadcast_to_team(event.source, message)

    async def stop(self) -> None:
        logger.info("WSBroadcaster stopped")


def create_broadcaster() -> WSBroadcaster:
    """延迟创建 Broadcaster（避免循环导入）"""
    from app.services.blackboard import blackboard
    return WSBroadcaster(blackboard=blackboard, conn_manager=manager)


broadcaster: Optional[WSBroadcaster] = None
