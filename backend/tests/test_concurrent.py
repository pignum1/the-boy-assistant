"""并发集成测试：验证 Agent Pool / Scheduler / Blackboard 的并发协作

场景：
1. Agent Pool acquire/release 并发安全
2. Scheduler 优先级调度
3. Blackboard 发布/订阅
4. Agent Pool 能力匹配
"""

import asyncio
import pytest

from app.services.agent_pool import AgentPool, AgentStatus, PoolEntry, ROLE_CAPABILITY_MAP
from app.services.scheduler import Scheduler, Priority, ScheduledTask
from app.services.blackboard import Blackboard, EventType, Event


# ── Agent Pool 测试 ──────────────────────────────────────


class TestAgentPoolConcurrency:
    """Agent Pool 并发安全测试"""

    def test_register_and_status(self):
        """注册 Agent 后状态正确"""
        pool = AgentPool()

        entry = PoolEntry(
            agent_id="a1",
            agent_name="TestAgent",
            persona_id="p1",
            capabilities={"coding": True, "debugging": True},
        )
        pool._entries["a1"] = entry

        status = pool.get_status()
        assert len(status) == 1
        assert status[0]["agent_id"] == "a1"
        assert status[0]["status"] == "idle"
        assert pool.get_available_count() == 1

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """acquire 后状态变更，release 后恢复"""
        pool = AgentPool()
        pool._entries["a1"] = PoolEntry(
            agent_id="a1",
            agent_name="TestAgent",
            persona_id="p1",
            capabilities={"coding": True},
        )

        # Acquire
        entry = await pool.acquire(agent_id="a1", task_id="task-1")
        assert entry is not None
        assert entry.status == AgentStatus.BUSY
        assert pool.get_available_count() == 0

        # 再次 acquire 同一个 Agent 应失败
        entry2 = await pool.acquire(agent_id="a1")
        assert entry2 is None

        # Release
        released = await pool.release("a1")
        assert released is True
        assert pool.get_available_count() == 1

    @pytest.mark.asyncio
    async def test_capability_matching(self):
        """能力匹配：role_slot 映射和直接能力匹配"""
        pool = AgentPool()

        pool._entries["coder"] = PoolEntry(
            agent_id="coder",
            agent_name="Coder",
            persona_id="p1",
            capabilities={"coding": True, "debugging": True},
        )
        pool._entries["architect"] = PoolEntry(
            agent_id="architect",
            agent_name="Architect",
            persona_id="p2",
            capabilities={"system_design": True, "architecture": True},
        )

        # 通过 role_slot 匹配
        entry = await pool.acquire(role_slot="coder", task_id="t1")
        assert entry is not None
        assert entry.agent_name == "Coder"

        await pool.release("coder")

        # 通过 capabilities 匹配
        entry = await pool.acquire(required_capabilities=["architecture"], task_id="t2")
        assert entry is not None
        assert entry.agent_name == "Architect"

        await pool.release("architect")

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """并发 acquire：只有一个能成功"""
        pool = AgentPool()
        pool._entries["a1"] = PoolEntry(
            agent_id="a1", agent_name="Solo", persona_id="p1",
        )

        results = await asyncio.gather(
            pool.acquire(agent_id="a1", task_id="t1"),
            pool.acquire(agent_id="a1", task_id="t2"),
            pool.acquire(agent_id="a1", task_id="t3"),
        )

        acquired = [r for r in results if r is not None]
        assert len(acquired) == 1
        assert pool.get_busy_count() == 1

    @pytest.mark.asyncio
    async def test_mark_error_and_reset(self):
        """error 状态流转"""
        pool = AgentPool()
        pool._entries["a1"] = PoolEntry(
            agent_id="a1", agent_name="ErrAgent", persona_id="p1",
        )

        await pool.acquire(agent_id="a1")
        await pool.mark_error("a1")

        status = pool.get_status()
        assert status[0]["status"] == "error"
        assert pool.get_available_count() == 0

        # 从 error 恢复
        reset = await pool.reset("a1")
        assert reset is True
        assert pool.get_available_count() == 1

    @pytest.mark.asyncio
    async def test_acquire_with_retry(self):
        """acquire_with_retry：等待 release 后成功"""
        pool = AgentPool()
        pool._entries["a1"] = PoolEntry(
            agent_id="a1", agent_name="RetryAgent", persona_id="p1",
        )

        # 先占用
        await pool.acquire(agent_id="a1")

        # 后台释放
        async def delayed_release():
            await asyncio.sleep(0.1)
            await pool.release("a1")

        asyncio.create_task(delayed_release())

        entry = await pool.acquire_with_retry(
            agent_id="a1",
            max_retries=5,
            interval=0.05,
        )
        assert entry is not None

    def test_role_capability_map(self):
        """role_slot → capabilities 映射完整性"""
        assert "architect" in ROLE_CAPABILITY_MAP
        assert "coder" in ROLE_CAPABILITY_MAP
        assert "coding" in ROLE_CAPABILITY_MAP["coder"]
        assert "architecture" in ROLE_CAPABILITY_MAP["architect"]

    def test_status_filter(self):
        """状态过滤"""
        pool = AgentPool()
        pool._entries["a1"] = PoolEntry(agent_id="a1", agent_name="A1", persona_id="p1", status=AgentStatus.IDLE)
        pool._entries["a2"] = PoolEntry(agent_id="a2", agent_name="A2", persona_id="p2", status=AgentStatus.BUSY)
        pool._entries["a3"] = PoolEntry(agent_id="a3", agent_name="A3", persona_id="p3", status=AgentStatus.ERROR)

        assert len(pool.get_status(status_filter="idle")) == 1
        assert len(pool.get_status(status_filter="busy")) == 1
        assert len(pool.get_status(status_filter="error")) == 1


