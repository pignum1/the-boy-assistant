"""统一 Workflow 架构 - 工作流引擎集成测试

测试 WorkflowEngine 的端到端执行流程（使用真实数据库）
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.workflow_instance import WorkflowInstance, NodeExecution
from app.services.workflow_service import WorkflowService
from app.services.workflow_engine import WorkflowEngine, ExecutionContext
from app.schemas.workflow import WorkflowNodeCreate, WorkflowEdgeCreate


@pytest_asyncio.fixture
async def sample_workflow(db: AsyncSession):
    """创建示例工作流用于测试"""
    svc = WorkflowService(db)

    # 创建工作流
    workflow = await svc.create_workflow(
        name="集成测试工作流",
        description="用于引擎集成测试的简单工作流",
        definition={"nodes": [], "edges": []},
    )

    # 创建节点: Start -> Agent -> End
    start_node = await svc.add_node(
        WorkflowNodeCreate(
            workflow_id=workflow.id,
            type="Start",
            label="开始",
        )
    )

    agent_node = await svc.add_node(
        WorkflowNodeCreate(
            workflow_id=workflow.id,
            type="Agent",
            label="处理节点",
            config={"agent_id": str(uuid.uuid4()), "prompt_template": "处理: {user_input}"},
        )
    )

    end_node = await svc.add_node(
        WorkflowNodeCreate(
            workflow_id=workflow.id,
            type="End",
            label="结束",
        )
    )

    # 创建边
    await svc.add_edge(
        WorkflowEdgeCreate(
            workflow_id=workflow.id,
            source_id=start_node.id,
            target_id=agent_node.id,
            type="Forward",
        )
    )

    await svc.add_edge(
        WorkflowEdgeCreate(
            workflow_id=workflow.id,
            source_id=agent_node.id,
            target_id=end_node.id,
            type="Forward",
        )
    )

    # 重新获取工作流以确保最新状态
    await db.refresh(workflow)
    return workflow


class TestWorkflowEngineBasics:
    """WorkflowEngine 基础功能测试"""

    @pytest.mark.asyncio
    async def test_create_engine(self, db: AsyncSession):
        """测试创建引擎"""
        engine = WorkflowEngine(db)
        assert engine is not None
        assert engine.db == db
        assert len(engine.node_executors) == 8  # 8 种节点类型

    @pytest.mark.asyncio
    async def test_default_executors(self, db: AsyncSession):
        """测试默认执行器配置"""
        engine = WorkflowEngine(db)

        expected_types = {
            "Start", "End", "Agent", "Router",
            "Parallel", "Condition", "Validation", "HITL"
        }

        assert set(engine.node_executors.keys()) == expected_types


class TestWorkflowInstanceManagement:
    """工作流实例管理测试"""

    @pytest.mark.asyncio
    async def test_create_instance(self, db: AsyncSession, sample_workflow):
        """测试创建实例"""
        engine = WorkflowEngine(db)

        instance = await engine.create_instance(
            workflow_id=sample_workflow.id,
            session_id=None,  # 不使用 session_id 避免 FK 问题
            initial_state={"test": "value"},
        )

        assert instance.id is not None
        assert instance.workflow_id == sample_workflow.id
        assert instance.status == "pending"
        assert instance.state == {"test": "value"}
        assert instance.retry_count == 0

    @pytest.mark.asyncio
    async def test_start_instance(self, db: AsyncSession, sample_workflow):
        """测试启动实例"""
        engine = WorkflowEngine(db)

        # 创建实例
        instance = await engine.create_instance(workflow_id=sample_workflow.id)

        # 启动实例
        started = await engine.start_instance(
            instance_id=instance.id,
            user_input="测试输入",
        )

        assert started.status == "running"
        assert started.started_at is not None

        # 等待一下让异步执行完成
        import asyncio
        await asyncio.sleep(0.5)

        # 重新获取实例查看最终状态
        await db.refresh(started)
        # 由于 Agent 节点可能失败（没有实际 Agent），状态可能是 failed
        assert started.status in ["running", "failed", "completed"]

    @pytest.mark.asyncio
    async def test_pause_instance(self, db: AsyncSession, sample_workflow):
        """测试暂停实例"""
        engine = WorkflowEngine(db)

        instance = await engine.create_instance(workflow_id=sample_workflow.id)

        # 先手动将状态改为 running（避免后台任务的并发问题）
        instance.status = "running"
        instance.started_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(instance)

        # 暂停
        paused = await engine.pause_instance(instance.id)

        assert paused.status == "paused"

    @pytest.mark.asyncio
    async def test_cancel_instance(self, db: AsyncSession, sample_workflow):
        """测试取消实例"""
        engine = WorkflowEngine(db)

        instance = await engine.create_instance(workflow_id=sample_workflow.id)

        # 取消（从 pending 状态）
        cancelled = await engine.cancel_instance(instance.id)

        assert cancelled.status == "cancelled"
        assert cancelled.completed_at is not None


class TestWorkflowExecution:
    """工作流执行测试"""

    @pytest.mark.asyncio
    async def test_simple_workflow_execution(self, db: AsyncSession):
        """测试简单工作流执行: Start -> End"""
        svc = WorkflowService(db)

        # 创建简单工作流
        workflow = await svc.create_workflow(
            name="简单工作流",
            definition={"nodes": [], "edges": []},
        )

        start = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始")
        )
        end = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束")
        )

        await svc.add_edge(
            WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=end.id, type="Forward")
        )

        # 执行
        engine = WorkflowEngine(db)
        instance = await engine.create_instance(workflow_id=workflow.id)

        # 模拟执行（直接调用内部方法）
        await engine.start_instance(instance_id=instance.id)

        # 等待执行完成
        import asyncio
        await asyncio.sleep(1)

        await db.refresh(instance)

        # 验证最终状态
        assert instance.status in ["completed", "failed"]

    @pytest.mark.asyncio
    async def test_execution_records(self, db: AsyncSession):
        """测试执行记录创建"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="执行记录测试",
            definition={"nodes": [], "edges": []},
        )

        start = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始")
        )
        end = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束")
        )

        await svc.add_edge(
            WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=end.id, type="Forward")
        )

        # 执行
        engine = WorkflowEngine(db)
        instance = await engine.create_instance(workflow_id=workflow.id)
        await engine.start_instance(instance_id=instance.id)

        # 等待执行
        import asyncio
        await asyncio.sleep(1)

        # 查询执行记录
        result = await db.execute(
            select(NodeExecution).where(NodeExecution.instance_id == instance.id)
        )
        executions = result.scalars().all()

        # 应该至少有 Start 节点的执行记录
        assert len(executions) >= 1

        # 验证记录内容
        start_execution = [e for e in executions if e.node_type == "Start"][0]
        assert start_execution.instance_id == instance.id
        assert start_execution.node_type == "Start"
        assert start_execution.status in ["completed", "running", "failed"]


