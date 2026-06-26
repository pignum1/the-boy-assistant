"""Workflow Service：工作流管理服务

职责：
1. 工作流 CRUD（创建、查询、更新、删除）
2. 节点管理（添加、更新、删除节点）
3. 边管理（添加、删除边）
4. 工作流验证（完整性检查）
5. 预设模板管理
"""

import logging
import uuid
from typing import Optional, Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.workflow_template import WorkflowTemplate
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowNodeCreate,
    WorkflowNodeUpdate,
    WorkflowEdgeCreate,
)

logger = logging.getLogger(__name__)


# 预设模板定义
PRESET_TEMPLATES: dict[str, dict] = {
    "free_discussion": {
        "name": "自由讨论",
        "description": "所有团队成员并行参与，无约束的自由讨论",
        "definition": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "all_agents", "type": "Agent", "label": "所有成员", "config": {"agent_mode": "all"}, "position": {"x": 100, "y": 200}},
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 300}},
            ],
            "edges": [
                {"source": "start", "target": "all_agents", "type": "Forward"},
                {"source": "all_agents", "target": "end", "type": "Forward"},
            ],
        },
    },
    "supervisor_dispatch": {
        "name": "主管调度",
        "description": "由主管 Agent 接收任务，分配给工作组成员，最后汇总审核",
        "definition": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "supervisor", "type": "Agent", "label": "主管调度", "config": {"role_slot": "supervisor"}, "position": {"x": 100, "y": 200}},
                {"id": "router", "type": "Router", "label": "成员路由", "config": {"strategy": "priority"}, "position": {"x": 100, "y": 300}},
                {"id": "validation", "type": "Validation", "label": "结果验证", "config": {"validator": "LLM"}, "position": {"x": 100, "y": 400}},
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 500}},
            ],
            "edges": [
                {"source": "start", "target": "supervisor", "type": "Forward"},
                {"source": "supervisor", "target": "router", "type": "Forward"},
                {"source": "router", "target": "validation", "type": "Forward"},
                {"source": "validation", "target": "end", "type": "Forward"},
                {"source": "validation", "target": "supervisor", "type": "Reject"},
            ],
        },
    },
    "sequential": {
        "name": "顺序执行",
        "description": "按步骤顺序依次执行各个 Agent",
        "definition": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "step1", "type": "Agent", "label": "步骤1", "config": {"step_order": 1}, "position": {"x": 100, "y": 200}},
                {"id": "step2", "type": "Agent", "label": "步骤2", "config": {"step_order": 2}, "position": {"x": 100, "y": 300}},
                {"id": "step3", "type": "Agent", "label": "步骤3", "config": {"step_order": 3}, "position": {"x": 100, "y": 400}},
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 500}},
            ],
            "edges": [
                {"source": "start", "target": "step1", "type": "Forward"},
                {"source": "step1", "target": "step2", "type": "Forward"},
                {"source": "step2", "target": "step3", "type": "Forward"},
                {"source": "step3", "target": "end", "type": "Forward"},
            ],
        },
    },
    "product_dev": {
        "name": "产品开发",
        "description": "多角色并行协作，适合跨职能产品开发",
        "definition": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "parallel", "type": "Parallel", "label": "并行分析", "config": {"branches": 3}, "position": {"x": 100, "y": 200}},
                {"id": "merge", "type": "Agent", "label": "合并结果", "position": {"x": 100, "y": 300}},
                {"id": "validation", "type": "Validation", "label": "审核", "config": {"validator": "LLM"}, "position": {"x": 100, "y": 400}},
                {"id": "hitl", "type": "HITL", "label": "人工决策", "config": {"action_type": "approve"}, "position": {"x": 100, "y": 500}},
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 600}},
            ],
            "edges": [
                {"source": "start", "target": "parallel", "type": "Forward"},
                {"source": "parallel", "target": "merge", "type": "Forward"},
                {"source": "merge", "target": "validation", "type": "Forward"},
                {"source": "validation", "target": "end", "type": "Forward"},
                {"source": "validation", "target": "hitl", "type": "Reject"},
                {"source": "hitl", "target": "end", "type": "Forward"},
            ],
        },
    },
    "hotfix": {
        "name": "紧急修复",
        "description": "快速路由和执行，适合紧急事件处理",
        "definition": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {"id": "triage", "type": "Router", "label": "分类路由", "config": {"strategy": "priority"}, "position": {"x": 100, "y": 200}},
                {"id": "fix", "type": "Agent", "label": "开发修复", "config": {"role_slot": "developer"}, "position": {"x": 100, "y": 300}},
                {"id": "validate", "type": "Validation", "label": "验证", "config": {"validator": "LLM"}, "position": {"x": 100, "y": 400}},
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 500}},
            ],
            "edges": [
                {"source": "start", "target": "triage", "type": "Forward"},
                {"source": "triage", "target": "fix", "type": "Forward"},
                {"source": "fix", "target": "validate", "type": "Forward"},
                {"source": "validate", "target": "end", "type": "Forward"},
                {"source": "validate", "target": "fix", "type": "Reject"},
            ],
        },
    },
}


