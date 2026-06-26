"""Tasks API 测试：SOP 任务相关的 HTTP 端点

使用 api_client fixture，自动注入 NullPool 数据库连接。
"""

import pytest
import uuid


@pytest.mark.asyncio
class TestTasksAPI:
    async def test_health_check(self, api_client):
        r = await api_client.get("/health")
        assert r.status_code == 200

    async def test_list_tasks(self, api_client):
        r = await api_client.get("/api/v1/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_pending_hitl_endpoint(self, api_client):
        r = await api_client.get("/api/v1/tasks/pending-hitl")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_get_task_not_found(self, api_client):
        r = await api_client.get(f"/api/v1/tasks/{uuid.uuid4()}")
        assert r.status_code == 404

    async def test_start_task_invalid_sop(self, api_client):
        r = await api_client.post("/api/v1/tasks", json={
            "sop_id": str(uuid.uuid4()),
            "team_id": str(uuid.uuid4()),
            "input": {"requirements": "test"},
        })
        assert r.status_code == 400
