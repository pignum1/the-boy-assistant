"""统一 Workflow 架构 - 服务层测试

测试 WorkflowService 的 CRUD、节点/边管理、验证功能
"""

import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.services.workflow_service import WorkflowService
from app.schemas.workflow import (
    WorkflowNodeCreate,
    WorkflowNodeUpdate,
    WorkflowEdgeCreate,
)


class TestWorkflowServiceCRUD:
    """WorkflowService CRUD 操作测试"""

    @pytest.mark.asyncio
    async def test_create_workflow(self, db: AsyncSession):
        """测试创建工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="测试工作流",
            description="测试描述",
            template_type="custom",
            definition={
                "nodes": [{"id": "n1", "type": "Start", "label": "开始"}],
                "edges": []
            },
        )

        assert workflow.id is not None
        assert workflow.name == "测试工作流"
        assert workflow.description == "测试描述"
        assert workflow.template_type == "custom"
        assert workflow.status == "draft"
        assert workflow.version == 1

    @pytest.mark.asyncio
    async def test_get_workflow(self, db: AsyncSession):
        """测试获取工作流"""
        svc = WorkflowService(db)

        # 先创建
        created = await svc.create_workflow(
            name="获取测试",
            definition={"nodes": [], "edges": []},
        )

        # 再获取
        workflow = await svc.get_workflow(created.id)
        assert workflow is not None
        assert workflow.id == created.id
        assert workflow.name == "获取测试"

    @pytest.mark.asyncio
    async def test_list_workflows(self, db: AsyncSession):
        """测试列出工作流"""
        svc = WorkflowService(db)

        # 创建多个工作流
        await svc.create_workflow(name="工作流1", definition={"nodes": [], "edges": []})
        await svc.create_workflow(name="工作流2", definition={"nodes": [], "edges": []})

        # 列出
        workflows = await svc.list_workflows()
        assert len(workflows) >= 2

    @pytest.mark.asyncio
    async def test_update_workflow(self, db: AsyncSession):
        """测试更新工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="原始名称",
            definition={"nodes": [], "edges": []},
        )

        updated = await svc.update_workflow(
            workflow.id,
            name="更新后名称",
            description="更新描述",
        )

        assert updated.name == "更新后名称"
        assert updated.description == "更新描述"

    @pytest.mark.asyncio
    async def test_delete_workflow(self, db: AsyncSession):
        """测试删除工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="待删除",
            definition={"nodes": [], "edges": []},
        )

        result = await svc.delete_workflow(workflow.id)
        assert result is True

        # 验证已删除
        deleted = await svc.get_workflow(workflow.id)
        assert deleted is None


class TestWorkflowServiceNodes:
    """WorkflowService 节点管理测试"""

    @pytest.mark.asyncio
    async def test_add_node(self, db: AsyncSession):
        """测试添加节点"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="节点测试",
            definition={"nodes": [], "edges": []},
        )

        node = await svc.add_node(
            WorkflowNodeCreate(
                workflow_id=workflow.id,
                type="Agent",
                label="处理节点",
                config={"agent_id": str(uuid.uuid4())},
                position_x=100,
                position_y=200,
            )
        )

        assert node.id is not None
        assert node.type == "Agent"
        assert node.label == "处理节点"
        assert node.position_x == 100
        assert node.position_y == 200

    @pytest.mark.asyncio
    async def test_update_node(self, db: AsyncSession):
        """测试更新节点"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="更新节点测试",
            definition={"nodes": [], "edges": []},
        )

        node = await svc.add_node(
            WorkflowNodeCreate(
                workflow_id=workflow.id,
                type="Agent",
                label="原始标签",
                config={},
            )
        )

        updated = await svc.update_node(
            node.id,
            WorkflowNodeUpdate(label="更新标签", config={"agent_id": str(uuid.uuid4())})
        )

        assert updated.label == "更新标签"
        assert "agent_id" in updated.config

    @pytest.mark.asyncio
    async def test_delete_node(self, db: AsyncSession):
        """测试删除节点"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="删除节点测试",
            definition={"nodes": [], "edges": []},
        )

        node = await svc.add_node(
            WorkflowNodeCreate(
                workflow_id=workflow.id,
                type="Agent",
                label="待删除",
                config={},
            )
        )

        result = await svc.delete_node(node.id)
        assert result is True

        # 验证已删除
        node_result = await db.execute(select(WorkflowNode).where(WorkflowNode.id == node.id))
        assert node_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_get_nodes(self, db: AsyncSession):
        """测试获取工作流的所有节点"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="获取节点测试",
            definition={"nodes": [], "edges": []},
        )

        # 添加多个节点
        await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))
        await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        nodes = await svc.get_nodes(workflow.id)
        assert len(nodes) == 3
        node_types = {n.type for n in nodes}
        assert node_types == {"Start", "Agent", "End"}


class TestWorkflowServiceEdges:
    """WorkflowService 边管理测试"""

    @pytest.mark.asyncio
    async def test_add_edge(self, db: AsyncSession):
        """测试添加边"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="边测试",
            definition={"nodes": [], "edges": []},
        )

        node1 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        node2 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        edge = await svc.add_edge(
            WorkflowEdgeCreate(
                workflow_id=workflow.id,
                source_id=node1.id,
                target_id=node2.id,
                type="Forward",
            )
        )

        assert edge.id is not None
        assert edge.source_id == node1.id
        assert edge.target_id == node2.id
        assert edge.type == "Forward"

    @pytest.mark.asyncio
    async def test_delete_edge(self, db: AsyncSession):
        """测试删除边"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="删除边测试",
            definition={"nodes": [], "edges": []},
        )

        node1 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        node2 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        edge = await svc.add_edge(
            WorkflowEdgeCreate(
                workflow_id=workflow.id,
                source_id=node1.id,
                target_id=node2.id,
                type="Forward",
            )
        )

        result = await svc.delete_edge(edge.id)
        assert result is True

        # 验证已删除
        edge_result = await db.execute(select(WorkflowEdge).where(WorkflowEdge.id == edge.id))
        assert edge_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_get_edges(self, db: AsyncSession):
        """测试获取工作流的所有边"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="获取边测试",
            definition={"nodes": [], "edges": []},
        )

        node1 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        node2 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))
        node3 = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        # 添加多条边
        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=node1.id, target_id=node2.id, type="Forward"))
        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=node2.id, target_id=node3.id, type="Forward"))
        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=node2.id, target_id=node1.id, type="Reject"))

        edges = await svc.get_edges(workflow.id)
        assert len(edges) == 3
        edge_types = {e.type for e in edges}
        assert edge_types == {"Forward", "Reject"}


