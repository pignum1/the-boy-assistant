"""统一 Workflow 架构 - 执行器单元测试

测试 8 种节点执行器的执行逻辑（纯逻辑，无数据库）
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.workflow_executors import (
    StartNodeExecutor,
    EndNodeExecutor,
    AgentNodeExecutor,
    RouterNodeExecutor,
    ConditionNodeExecutor,
    ParallelNodeExecutor,
    ValidationNodeExecutor,
    HITLNodeExecutor,
)
from app.models.workflow import WorkflowNode
from app.models.workflow_instance import WorkflowInstance, NodeExecution
from app.services.workflow_engine import ExecutionContext


class MockDB:
    """Mock 数据库会话"""
    def __init__(self):
        self.committed = False
        self.objects = {}

    def add(self, obj):
        return obj

    async def commit(self):
        self.committed = True

    async def get(self, model, id):
        return self.objects.get(id)

    async def refresh(self, obj):
        pass


class MockExecutionContext(ExecutionContext):
    """Mock 执行上下文"""
    def __init__(self):
        self.db = MockDB()
        self.user_input = "测试输入"
        self.session_id = uuid.uuid4()
        self._agents = {}

    def add_agent(self, agent_id: uuid.UUID, agent_data: dict):
        self._agents[agent_id] = agent_data

    async def get_agent(self, agent_id):
        """支持 UUID 或字符串 ID"""
        # 如果是字符串，尝试转换为 UUID
        if isinstance(agent_id, str):
            try:
                agent_id = uuid.UUID(agent_id)
            except ValueError:
                # 如果不是有效的 UUID 格式，直接用字符串查找
                for aid, data in self._agents.items():
                    if str(aid) == agent_id:
                        return data
                return None
        return self._agents.get(agent_id)

    async def get_llm_response(self, prompt: str, **kwargs):
        return {"content": "Mock LLM 响应"}


@pytest.fixture
def mock_context():
    """提供 Mock 执行上下文"""
    return MockExecutionContext()


@pytest.fixture
def mock_instance():
    """提供 Mock 工作流实例"""
    instance = WorkflowInstance(
        workflow_id=uuid.uuid4(),
        status="running",
        retry_count=0,
        hitl_pending=False,
    )
    instance.hitl_pending = False
    return instance


class TestStartNodeExecutor:
    """StartNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_start_node_execution(self, mock_context, mock_instance):
        """测试开始节点执行"""
        executor = StartNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(type="Start", label="开始", config={})

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        assert result["output"]["message"] == "Workflow started"
        assert result["next_edge_type"] == "Forward"


