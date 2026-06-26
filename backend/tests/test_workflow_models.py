"""统一 Workflow 架构 - 数据模型单元测试

测试 Workflow, WorkflowNode, WorkflowEdge, WorkflowInstance, NodeExecution 模型
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.workflow_instance import WorkflowInstance, NodeExecution
from app.models.workflow_template import WorkflowTemplate


class TestWorkflowModel:
    """Workflow 模型测试"""

    @pytest.mark.asyncio
    async def test_create_workflow_minimal(self, db: AsyncSession):
        """测试创建最小工作流"""
        workflow = Workflow(
            name="测试工作流",
            description="测试描述",
            definition={
                "nodes": [{"id": "n1", "type": "Start", "label": "开始"}],
                "edges": []
            },
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        assert workflow.id is not None
        assert workflow.name == "测试工作流"
        assert workflow.status == "draft"
        assert workflow.version == 1
        assert workflow.created_at is not None
        assert workflow.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_workflow_with_template(self, db: AsyncSession):
        """测试创建模板工作流"""
        workflow = Workflow(
            name="客服处理模板",
            description="客服场景的标准工作流",
            template_type="customer_service",
            definition={
                "nodes": [],
                "edges": []
            },
            version=1,
            is_template=True,
            status="active",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        assert workflow.is_template is True
        assert workflow.template_type == "customer_service"
        assert workflow.status == "active"

    @pytest.mark.asyncio
    async def test_workflow_definition_jsonb(self, db: AsyncSession):
        """测试 JSONB 字段的存储和读取"""
        definition = {
            "nodes": [
                {"id": "n1", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "n2", "type": "Agent", "label": "处理", "config": {"agent_id": str(uuid.uuid4())}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "Forward"}
            ]
        }

        workflow = Workflow(
            name="测试 JSONB",
            definition=definition,
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        # 读取并验证
        assert len(workflow.definition["nodes"]) == 2
        assert workflow.definition["nodes"][0]["type"] == "Start"
        assert workflow.definition["edges"][0]["type"] == "Forward"

    @pytest.mark.asyncio
    async def test_workflow_version_increment(self, db: AsyncSession):
        """测试版本号自增"""
        workflow = Workflow(
            name="版本测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        assert workflow.version == 1

        # 更新版本
        workflow.version = 2
        await db.commit()
        await db.refresh(workflow)

        assert workflow.version == 2

    @pytest.mark.asyncio
    async def test_workflow_status_transitions(self, db: AsyncSession):
        """测试状态流转"""
        workflow = Workflow(
            name="状态测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        # draft -> active
        workflow.status = "active"
        await db.commit()
        await db.refresh(workflow)
        assert workflow.status == "active"

        # active -> archived
        workflow.status = "archived"
        await db.commit()
        await db.refresh(workflow)
        assert workflow.status == "archived"


class TestWorkflowNodeModel:
    """WorkflowNode 模型测试"""

    @pytest.mark.asyncio
    async def test_create_node(self, db: AsyncSession):
        """测试创建节点"""
        workflow = Workflow(
            name="测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        node = WorkflowNode(
            workflow_id=workflow.id,
            type="Agent",
            label="处理节点",
            config={"agent_id": str(uuid.uuid4()), "prompt_template": "处理: {user_input}"},
            position_x=200,
            position_y=150,
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)

        assert node.id is not None
        assert node.workflow_id == workflow.id
        assert node.type == "Agent"
        assert node.label == "处理节点"
        assert node.config["agent_id"] is not None
        assert node.position_x == 200
        assert node.position_y == 150

    @pytest.mark.asyncio
    async def test_node_types(self, db: AsyncSession):
        """测试所有节点类型"""
        workflow = Workflow(
            name="节点类型测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node_types = ["Start", "End", "Agent", "Router", "Parallel", "Condition", "HITL", "Validation"]

        for node_type in node_types:
            node = WorkflowNode(
                workflow_id=workflow.id,
                type=node_type,
                label=f"{node_type} 节点",
                config={},
            )
            db.add(node)

        await db.commit()

        # 验证所有节点类型都已创建
        from sqlalchemy import select
        result = await db.execute(
            select(WorkflowNode).where(WorkflowNode.workflow_id == workflow.id)
        )
        nodes = result.scalars().all()

        assert len(nodes) == len(node_types)
        created_types = {n.type for n in nodes}
        assert created_types == set(node_types)

    @pytest.mark.asyncio
    async def test_node_config_variations(self, db: AsyncSession):
        """测试不同节点的配置结构"""
        workflow = Workflow(
            name="配置测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        # Agent 节点配置
        agent_node = WorkflowNode(
            workflow_id=workflow.id,
            type="Agent",
            label="Agent 节点",
            config={
                "agent_id": str(uuid.uuid4()),
                "prompt_template": "请处理: {input}",
                "model_config": {"model": "claude-3-5-sonnet", "temperature": 0.7},
            },
        )

        # Router 节点配置
        router_node = WorkflowNode(
            workflow_id=workflow.id,
            type="Router",
            label="Router 节点",
            config={
                "strategy": "round_robin",
                "candidates": ["agent-1", "agent-2"],
                "fallback": "agent-default",
            },
        )

        # Condition 节点配置
        condition_node = WorkflowNode(
            workflow_id=workflow.id,
            type="Condition",
            label="Condition 节点",
            config={
                "expression": "sentiment",
                "branches": {"positive": "n1", "negative": "n2"},
            },
        )

        db.add_all([agent_node, router_node, condition_node])
        await db.commit()

        # 验证配置正确存储
        assert agent_node.config["model_config"]["temperature"] == 0.7
        assert router_node.config["strategy"] == "round_robin"
        assert condition_node.config["branches"]["positive"] == "n1"


class TestWorkflowEdgeModel:
    """WorkflowEdge 模型测试"""

    @pytest.mark.asyncio
    async def test_create_edge(self, db: AsyncSession):
        """测试创建边"""
        workflow = Workflow(
            name="测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        # 创建两个节点
        node1 = WorkflowNode(workflow_id=workflow.id, type="Start", label="开始")
        node2 = WorkflowNode(workflow_id=workflow.id, type="End", label="结束")
        db.add_all([node1, node2])
        await db.commit()
        await db.refresh(node1)
        await db.refresh(node2)

        # 创建边
        edge = WorkflowEdge(
            workflow_id=workflow.id,
            source_id=node1.id,
            target_id=node2.id,
            type="Forward",
        )
        db.add(edge)
        await db.commit()
        await db.refresh(edge)

        assert edge.id is not None
        assert edge.workflow_id == workflow.id
        assert edge.source_id == node1.id
        assert edge.target_id == node2.id
        assert edge.type == "Forward"

    @pytest.mark.asyncio
    async def test_edge_types(self, db: AsyncSession):
        """测试所有边类型"""
        workflow = Workflow(
            name="边类型测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        # 创建节点
        node1 = WorkflowNode(workflow_id=workflow.id, type="Start", label="开始")
        node2 = WorkflowNode(workflow_id=workflow.id, type="End", label="结束")
        db.add_all([node1, node2])
        await db.commit()
        await db.refresh(node1)
        await db.refresh(node2)

        edge_types = ["Forward", "Reject", "Escalate", "Timeout", "Fallback"]

        for edge_type in edge_types:
            edge = WorkflowEdge(
                workflow_id=workflow.id,
                source_id=node1.id,
                target_id=node2.id,
                type=edge_type,
            )
            db.add(edge)

        await db.commit()

        # 验证所有边类型都已创建
        from sqlalchemy import select
        result = await db.execute(
            select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow.id)
        )
        edges = result.scalars().all()

        assert len(edges) == len(edge_types)
        created_types = {e.type for e in edges}
        assert created_types == set(edge_types)

    @pytest.mark.asyncio
    async def test_edge_with_condition(self, db: AsyncSession):
        """测试带条件的边"""
        workflow = Workflow(
            name="条件边测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node1 = WorkflowNode(workflow_id=workflow.id, type="Condition", label="判断")
        node2 = WorkflowNode(workflow_id=workflow.id, type="Agent", label="处理")
        db.add_all([node1, node2])
        await db.commit()
        await db.refresh(node1)
        await db.refresh(node2)

        edge = WorkflowEdge(
            workflow_id=workflow.id,
            source_id=node1.id,
            target_id=node2.id,
            type="Forward",
            condition={"expression": "result == 'success'"},
        )
        db.add(edge)
        await db.commit()
        await db.refresh(edge)

        assert edge.condition is not None
        assert edge.condition["expression"] == "result == 'success'"


class TestWorkflowInstanceModel:
    """WorkflowInstance 模型测试"""

    @pytest.mark.asyncio
    async def test_create_instance(self, db: AsyncSession):
        """测试创建实例"""
        workflow = Workflow(
            name="测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="pending",
            retry_count=0,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        assert instance.id is not None
        assert instance.workflow_id == workflow.id
        assert instance.status == "pending"
        assert instance.retry_count == 0
        assert instance.hitl_pending is False

    @pytest.mark.asyncio
    async def test_instance_status_transitions(self, db: AsyncSession):
        """测试实例状态流转"""
        workflow = Workflow(
            name="状态测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="pending",
            retry_count=0,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        # pending -> running
        instance.status = "running"
        instance.started_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(instance)
        assert instance.status == "running"
        assert instance.started_at is not None

        # running -> completed
        instance.status = "completed"
        instance.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.completed_at is not None

    @pytest.mark.asyncio
    async def test_instance_hitl_state(self, db: AsyncSession):
        """测试 HITL 状态"""
        workflow = Workflow(
            name="HITL 测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="running",
            retry_count=0,
            hitl_pending=True,
            hitl_node_id=uuid.uuid4(),
            hitl_action_type="approve",
            hitl_timeout_at=datetime.now(timezone.utc).replace(second=0, microsecond=0) + __import__('datetime').timedelta(hours=1),
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        assert instance.hitl_pending is True
        assert instance.hitl_action_type == "approve"
        assert instance.hitl_timeout_at is not None

    @pytest.mark.asyncio
    async def test_instance_error_state(self, db: AsyncSession):
        """测试错误状态"""
        workflow = Workflow(
            name="错误测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="failed",
            error_message="执行失败: Agent 不可用",
            retry_count=2,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        assert instance.status == "failed"
        assert instance.error_message == "执行失败: Agent 不可用"
        assert instance.retry_count == 2


class TestNodeExecutionModel:
    """NodeExecution 模型测试"""

    @pytest.mark.asyncio
    async def test_create_execution(self, db: AsyncSession):
        """测试创建执行记录"""
        workflow = Workflow(
            name="测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="running",
            retry_count=0,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        execution = NodeExecution(
            instance_id=instance.id,
            node_id=None,  # 暂时设为 None，避免外键约束
            node_type="Agent",
            node_label="处理节点",
            status="running",
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        assert execution.id is not None
        assert execution.instance_id == instance.id
        assert execution.node_type == "Agent"
        assert execution.status == "running"

    @pytest.mark.asyncio
    async def test_execution_completion(self, db: AsyncSession):
        """测试执行完成状态"""
        workflow = Workflow(
            name="完成测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="running",
            retry_count=0,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        execution = NodeExecution(
            instance_id=instance.id,
            node_id=None,  # 暂时设为 None，避免外键约束
            node_type="Agent",
            node_label="处理节点",
            status="running",
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        # 标记完成
        execution.status = "completed"
        execution.output = {"result": "处理成功", "confidence": 0.95}
        execution.completed_at = datetime.now(timezone.utc)
        execution.agent_id = None  # 暂时设为 None，避免外键约束
        execution.agent_name = "测试Agent"
        execution.prompt_tokens = 100
        execution.completion_tokens = 200

        await db.commit()
        await db.refresh(execution)

        assert execution.status == "completed"
        assert execution.output["result"] == "处理成功"
        assert execution.completed_at is not None
        assert execution.agent_name == "测试Agent"
        assert execution.prompt_tokens == 100

    @pytest.mark.asyncio
    async def test_execution_failure(self, db: AsyncSession):
        """测试执行失败状态"""
        workflow = Workflow(
            name="失败测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="active",
        )
        db.add(workflow)
        await db.commit()

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="running",
            retry_count=0,
            hitl_pending=False,
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        execution = NodeExecution(
            instance_id=instance.id,
            node_id=None,  # 暂时设为 None，避免外键约束
            node_type="Agent",
            node_label="处理节点",
            status="running",
            retry_count=1,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        # 标记失败
        execution.status = "failed"
        execution.error_message = "LLM 调用超时"
        execution.completed_at = datetime.now(timezone.utc)
        execution.retry_count = 2

        await db.commit()
        await db.refresh(execution)

        assert execution.status == "failed"
        assert execution.error_message == "LLM 调用超时"
        assert execution.retry_count == 2


class TestWorkflowTemplateModel:
    """WorkflowTemplate 模型测试"""

    @pytest.mark.asyncio
    async def test_create_template(self, db: AsyncSession):
        """测试创建模板"""
        unique_type = f"customer_service_{uuid.uuid4().hex[:6]}"
        template = WorkflowTemplate(
            template_type=unique_type,
            name="客服处理模板",
            description="标准客服场景工作流",
            definition={
                "nodes": [
                    {"id": "n1", "type": "Start", "label": "开始"},
                    {"id": "n2", "type": "Agent", "label": "理解需求"},
                    {"id": "n3", "type": "End", "label": "结束"},
                ],
                "edges": [
                    {"source": "n1", "target": "n2", "type": "Forward"},
                    {"source": "n2", "target": "n3", "type": "Forward"},
                ]
            },
            default_config={
                "timeout": 300,
                "max_retries": 3,
            },
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)

        assert template.id is not None
        assert template.template_type == unique_type
        assert template.name == "客服处理模板"
        assert len(template.definition["nodes"]) == 3
        assert template.default_config["timeout"] == 300

    @pytest.mark.asyncio
    async def test_template_preset_types(self, db: AsyncSession):
        """测试预设模板类型"""
        suffix = uuid.uuid4().hex[:6]
        preset_templates = [
            (f"free_discussion_{suffix}", "自由讨论", "多 Agent 自由讨论场景"),
            (f"supervisor_dispatch_{suffix}", "主管分发", "主管分派任务给成员"),
            (f"sequential_{suffix}", "顺序执行", "按顺序执行多个节点"),
            (f"product_development_{suffix}", "产品开发", "产品开发流程"),
            (f"hotfix_{suffix}", "热修复", "紧急修复流程"),
        ]

        for template_type, name, description in preset_templates:
            template = WorkflowTemplate(
                template_type=template_type,
                name=name,
                description=description,
                definition={"nodes": [], "edges": []},
            )
            db.add(template)

        await db.commit()

        # 验证本次创建的预设模板都已创建
        from sqlalchemy import select
        result = await db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.template_type.in_([t[0] for t in preset_templates])
            )
        )
        templates = result.scalars().all()

        assert len(templates) == len(preset_templates)
