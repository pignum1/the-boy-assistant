"""Locust 性能测试脚本"""
from locust import HttpUser, task, between, events
import json

class APIUser(HttpUser):
    """模拟 API 用户行为"""
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        """登录获取 Token"""
        resp = self.client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "test123"
        })
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
        else:
            self.token = ""

    @task(3)
    def list_items(self):
        """列表查询（高频）"""
        self.client.get("/api/v1/items", headers=self._headers())

    @task(1)
    def create_item(self):
        """创建（低频）"""
        self.client.post("/api/v1/items", json={
            "name": f"perf-test-{self._random_id()}",
            "status": "active"
        }, headers=self._headers())

    @task(2)
    def get_item(self):
        """详情查询"""
        self.client.get("/api/v1/items/test-id", headers=self._headers())

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _random_id(self):
        import uuid
        return str(uuid.uuid4())[:8]