class TestEndNodeExecutor:
    """EndNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_end_node_execution(self, mock_context, mock_instance):
        """测试结束节点执行"""
        executor = EndNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(type="End", label="结束", config={})

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        assert result["output"]["message"] == "Workflow completed"


class TestRouterNodeExecutor:
    """RouterNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_round_robin_strategy(self, mock_context, mock_instance):
        """测试轮询策略"""
        executor = RouterNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Router",
            label="路由器",
            config={
                "strategy": "round_robin",
                "candidates": ["agent-1", "agent-2", "agent-3"],
            },
        )

        state = {}
        for i in range(5):
            result = await executor.execute(
                node=node,
                instance=mock_instance,
                state=state,
                context=mock_context,
            )
            expected = ["agent-1", "agent-2", "agent-3", "agent-1", "agent-2"]
            assert result["next_node_id"] == expected[i]

    @pytest.mark.asyncio
    async def test_priority_strategy(self, mock_context, mock_instance):
        """测试优先级策略"""
        executor = RouterNodeExecutor()
        executor.db = mock_context.db

        # 添加候选 Agent
        agent_id_1 = uuid.uuid4()
        agent_id_2 = uuid.uuid4()
        mock_context.add_agent(agent_id_1, {"id": agent_id_1, "name": "Agent 1"})
        mock_context.add_agent(agent_id_2, {"id": agent_id_2, "name": "Agent 2"})

        node = WorkflowNode(
            type="Router",
            label="路由器",
            config={
                "strategy": "priority",
                "candidates": [str(agent_id_1), str(agent_id_2)],
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        # 优先级策略返回第一个可用的
        assert result["next_node_id"] == str(agent_id_1)

    @pytest.mark.asyncio
    async def test_workload_strategy(self, mock_context, mock_instance):
        """测试负载均衡策略"""
        executor = RouterNodeExecutor()
        executor.db = mock_context.db

        # 添加候选 Agent
        agent_id_1 = uuid.uuid4()
        agent_id_2 = uuid.uuid4()
        mock_context.add_agent(agent_id_1, {"id": agent_id_1, "name": "Agent 1"})
        mock_context.add_agent(agent_id_2, {"id": agent_id_2, "name": "Agent 2"})

        node = WorkflowNode(
            type="Router",
            label="路由器",
            config={
                "strategy": "workload",
                "candidates": [str(agent_id_1), str(agent_id_2)],
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        # 负载均衡策略返回一个候选
        assert result["next_node_id"] in [str(agent_id_1), str(agent_id_2)]


class TestConditionNodeExecutor:
    """ConditionNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_condition_match(self, mock_context, mock_instance):
        """测试条件匹配"""
        executor = ConditionNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Condition",
            label="条件判断",
            config={
                "expression": "user_sentiment",
                "branches": {"positive": "node-1", "negative": "node-2"},
            },
        )

        state = {"user_sentiment": "positive"}

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state=state,
            context=mock_context,
        )

        assert result["next_node_id"] == "node-1"

    @pytest.mark.asyncio
    async def test_condition_default_branch(self, mock_context, mock_instance):
        """测试默认分支"""
        executor = ConditionNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Condition",
            label="条件判断",
            config={
                "expression": "unknown_value",
                "branches": {
                    "positive": "node-1",
                    "negative": "node-2",
                    "default": "node-fallback",
                },
            },
        )

        state = {"unknown_value": "other"}

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state=state,
            context=mock_context,
        )

        assert result["next_node_id"] == "node-fallback"


class TestValidationNodeExecutor:
    """ValidationNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_llm_validation_passed(self, mock_context, mock_instance):
        """测试 LLM 验证通过"""
        executor = ValidationNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Validation",
            label="验证",
            config={
                "validator": "LLM",
                "criteria": ["内容完整", "格式正确"],
                "on_fail": "reject",
            },
        )

        state = {"last_output": "完整且格式正确的内容"}

        # Mock LLM 返回通过结果
        with patch.object(executor, '_llm_validate', return_value=True):
            result = await executor.execute(
                node=node,
                instance=mock_instance,
                state=state,
                context=mock_context,
            )

        assert result["next_edge_type"] == "Forward"

    @pytest.mark.asyncio
    async def test_validation_failed(self, mock_context, mock_instance):
        """测试验证失败"""
        executor = ValidationNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Validation",
            label="验证",
            config={
                "validator": "LLM",
                "criteria": ["内容完整"],
                "on_fail": "reject",
            },
        )

        state = {"last_output": "不完整的内容"}

        # Mock LLM 返回失败结果
        with patch.object(executor, '_llm_validate', return_value=False):
            result = await executor.execute(
                node=node,
                instance=mock_instance,
                state=state,
                context=mock_context,
            )

        assert result["next_edge_type"] == "Reject"

    @pytest.mark.asyncio
    async def test_validation_on_fail_retry(self, mock_context, mock_instance):
        """测试验证失败重试"""
        executor = ValidationNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Validation",
            label="验证",
            config={
                "validator": "LLM",
                "criteria": ["内容完整"],
                "on_fail": "retry",
            },
        )

        state = {"last_output": "不完整的内容", "_last_node_id": "previous-node"}

        # Mock LLM 返回失败结果
        with patch.object(executor, '_llm_validate', return_value=False):
            result = await executor.execute(
                node=node,
                instance=mock_instance,
                state=state,
                context=mock_context,
            )

        assert result["next_node_id"] == "previous-node"


class TestHITLNodeExecutor:
    """HITLNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_hitl_approve_required(self, mock_context, mock_instance):
        """测试 HITL 审批要求"""
        executor = HITLNodeExecutor()
        executor.db = mock_context.db

        node_id = uuid.uuid4()
        node = WorkflowNode(
            id=node_id,
            type="HITL",
            label="人工审批",
            config={
                "action_type": "approve",
                "timeout": 3600,
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        assert result["output"]["hitl"] == "pending"
        assert mock_instance.hitl_pending is True
        assert mock_instance.hitl_node_id == node_id
        assert mock_instance.hitl_action_type == "approve"

    @pytest.mark.asyncio
    async def test_hitl_input_required(self, mock_context, mock_instance):
        """测试 HITL 输入要求"""
        executor = HITLNodeExecutor()
        executor.db = mock_context.db

        node_id = uuid.uuid4()
        node = WorkflowNode(
            id=node_id,
            type="HITL",
            label="人工输入",
            config={
                "action_type": "input",
                "timeout": 1800,
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        assert result["output"]["action_type"] == "input"
        assert mock_instance.hitl_pending is True


class TestParallelNodeExecutor:
    """ParallelNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, mock_context, mock_instance):
        """测试并行执行"""
        executor = ParallelNodeExecutor()
        executor.db = mock_context.db

        # Mock AgentNodeExecutor to avoid DB calls
        with patch.object(AgentNodeExecutor, 'execute', return_value={"output": {"response": "done"}}):
            node = WorkflowNode(
                type="Parallel",
                label="并行处理",
                config={
                    "merge_strategy": "all",
                    "branches": [
                        [  # 第一个分支 - 列表形式的节点序列
                            {"type": "Agent", "label": "分支1", "config": {"task": "task1"}},
                        ],
                        [  # 第二个分支
                            {"type": "Agent", "label": "分支2", "config": {"task": "task2"}},
                        ],
                    ],
                },
            )

            result = await executor.execute(
                node=node,
                instance=mock_instance,
                state={},
                context=mock_context,
            )

            assert result["output"]["parallel_result"]["merged"] == "all"

    @pytest.mark.asyncio
    async def test_parallel_first_strategy(self, mock_context, mock_instance):
        """测试并行首个完成策略"""
        executor = ParallelNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Parallel",
            label="并行处理",
            config={
                "merge_strategy": "first",
                "branches": [],  # 空分支
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        # 空分支返回空结果
        assert "parallel_result" in result["output"]

    @pytest.mark.asyncio
    async def test_parallel_majority_strategy(self, mock_context, mock_instance):
        """测试并行多数完成策略"""
        executor = ParallelNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Parallel",
            label="并行处理",
            config={
                "merge_strategy": "majority",
                "branches": [],  # 空分支
            },
        )

        result = await executor.execute(
            node=node,
            instance=mock_instance,
            state={},
            context=mock_context,
        )

        assert "parallel_result" in result["output"]


