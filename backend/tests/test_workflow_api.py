"""统一 Workflow 架构 - API 层测试

测试 Workflow API 端点（简化版，不依赖认证）
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge


class TestWorkflowListAPI:
    """工作流列表 API 测试"""

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self, api_client: AsyncClient):
        """测试空列表"""
        response = await api_client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestWorkflowCreateAPI:
    """工作流创建 API 测试"""

    @pytest.mark.asyncio
    async def test_create_workflow(self, api_client: AsyncClient):
        """测试创建工作流"""
        response = await api_client.post(
            "/api/v1/workflows",
            json={
                "name": "新建工作流",
                "description": "API 测试创建",
                "template_type": "custom",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "新建工作流"
        assert data["status"] == "draft"


class TestWorkflowDetailAPI:
    """工作流详情 API 测试"""

    @pytest.mark.asyncio
    async def test_get_workflow(self, api_client: AsyncClient, db: AsyncSession):
        """测试获取工作流详情"""
        workflow = Workflow(
            name="详情测试",
            description="用于测试详情 API",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        response = await api_client.get(f"/api/v1/workflows/{workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(workflow.id)
        assert data["name"] == "详情测试"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, api_client: AsyncClient):
        """测试获取不存在的工作流"""
        fake_id = uuid.uuid4()
        response = await api_client.get(f"/api/v1/workflows/{fake_id}")
        assert response.status_code == 404


class TestWorkflowUpdateAPI:
    """工作流更新 API 测试"""

    @pytest.mark.asyncio
    async def test_update_workflow(self, api_client: AsyncClient, db: AsyncSession):
        """测试更新工作流"""
        workflow = Workflow(
            name="原始名称",
            description="原始描述",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        response = await api_client.put(
            f"/api/v1/workflows/{workflow.id}",
            json={
                "name": "更新后名称",
                "description": "更新后描述",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新后名称"
        assert data["description"] == "更新后描述"


class TestWorkflowDeleteAPI:
    """工作流删除 API 测试"""

    @pytest.mark.asyncio
    async def test_delete_workflow(self, api_client: AsyncClient, db: AsyncSession):
        """测试删除工作流"""
        workflow = Workflow(
            name="待删除",
            description="将被删除",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        response = await api_client.delete(f"/api/v1/workflows/{workflow.id}")
        assert response.status_code == 204

        # 验证已删除
        result = await db.execute(select(Workflow).where(Workflow.id == workflow.id))
        assert result.scalar_one_or_none() is None


class TestWorkflowNodeAPI:
    """工作流节点 API 测试"""

    @pytest.mark.asyncio
    async def test_add_node(self, api_client: AsyncClient, db: AsyncSession):
        """测试添加节点"""
        workflow = Workflow(
            name="节点测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        response = await api_client.post(
            f"/api/v1/workflows/{workflow.id}/nodes",
            json={
                "workflow_id": str(workflow.id),  # Schema 要求
                "type": "Agent",
                "label": "处理节点",
                "config": {"agent_id": str(uuid.uuid4())},
                "position_x": 100,
                "position_y": 200,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "Agent"
        assert data["position_x"] == 100

    @pytest.mark.asyncio
    async def test_update_node(self, api_client: AsyncClient, db: AsyncSession):
        """测试更新节点"""
        workflow = Workflow(
            name="更新节点测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node = WorkflowNode(
            workflow_id=workflow.id,
            type="Agent",
            label="原始标签",
            config={},
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)

        response = await api_client.put(
            f"/api/v1/workflows/nodes/{node.id}",
            json={"label": "更新标签"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "更新标签"

    @pytest.mark.asyncio
    async def test_delete_node(self, api_client: AsyncClient, db: AsyncSession):
        """测试删除节点"""
        workflow = Workflow(
            name="删除节点测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node = WorkflowNode(
            workflow_id=workflow.id,
            type="Agent",
            label="待删除",
            config={},
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)

        response = await api_client.delete(f"/api/v1/workflows/nodes/{node.id}")
        assert response.status_code == 204


class TestWorkflowEdgeAPI:
    """工作流边 API 测试"""

    @pytest.mark.asyncio
    async def test_add_edge(self, api_client: AsyncClient, db: AsyncSession):
        """测试添加边"""
        workflow = Workflow(
            name="边测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node1 = WorkflowNode(workflow_id=workflow.id, type="Start", label="开始")
        node2 = WorkflowNode(workflow_id=workflow.id, type="End", label="结束")
        db.add_all([node1, node2])
        await db.commit()
        await db.refresh(node1)
        await db.refresh(node2)

        response = await api_client.post(
            f"/api/v1/workflows/{workflow.id}/edges",
            json={
                "workflow_id": str(workflow.id),  # Schema 要求
                "source_id": str(node1.id),
                "target_id": str(node2.id),
                "type": "Forward",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_id"] == str(node1.id)
        assert data["target_id"] == str(node2.id)

    @pytest.mark.asyncio
    async def test_delete_edge(self, api_client: AsyncClient, db: AsyncSession):
        """测试删除边"""
        workflow = Workflow(
            name="删除边测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        node1 = WorkflowNode(workflow_id=workflow.id, type="Start", label="开始")
        node2 = WorkflowNode(workflow_id=workflow.id, type="End", label="结束")
        db.add_all([node1, node2])
        await db.commit()
        await db.refresh(node1)
        await db.refresh(node2)

        edge = WorkflowEdge(
            workflow_id=workflow.id,
            source_id=node1.id,
            target_id=node2.id,
            type="Forward",
        )
        db.add(edge)
        await db.commit()
        await db.refresh(edge)

        response = await api_client.delete(f"/api/v1/workflows/edges/{edge.id}")
        assert response.status_code == 204


class TestWorkflowValidationAPI:
    """工作流验证 API 测试"""

    @pytest.mark.asyncio
    async def test_validate_workflow(self, api_client: AsyncClient, db: AsyncSession):
        """测试验证工作流"""
        workflow = Workflow(
            name="验证测试",
            definition={"nodes": [], "edges": []},
            version=1,
            is_template=False,
            status="draft",
        )
        db.add(workflow)
        await db.commit()

        # 添加有效节点
        start = WorkflowNode(workflow_id=workflow.id, type="Start", label="开始")
        end = WorkflowNode(workflow_id=workflow.id, type="End", label="结束")
        db.add_all([start, end])
        await db.commit()

        response = await api_client.post(f"/api/v1/workflows/{workflow.id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data


class TestWorkflowTemplateAPI:
    """工作流模板 API 测试"""

    @pytest.mark.asyncio
    async def test_list_templates(self, api_client: AsyncClient):
        """测试列出模板"""
        response = await api_client.get("/api/v1/workflows/templates/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_create_from_template(self, api_client: AsyncClient):
        """测试从模板创建"""
        response = await api_client.post(
            "/api/v1/workflows/templates/free_discussion/create?name=基于模板的工作流"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["template_type"] == "free_discussion"