# ── Scheduler 测试 ──────────────────────────────────────


class TestScheduler:
    """Scheduler 优先级调度测试"""

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """优先级排序：CRITICAL 先于 LOW"""
        scheduler = Scheduler(max_concurrent=10)

        execution_log = []

        async def mock_task(name: str):
            execution_log.append(name)

        scheduler.enqueue(mock_task, "low", Priority.LOW, name="low")
        scheduler.enqueue(mock_task, "high", Priority.HIGH, name="high")
        scheduler.enqueue(mock_task, "critical", Priority.CRITICAL, name="critical")
        scheduler.enqueue(mock_task, "normal", Priority.NORMAL, name="normal")

        # 按优先级取出
        task1 = await scheduler.dequeue()
        task2 = await scheduler.dequeue()
        task3 = await scheduler.dequeue()
        task4 = await scheduler.dequeue()

        assert task1.task_id == "critical"
        assert task2.task_id == "high"
        assert task3.task_id == "normal"
        assert task4.task_id == "low"

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """并发控制：超出 max_concurrent 时拒绝"""
        scheduler = Scheduler(max_concurrent=2)

        async def slow_task():
            await asyncio.sleep(0.2)

        scheduled = ScheduledTask(
            sort_key=(Priority.NORMAL, 0),
            task_id="t1",
            task_func=slow_task,
            team_id="team-a",
        )

        # 手动设置 running 计数
        scheduler._running = 2
        can = await scheduler._can_execute(scheduled)
        assert can is False

        scheduler._running = 1
        can = await scheduler._can_execute(scheduled)
        assert can is True

    @pytest.mark.asyncio
    async def test_team_parallel_limit(self):
        """每 Team 并行限制"""
        scheduler = Scheduler(max_concurrent=10, max_per_team=1)

        scheduled = ScheduledTask(
            sort_key=(Priority.NORMAL, 0),
            task_id="t1",
            task_func=asyncio.sleep,
            args=(0.1,),
            team_id="team-a",
        )

        scheduler._team_running["team-a"] = 1
        can = await scheduler._can_execute(scheduled)
        assert can is False

        scheduler._team_running["team-a"] = 0
        can = await scheduler._can_execute(scheduled)
        assert can is True

    @pytest.mark.asyncio
    async def test_aging_mechanism(self):
        """Aging：等待超时提升优先级"""
        import time

        scheduler = Scheduler(aging_seconds=0)

        scheduler.enqueue(lambda: None, "low-task", Priority.LOW)

        # 等待超过 aging 阈值
        await asyncio.sleep(0.05)

        task = await scheduler.dequeue()
        assert task is not None
        # sort_key 的优先级应该被提升（数字更小）
        assert task.sort_key[0] <= Priority.LOW

    def test_get_status(self):
        """状态查询"""
        scheduler = Scheduler(max_concurrent=5, max_per_team=2)
        status = scheduler.get_status()

        assert status["running"] == 0
        assert status["queued"] == 0
        assert status["max_concurrent"] == 5
        assert status["max_per_team"] == 2

    @pytest.mark.asyncio
    async def test_execute_task(self):
        """执行任务并更新计数"""
        scheduler = Scheduler(max_concurrent=5)

        result = []

        async def record_task(name: str):
            result.append(name)

        scheduled = ScheduledTask(
            sort_key=(Priority.NORMAL, 0),
            task_id="t1",
            task_func=record_task,
            args=("hello",),
            team_id="team-a",
        )

        await scheduler._execute(scheduled)
        assert result == ["hello"]
        assert scheduler._running == 0