class TestAgentNodeExecutor:
    """AgentNodeExecutor 测试"""

    @pytest.mark.asyncio
    async def test_agent_execution_success(self, mock_context, mock_instance):
        """测试 Agent 节点执行成功"""
        executor = AgentNodeExecutor()
        executor.db = mock_context.db

        # 创建 Agent 数据
        agent_id = uuid.uuid4()
        agent_data = {
            "id": agent_id,
            "name": "测试Agent",
            "system_prompt": "你是一个测试助手",
        }
        mock_context.add_agent(agent_id, agent_data)

        # Mock Agent 模型对象
        mock_agent = MagicMock()
        mock_agent.id = agent_id
        mock_agent.name = "测试Agent"
        mock_agent.system_prompt = "你是一个测试助手"

        node = WorkflowNode(
            type="Agent",
            label="处理任务",
            config={
                "agent_id": str(agent_id),
                "prompt_template": "请处理: {user_input}",
            },
        )

        # Mock agent_chat 函数 - 需要在正确的位置 mock
        with patch('app.services.agent_chat.agent_chat', return_value={"content": "处理完成"}) as mock_chat:
            with patch.object(mock_context.db, 'get', return_value=mock_agent):
                result = await executor.execute(
                    node=node,
                    instance=mock_instance,
                    state={},
                    context=mock_context,
                )

        assert result["output"]["response"] == "处理完成"
        assert result["agent_id"] == str(agent_id)

    @pytest.mark.asyncio
    async def test_agent_execution_missing_agent(self, mock_context, mock_instance):
        """测试 Agent 节点缺少 Agent 配置"""
        executor = AgentNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Agent",
            label="处理任务",
            config={},  # 缺少 agent_id
        )

        with pytest.raises(ValueError, match="agent_id"):
            await executor.execute(
                node=node,
                instance=mock_instance,
                state={},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_agent_execution_agent_not_found(self, mock_context, mock_instance):
        """测试 Agent 节点 Agent 不存在"""
        executor = AgentNodeExecutor()
        executor.db = mock_context.db

        node = WorkflowNode(
            type="Agent",
            label="处理任务",
            config={
                "agent_id": str(uuid.uuid4()),  # 不存在的 Agent
            },
        )

        with pytest.raises(ValueError, match="not found"):
            await executor.execute(
                node=node,
                instance=mock_instance,
                state={},
                context=mock_context,
            )