class WorkflowService:
    """工作流管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Workflow CRUD ────────────────────────────────────────

    async def create_workflow(
        self,
        name: str,
        description: Optional[str] = None,
        template_type: Optional[str] = None,
        definition: Optional[dict] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> Workflow:
        """创建工作流"""
        workflow = Workflow(
            name=name,
            description=description,
            template_type=template_type,
            definition=definition or {},
            created_by=created_by,
            status="draft",
        )
        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)
        logger.info(f"Workflow created: {name} (template={template_type})")
        return workflow

    async def get_workflow(self, workflow_id: uuid.UUID) -> Optional[Workflow]:
        """获取工作流"""
        return await self.db.get(Workflow, workflow_id)

    async def list_workflows(
        self,
        template_type: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Workflow], int]:
        """列出工作流（分页）"""
        from sqlalchemy import func as _func
        base = select(Workflow)
        if template_type:
            base = base.where(Workflow.template_type == template_type)
        if status:
            base = base.where(Workflow.status == status)
        # 总数
        count_result = await self.db.execute(select(_func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        # 分页数据
        query = base.order_by(Workflow.updated_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update_workflow(
        self, workflow_id: uuid.UUID, **kwargs
    ) -> Optional[Workflow]:
        """更新工作流"""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(workflow, k):
                setattr(workflow, k, v)
        await self.db.commit()
        await self.db.refresh(workflow)
        return workflow

    async def delete_workflow(self, workflow_id: uuid.UUID) -> bool:
        """删除工作流"""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return False
        await self.db.delete(workflow)
        await self.db.commit()
        logger.info(f"Workflow deleted: {workflow.name}")
        return True

    # ── Node Management ───────────────────────────────────────

    async def add_node(self, req: WorkflowNodeCreate) -> WorkflowNode:
        """添加节点"""
        node = WorkflowNode(
            workflow_id=req.workflow_id,
            type=req.type,
            label=req.label,
            config=req.config,
            position_x=req.position_x,
            position_y=req.position_y,
        )
        self.db.add(node)
        await self.db.commit()
        await self.db.refresh(node)
        logger.info(f"Node added: {req.type}/{req.label} to workflow {req.workflow_id}")
        return node

    async def update_node(
        self, node_id: uuid.UUID, req: WorkflowNodeUpdate
    ) -> Optional[WorkflowNode]:
        """更新节点"""
        node = await self.db.get(WorkflowNode, node_id)
        if not node:
            return None
        for k, v in req.model_dump(exclude_unset=True).items():
            if v is not None:
                setattr(node, k, v)
        await self.db.commit()
        await self.db.refresh(node)
        return node

    async def delete_node(self, node_id: uuid.UUID) -> bool:
        """删除节点"""
        node = await self.db.get(WorkflowNode, node_id)
        if not node:
            return False
        # 级联删除相关的边
        await self.db.execute(
            delete(WorkflowEdge).where(
                (WorkflowEdge.source_id == node_id) | (WorkflowEdge.target_id == node_id)
            )
        )
        await self.db.delete(node)
        await self.db.commit()
        return True

    async def get_nodes(self, workflow_id: uuid.UUID) -> list[WorkflowNode]:
        """获取工作流的所有节点"""
        result = await self.db.execute(
            select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)
        )
        return list(result.scalars().all())

    # ── Edge Management ───────────────────────────────────────

    async def add_edge(self, req: WorkflowEdgeCreate) -> WorkflowEdge:
        """添加边"""
        edge = WorkflowEdge(
            workflow_id=req.workflow_id,
            source_id=req.source_id,
            target_id=req.target_id,
            type=req.type,
            condition=req.condition,
        )
        self.db.add(edge)
        await self.db.commit()
        await self.db.refresh(edge)
        logger.info(
            f"Edge added: {req.source_id} -> {req.target_id} ({req.type}) in workflow {req.workflow_id}"
        )
        return edge

    async def update_edge(
        self, edge_id: uuid.UUID, **kwargs
    ) -> Optional[WorkflowEdge]:
        """更新边（类型、条件等）"""
        edge = await self.db.get(WorkflowEdge, edge_id)
        if not edge:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(edge, k):
                setattr(edge, k, v)
        await self.db.commit()
        await self.db.refresh(edge)
        return edge

    async def delete_edge(self, edge_id: uuid.UUID) -> bool:
        """删除边"""
        edge = await self.db.get(WorkflowEdge, edge_id)
        if not edge:
            return False
        await self.db.delete(edge)
        await self.db.commit()
        return True

    async def get_edges(self, workflow_id: uuid.UUID) -> list[WorkflowEdge]:
        """获取工作流的所有边"""
        result = await self.db.execute(
            select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow_id)
        )
        return list(result.scalars().all())

    # ── Validation ───────────────────────────────────────────

    async def validate_workflow(self, workflow_id: uuid.UUID) -> dict[str, Any]:
        """验证工作流完整性

        检查项：
        1. 至少有一个 Start 节点和一个 End 节点
        2. 所有节点都可达（没有孤立节点）
        3. 所有节点都有入边（除了 Start）和出边（除了 End）
        """
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return {"valid": False, "errors": ["Workflow not found"]}

        nodes = await self.get_nodes(workflow_id)
        edges = await self.get_edges(workflow_id)

        errors = []
        warnings = []

        node_ids = {n.id for n in nodes}
        node_types = {n.id: n.type for n in nodes}

        # 检查 Start 和 End 节点
        start_nodes = [n for n in nodes if n.type == "Start"]
        end_nodes = [n for n in nodes if n.type == "End"]

        if not start_nodes:
            errors.append("Workflow must have at least one Start node")
        if not end_nodes:
            errors.append("Workflow must have at least one End node")

        # 检查孤立节点
        nodes_with_incoming = {e.target_id for e in edges}
        nodes_with_outgoing = {e.source_id for e in edges}

        for node in nodes:
            if node.type != "Start" and node.id not in nodes_with_incoming:
                # 非开始节点必须有入边
                errors.append(f"Node '{node.label}' ({node.type}) has no incoming edges")
            if node.type != "End" and node.id not in nodes_with_outgoing:
                # 非结束节点必须有出边
                errors.append(f"Node '{node.label}' ({node.type}) has no outgoing edges")

        # 检查边的引用
        for edge in edges:
            if edge.source_id not in node_ids:
                errors.append(f"Edge references non-existent source node: {edge.source_id}")
            if edge.target_id not in node_ids:
                errors.append(f"Edge references non-existent target node: {edge.target_id}")

        is_valid = len(errors) == 0

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    # ── Templates ───────────────────────────────────────────

    async def get_template(self, template_type: str) -> Optional[dict]:
        """获取预设模板"""
        if template_type not in PRESET_TEMPLATES:
            return None
        return PRESET_TEMPLATES[template_type]

    async def list_templates(self) -> list[dict]:
        """列出所有预设模板"""
        return [
            {
                "template_type": t,
                "name": v["name"],
                "description": v["description"],
                "definition": v["definition"],
            }
            for t, v in PRESET_TEMPLATES.items()
        ]

    async def create_from_template(
        self,
        template_type: str,
        name: str,
        description: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> Optional[Workflow]:
        """从模板创建工作流"""
        template = await self.get_template(template_type)
        if not template:
            raise ValueError(f"Template '{template_type}' not found")

        workflow = await self.create_workflow(
            name=name,
            description=description or template["description"],
            template_type=template_type,
            definition=template["definition"],
            created_by=created_by,
        )

        # 创建节点
        node_map = {}
        for node_def in template["definition"]["nodes"]:
            node = await self.add_node(
                WorkflowNodeCreate(
                    workflow_id=workflow.id,
                    type=node_def["type"],
                    label=node_def["label"],
                    config=node_def.get("config", {}),
                    position_x=node_def.get("position", {}).get("x"),
                    position_y=node_def.get("position", {}).get("y"),
                )
            )
            node_map[node_def["id"]] = node.id

        # 创建边
        for edge_def in template["definition"]["edges"]:
            await self.add_edge(
                WorkflowEdgeCreate(
                    workflow_id=workflow.id,
                    source_id=node_map[edge_def["source"]],
                    target_id=node_map[edge_def["target"]],
                    type=edge_def["type"],
                    condition=edge_def.get("condition"),
                )
            )

        logger.info(f"Workflow created from template: {template_type} -> {workflow.id}")
        return workflow