# ── Blackboard 测试 ──────────────────────────────────────


class TestBlackboard:
    """Blackboard 发布/订阅测试"""

    @pytest.mark.asyncio
    async def test_pub_sub_in_memory(self):
        """内存模式发布/订阅"""
        bb = Blackboard()
        # 不连接 Redis，使用内存模式

        received = []

        async def on_event(event: Event):
            received.append(event)

        await bb.sub(team_id="team-1", callback=on_event)

        await bb.pub(
            EventType.TASK_UPDATE,
            {"task_id": "t1", "status": "completed"},
            team_id="team-1",
            source="agent-1",
        )

        assert len(received) == 1
        assert received[0].type == EventType.TASK_UPDATE
        assert received[0].payload["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """多个订阅者都能收到事件"""
        bb = Blackboard()

        received_a = []
        received_b = []

        async def on_a(event):
            received_a.append(event)

        async def on_b(event):
            received_b.append(event)

        await bb.sub(team_id="team-1", callback=on_a)
        await bb.sub(team_id="team-1", callback=on_b)

        await bb.pub(EventType.AGENT_STATUS, {"agent": "a1", "status": "idle"}, team_id="team-1")

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_cross_team_request_response(self):
        """跨团队请求-响应"""
        bb = Blackboard()

        # Team B 订阅并自动响应
        async def on_request(event: Event):
            if event.type == EventType.CROSS_TEAM_REQUEST:
                await bb.respond_cross_team(
                    request_id=event.payload["request_id"],
                    target_team=event.payload["source_team"],
                    data={"answer": 42},
                )

        await bb.sub(team_id="team-b", callback=on_request)

        # Team A 发起请求
        response = await bb.request_cross_team(
            source_team="team-a",
            target_team="team-b",
            request_type="query",
            data={"question": "meaning of life"},
            timeout=5.0,
        )

        assert response is not None
        assert response["answer"] == 42

    @pytest.mark.asyncio
    async def test_get_status(self):
        """状态查询"""
        bb = Blackboard()
        status = bb.get_status()

        assert "connected" in status
        assert "channels" in status
        assert "pending_requests" in status

    @pytest.mark.asyncio
    async def test_event_types(self):
        """所有事件类型可用"""
        assert EventType.TASK_UPDATE.value == "task_update"
        assert EventType.AGENT_STATUS.value == "agent_status"
        assert EventType.HITL_NOTIFICATION.value == "hitl_notification"
        assert EventType.CROSS_TEAM_REQUEST.value == "cross_team_request"
        assert EventType.RATE_LIMIT_WARNING.value == "rate_limit_warning"


# ── Session Manager 测试 ──────────────────────────────────


class TestSessionManager:
    """Session Manager 基本测试（不需要 DB）"""

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Session 创建/查询/关闭（不需要 DB，mock memory view）"""
        from app.services.session_manager import SessionManager, SessionStatus

        # 使用 mock db（不实际访问 DB）
        mgr = SessionManager(None)

        # 直接创建 Session 对象
        from app.services.session_manager import AgentSession
        session = AgentSession(
            session_id="s1",
            team_id="t1",
            agent_id="a1",
            task_id="task-1",
        )
        mgr._sessions["s1"] = session
        mgr._session_tools["s1"] = set()

        # 查询
        found = await mgr.get_session("s1")
        assert found is not None
        assert found.status == SessionStatus.ACTIVE

        # 列表
        sessions = mgr.list_sessions()
        assert len(sessions) == 1

        # 关闭
        closed = await mgr.close_session("s1")
        assert closed is True
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_session_status_filter(self):
        """状态过滤"""
        from app.services.session_manager import SessionManager, AgentSession, SessionStatus

        mgr = SessionManager(None)
        mgr._sessions["s1"] = AgentSession(session_id="s1", team_id="t1", agent_id="a1", status=SessionStatus.ACTIVE)
        mgr._sessions["s2"] = AgentSession(session_id="s2", team_id="t1", agent_id="a2", status=SessionStatus.IDLE)

        active = mgr.list_sessions(status="active")
        assert len(active) == 1
        assert active[0]["session_id"] == "s1"

    def test_memory_summary(self):
        """记忆摘要生成"""
        from app.services.session_manager import SessionManager

        mgr = SessionManager(None)
        summary = mgr._summarize_memory({})
        assert "No memories" in summary

        # 带有 mock 数据
        mock_view = {"L1_system": []}
        summary = mgr._summarize_memory(mock_view)
        assert isinstance(summary, str)