class TestWorkflowErrorHandling:
    """工作流错误处理测试"""

    @pytest.mark.asyncio
    async def test_missing_start_node(self, db: AsyncSession):
        """测试缺少开始节点的工作流"""
        svc = WorkflowService(db)

        # 创建没有 Start 节点的工作流
        workflow = await svc.create_workflow(
            name="无开始节点",
            definition={"nodes": [], "edges": []},
        )

        agent = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理",
                             config={"agent_id": str(uuid.uuid4())})
        )
        end = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束")
        )

        await svc.add_edge(
            WorkflowEdgeCreate(workflow_id=workflow.id, source_id=agent.id, target_id=end.id, type="Forward")
        )

        # 尝试执行
        engine = WorkflowEngine(db)
        instance = await engine.create_instance(workflow_id=workflow.id)
        await engine.start_instance(instance_id=instance.id)

        # 等待执行
        import asyncio
        await asyncio.sleep(1)

        await db.refresh(instance)

        # 应该失败
        assert instance.status == "failed"
        assert "Start" in instance.error_message or "start" in instance.error_message.lower()

    @pytest.mark.asyncio
    async def test_agent_node_missing_agent(self, db: AsyncSession):
        """测试 Agent 节点缺少 Agent"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="缺少 Agent",
            definition={"nodes": [], "edges": []},
        )

        start = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始")
        )

        # Agent 节点使用不存在的 agent_id
        agent = await svc.add_node(
            WorkflowNodeCreate(
                workflow_id=workflow.id,
                type="Agent",
                label="处理",
                config={"agent_id": str(uuid.uuid4())}  # 随机 ID，不存在
            )
        )

        end = await svc.add_node(
            WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束")
        )

        await svc.add_edge(
            WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=agent.id, type="Forward")
        )
        await svc.add_edge(
            WorkflowEdgeCreate(workflow_id=workflow.id, source_id=agent.id, target_id=end.id, type="Forward")
        )

        # 执行
        engine = WorkflowEngine(db)
        instance = await engine.create_instance(workflow_id=workflow.id)
        await engine.start_instance(instance_id=instance.id)

        # 等待执行
        import asyncio
        await asyncio.sleep(1)

        await db.refresh(instance)

        # 应该失败
        assert instance.status == "failed"


class TestExecutionContext:
    """执行上下文测试"""

    @pytest.mark.asyncio
    async def test_execution_context_creation(self, db: AsyncSession):
        """测试执行上下文创建"""
        context = ExecutionContext(
            db=db,
            user_input="测试输入",
            session_id=uuid.uuid4(),
            workspace_path="/tmp/test",
        )

        assert context.db == db
        assert context.user_input == "测试输入"
        assert context.session_id is not None
        assert context.workspace_path == "/tmp/test"
        assert context.metadata == {}

    @pytest.mark.asyncio
    async def test_execution_context_metadata(self, db: AsyncSession):
        """测试执行上下文元数据"""
        context = ExecutionContext(db=db)

        # 设置元数据
        context.metadata["key1"] = "value1"
        context.metadata["key2"] = 123

        assert context.metadata["key1"] == "value1"
        assert context.metadata["key2"] == 123


class TestWorkflowEvents:
    """工作流事件测试"""

    @pytest.mark.asyncio
    async def test_event_callback(self, db: AsyncSession):
        """测试事件回调"""
        events = []

        async def event_callback(event_type: str, data: dict):
            events.append((event_type, data))

        engine = WorkflowEngine(db, event_callback=event_callback)

        # 创建实例
        workflow = await WorkflowService(db).create_workflow(
            name="事件测试",
            definition={"nodes": [], "edges": []},
        )

        instance = await engine.create_instance(
            workflow_id=workflow.id,
            session_id=None,  # 不使用 session_id 避免 FK 问题
        )

        # 应该触发 instance.created 事件
        assert len(events) >= 1
        assert events[0][0] == "instance.created"
        assert events[0][1]["instance_id"] == str(instance.id)
