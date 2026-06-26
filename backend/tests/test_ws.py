"""WebSocket Broadcaster 单元测试：ConnectionManager"""

import pytest

from app.services.ws_broadcaster import ConnectionManager


# ── Mock WebSocket ──────────────────────────────────────────

class MockWebSocket:
    """模拟 WebSocket 连接"""

    def __init__(self, raise_on_send: bool = False):
        self.sent_messages: list[dict] = []
        self.raise_on_send = raise_on_send

    async def send_json(self, message: dict):
        if self.raise_on_send:
            raise RuntimeError("Connection closed")
        self.sent_messages.append(message)

    async def close(self):
        pass


# ── ConnectionManager 测试 ─────────────────────────────────

class TestConnectionManager:
    def setup_method(self):
        self.cm = ConnectionManager()

    @pytest.mark.asyncio
    async def test_connect(self):
        ws = MockWebSocket()
        await self.cm.connect("task-001", "team-a", ws)
        assert self.cm.active_connections == 1

    @pytest.mark.asyncio
    async def test_disconnect(self):
        ws = MockWebSocket()
        await self.cm.connect("task-001", "team-a", ws)
        await self.cm.disconnect("task-001", ws)
        assert self.cm.active_connections == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_task(self):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        ws3 = MockWebSocket()

        await self.cm.connect("task-001", "team-a", ws1)
        await self.cm.connect("task-001", "team-a", ws2)
        await self.cm.connect("task-002", "team-b", ws3)

        await self.cm.broadcast_to_task("task-001", {"type": "test", "payload": {}})

        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 1
        assert len(ws3.sent_messages) == 0  # different task

    @pytest.mark.asyncio
    async def test_broadcast_to_team(self):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()

        await self.cm.connect("task-001", "team-a", ws1)
        await self.cm.connect("task-002", "team-b", ws2)

        await self.cm.broadcast_to_team("team-a", {"type": "test", "payload": {}})

        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 0  # different team

    @pytest.mark.asyncio
    async def test_broadcast_empty(self):
        # No connections, should not raise
        count = await self.cm.broadcast_to_task("task-000", {"type": "test"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_broadcast_handles_error(self):
        ws_bad = MockWebSocket(raise_on_send=True)
        await self.cm.connect("task-001", "team-a", ws_bad)

        # Should not raise, just skip the bad connection
        count = await self.cm.broadcast_to_task("task-001", {"type": "test"})
        # Bad connection gets cleaned up
        assert self.cm.active_connections == 0

    @pytest.mark.asyncio
    async def test_multiple_connections_same_task(self):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await self.cm.connect("task-001", "team-a", ws1)
        await self.cm.connect("task-001", "team-a", ws2)
        assert self.cm.active_connections == 2

    def test_get_task_team(self):
        # Not connected yet
        assert self.cm.get_task_team("task-001") is None

    @pytest.mark.asyncio
    async def test_active_tasks(self):
        await self.cm.connect("task-001", "team-a", MockWebSocket())
        await self.cm.connect("task-002", "team-b", MockWebSocket())
        assert self.cm.active_tasks == 2

    @pytest.mark.asyncio
    async def test_disconnect_cleans_empty_task(self):
        ws = MockWebSocket()
        await self.cm.connect("task-001", "team-a", ws)
        await self.cm.disconnect("task-001", ws)
        assert self.cm.active_tasks == 0