class TestWorkflowServiceValidation:
    """WorkflowService 验证功能测试"""

    @pytest.mark.asyncio
    async def test_validate_valid_workflow(self, db: AsyncSession):
        """测试验证有效的工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="有效工作流",
            definition={"nodes": [], "edges": []},
        )

        # 创建有效的节点和边
        start = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        agent = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))
        end = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=agent.id, type="Forward"))
        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=agent.id, target_id=end.id, type="Forward"))

        # 验证
        result = await svc.validate_workflow(workflow.id)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert result["node_count"] == 3
        assert result["edge_count"] == 2

    @pytest.mark.asyncio
    async def test_validate_empty_workflow(self, db: AsyncSession):
        """测试验证空工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="空工作流",
            definition={"nodes": [], "edges": []},
        )

        result = await svc.validate_workflow(workflow.id)

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_no_start_node(self, db: AsyncSession):
        """测试验证没有开始节点的工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="无开始节点",
            definition={"nodes": [], "edges": []},
        )

        # 只创建 Agent 和 End 节点
        agent = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))
        end = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=agent.id, target_id=end.id, type="Forward"))

        result = await svc.validate_workflow(workflow.id)

        assert result["valid"] is False
        assert any("开始" in err or "start" in err.lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_no_end_node(self, db: AsyncSession):
        """测试验证没有结束节点的工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="无结束节点",
            definition={"nodes": [], "edges": []},
        )

        start = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        agent = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))

        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=agent.id, type="Forward"))

        result = await svc.validate_workflow(workflow.id)

        assert result["valid"] is False
        assert any("结束" in err or "end" in err.lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_validate_orphan_nodes(self, db: AsyncSession):
        """测试验证孤立节点"""
        svc = WorkflowService(db)

        workflow = await svc.create_workflow(
            name="孤立节点",
            definition={"nodes": [], "edges": []},
        )

        start = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Start", label="开始"))
        agent = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="处理"))
        orphan = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="Agent", label="孤立节点"))
        end = await svc.add_node(WorkflowNodeCreate(workflow_id=workflow.id, type="End", label="结束"))

        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=start.id, target_id=agent.id, type="Forward"))
        await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow.id, source_id=agent.id, target_id=end.id, type="Forward"))
        # orphan 节点没有任何连接

        result = await svc.validate_workflow(workflow.id)

        assert result["valid"] is False
        assert any("孤立" in err or "未连接" in err or "orphan" in err.lower() for err in result["errors"])


class TestWorkflowServiceTemplates:
    """WorkflowService 模板管理测试"""

    @pytest.mark.asyncio
    async def test_list_templates(self, db: AsyncSession):
        """测试列出所有模板"""
        svc = WorkflowService(db)

        templates = await svc.list_templates()
        assert len(templates) > 0

    @pytest.mark.asyncio
    async def test_get_template(self, db: AsyncSession):
        """测试获取特定模板"""
        svc = WorkflowService(db)

        template = await svc.get_template("free_discussion")
        assert template is not None
        assert template["name"] == "自由讨论"
        assert "definition" in template

    @pytest.mark.asyncio
    async def test_create_from_template(self, db: AsyncSession):
        """测试从模板创建工作流"""
        svc = WorkflowService(db)

        workflow = await svc.create_from_template(
            name="基于自由讨论",
            template_type="free_discussion",
        )

        assert workflow.id is not None
        assert workflow.name == "基于自由讨论"
        assert workflow.template_type == "free_discussion"
        assert len(workflow.definition.get("nodes", [])) > 0
