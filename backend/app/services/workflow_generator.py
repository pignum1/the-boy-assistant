"""Workflow Generator：基于 LLM 的工作流生成器

DDD 设计原则：
1. 只依赖本领域的模型（Workflow, WorkflowNode, WorkflowEdge）
2. 通过 ID 引用其他领域实体，不直接导入其他领域模型
3. 跨领域数据通过参数传入，由调用方负责获取
4. 依赖抽象接口，不依赖具体实现
"""

import json
import logging
import uuid
from typing import Optional, Any
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.services.workflow_examples import (
    WORKFLOW_EXAMPLES,
    NODE_TYPE_REFERENCE,
    EDGE_TYPE_REFERENCE,
    get_relevant_examples,
)
from app.adapters.llm.litellm_adapter import LiteLLMAdapter

logger = logging.getLogger(__name__)


# 抽象接口：LLM 提供者
class LLMProvider(ABC):
    @abstractmethod
    async def acomplete(self, messages: list[dict], **kwargs) -> dict:
        pass


# 抽象接口：工作流存储
class WorkflowRepository(ABC):
    @abstractmethod
    async def create_workflow(self, data: dict) -> Workflow:
        pass

    @abstractmethod
    async def create_node(self, workflow_id: uuid.UUID, data: dict) -> WorkflowNode:
        pass

    @abstractmethod
    async def create_edge(self, workflow_id: uuid.UUID, data: dict) -> WorkflowEdge:
        pass


# 具体实现：数据库工作流仓储
class DatabaseWorkflowRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workflow(self, data: dict) -> Workflow:
        from app.services.workflow_service import WorkflowService
        svc = WorkflowService(self.db)
        return await svc.create_workflow(**data)

    async def create_node(self, workflow_id: uuid.UUID, data: dict) -> WorkflowNode:
        from app.services.workflow_service import WorkflowService
        from app.schemas.workflow import WorkflowNodeCreate
        svc = WorkflowService(self.db)
        return await svc.add_node(WorkflowNodeCreate(workflow_id=workflow_id, **data))

    async def create_edge(self, workflow_id: uuid.UUID, data: dict) -> WorkflowEdge:
        from app.services.workflow_service import WorkflowService
        from app.schemas.workflow import WorkflowEdgeCreate
        svc = WorkflowService(self.db)
        return await svc.add_edge(WorkflowEdgeCreate(workflow_id=workflow_id, **data))


class WorkflowGenerator:
    """基于 LLM 的工作流生成器

    只依赖 Workflow 领域，不直接引用其他领域模型。
    其他领域数据通过参数传入，保持领域独立。
    """

    def __init__(
        self,
        db: AsyncSession,
        llm_provider: Optional[LLMProvider] = None,
        repository: Optional[WorkflowRepository] = None,
    ):
        # 依赖注入，方便测试和解耦
        self.db = db
        self.llm_provider = llm_provider or LiteLLMAdapter()
        self.repository = repository or DatabaseWorkflowRepository(db)

    async def generate(
        self,
        requirement: str,
        # 其他领域数据通过参数传入，不直接查询
        available_agents: list[dict],  # [{"id": str, "name": str, "role": str}]
        team_context: Optional[dict] = None,  # 团队上下文信息
        name: Optional[str] = None,
    ) -> dict:
        """根据需求生成工作流定义

        Args:
            requirement: 用户需求描述
            available_agents: 可用的 Agent 列表（由调用方提供）
            team_context: 团队上下文（可选）
            name: 工作流名称（可选）

        Returns:
            工作流定义和分析结果
        """
        # 1. 分析需求
        analysis = await self._analyze_requirement(
            requirement=requirement,
            available_agents=available_agents,
        )

        # 2. 获取相关案例
        relevant_examples = get_relevant_examples(requirement)

        # 3. 生成工作流
        workflow_def = await self._generate_workflow(
            requirement=requirement,
            analysis=analysis,
            available_agents=available_agents,
            examples=relevant_examples,
        )

        # 4. 验证生成的工作流
        validation = self._validate_generated_workflow(workflow_def)

        return {
            "name": name or analysis.get("suggested_name", "Generated Workflow"),
            "description": analysis.get("summary", requirement),
            "template_type": "custom",
            "definition": workflow_def,
            "analysis": analysis,
            "validation": validation,
            "suggestions": analysis.get("suggestions", []),
        }

    async def _analyze_requirement(
        self, requirement: str, available_agents: list[dict]
    ) -> dict:
        """分析需求，提取关键信息

        只依赖传入的 Agent 信息，不查询数据库。
        """

        agents_info = "\n".join([
            f"- {a['name']} (角色: {a.get('role', 'N/A')})"
            for a in available_agents
        ])

        system_prompt = """你是一个工作流分析专家。分析用户需求，提取以下信息：

1. **task_type**: 任务类型
2. **complexity**: 复杂度（low/medium/high）
3. **participants**: 需要的参与者角色
4. **need_human**: 是否需要人工介入（true/false）
5. **suggested_name**: 建议的工作流名称
6. **summary**: 一句话总结需求
7. **suggested_template**: 最适合的模板类型
8. **suggestions**: 优化建议列表

返回 JSON 格式。"""

        user_prompt = f"""用户需求：{requirement}

可用成员：{agents_info}

请分析这个需求，返回 JSON 格式的分析结果。"""

        try:
            response = await self.llm_provider.acomplete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            content = response.get("content", "{}")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to analyze requirement: {e}")
            return {
                "task_type": "custom",
                "complexity": "medium",
                "need_human": False,
                "suggested_name": "Custom Workflow",
                "summary": requirement[:100],
                "suggested_template": "supervisor_dispatch",
                "suggestions": []
            }

    async def _generate_workflow(
        self,
        requirement: str,
        analysis: dict,
        available_agents: list[dict],
        examples: list[dict],
    ) -> dict:
        """生成工作流定义"""

        examples_text = ""
        if examples:
            examples_text = "\n\n参考案例：\n"
            for ex in examples[:2]:
                examples_text += f"\n案例：{ex['name']}\n场景：{ex['scenario']}\n"

        system_prompt = f"""你是一个工作流设计专家。根据用户需求生成工作流定义。

**可用节点类型**：
{json.dumps(NODE_TYPE_REFERENCE, ensure_ascii=False, indent=2)}

**可用边类型**：
{json.dumps(EDGE_TYPE_REFERENCE, ensure_ascii=False, indent=2)}

**设计原则**：
1. 必须包含一个 Start 节点和一个 End 节点
2. Agent 节点应该使用提供的 agent_id
3. 验证失败时应使用 Reject 边
{examples_text}

返回 JSON 格式，包含 nodes 和 edges 两个字段。"""

        agents_text = "\n".join([
            f"- {a['name']} (id: {a['id']}, role: {a.get('role', 'N/A')})"
            for a in available_agents
        ])

        user_prompt = f"""用户需求：{requirement}

任务类型：{analysis.get('task_type')}
复杂度：{analysis.get('complexity')}
需要人工介入：{analysis.get('need_human')}

可用成员：{agents_text}

请生成工作流定义，返回 JSON：{{"nodes": [...], "edges": [...]}}"""

        try:
            response = await self.llm_provider.acomplete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            content = response.get("content", "{}")
            workflow_def = json.loads(content)

            # 确保基本结构
            if "nodes" not in workflow_def:
                workflow_def["nodes"] = []
            if "edges" not in workflow_def:
                workflow_def["edges"] = []

            # 确保有 Start 和 End 节点
            node_ids = {n["id"] for n in workflow_def["nodes"]}
            has_start = any(n.get("type") == "Start" for n in workflow_def["nodes"])
            has_end = any(n.get("type") == "End" for n in workflow_def["nodes"])

            if not has_start:
                workflow_def["nodes"].insert(0, {
                    "id": "start",
                    "type": "Start",
                    "label": "开始",
                    "position": {"x": 100, "y": 100},
                    "config": {}
                })
            if not has_end:
                max_y = max((n.get("position", {}).get("y", 100) for n in workflow_def["nodes"]), default=500)
                workflow_def["nodes"].append({
                    "id": "end",
                    "type": "End",
                    "label": "结束",
                    "position": {"x": 100, "y": max_y + 100},
                    "config": {}
                })

            return workflow_def

        except Exception as e:
            logger.error(f"Failed to generate workflow: {e}")
            # 返回简单的默认工作流
            first_agent = available_agents[0] if available_agents else {"id": "dummy", "name": "Agent"}
            return {
                "nodes": [
                    {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}, "config": {}},
                    {"id": "agent_1", "type": "Agent", "label": first_agent.get("name", "Agent"),
                     "config": {"agent_id": first_agent.get("id", "dummy")}, "position": {"x": 100, "y": 200}},
                    {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 300}, "config": {}}
                ],
                "edges": [
                    {"source": "start", "target": "agent_1", "type": "Forward"},
                    {"source": "agent_1", "target": "end", "type": "Forward"}
                ]
            }

    def _validate_generated_workflow(self, workflow_def: dict) -> dict:
        """验证生成的工作流"""
        errors = []
        warnings = []

        nodes = workflow_def.get("nodes", [])
        edges = workflow_def.get("edges", [])

        if not nodes:
            errors.append("工作流没有节点")
        if not edges:
            warnings.append("工作流没有边")

        node_types = {n.get("type") for n in nodes}
        if "Start" not in node_types:
            errors.append("缺少 Start 节点")
        if "End" not in node_types:
            errors.append("缺少 End 节点")

        node_ids = {n.get("id") for n in nodes}
        source_ids = {e.get("source") for e in edges}
        target_ids = {e.get("target") for e in edges}

        for node in nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            if node_type != "Start" and node_id not in target_ids:
                warnings.append(f"节点 '{node.get('label')}' 没有入边")
            if node_type != "End" and node_id not in source_ids:
                warnings.append(f"节点 '{node.get('label')}' 没有出边")

        for edge in edges:
            if edge.get("source") not in node_ids:
                errors.append(f"边引用了不存在的源节点: {edge.get('source')}")
            if edge.get("target") not in node_ids:
                errors.append(f"边引用了不存在的目标节点: {edge.get('target')}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    async def save_workflow(
        self,
        workflow_def: dict,
        repository: WorkflowRepository,
        name: str,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Workflow:
        """保存生成的工作流

        通过注入的 Repository 保存，不直接依赖数据库。
        """
        # 创建工作流
        workflow = await repository.create_workflow({
            "name": name,
            "description": description,
            "template_type": "custom",
            "definition": workflow_def.get("definition", {}),
            "created_by": created_by,
        })

        # 创建节点
        node_map = {}
        for node_def in workflow_def.get("definition", {}).get("nodes", []):
            node = await repository.create_node(workflow.id, {
                "type": node_def.get("type", "Agent"),
                "label": node_def.get("label", ""),
                "config": node_def.get("config", {}),
                "position_x": node_def.get("position", {}).get("x"),
                "position_y": node_def.get("position", {}).get("y"),
            })
            node_map[node_def["id"]] = node.id

        # 创建边
        for edge_def in workflow_def.get("definition", {}).get("edges", []):
            source_id = node_map.get(edge_def["source"])
            target_id = node_map.get(edge_def["target"])
            if source_id and target_id:
                await repository.create_edge(workflow.id, {
                    "source_id": source_id,
                    "target_id": target_id,
                    "type": edge_def.get("type", "Forward"),
                    "condition": edge_def.get("condition"),
                })

        logger.info(f"Generated workflow saved: {workflow.id}")
        return workflow

    async def plan_from_requirement(
        self,
        requirement: str,
        available_agents: list[dict],
        team_context: Optional[dict] = None,
    ) -> dict:
        """从用户需求生成完整的任务规划

        这是 UserTask 专用的方法，返回更详细的规划信息。

        Args:
            requirement: 用户需求描述
            available_agents: 可用的 Agent 列表
            team_context: 团队上下文信息

        Returns:
            包含以下字段的字典：
            {
                "task_name": "...",
                "task_description": "...",
                "estimated_steps": 5,
                "estimated_duration_minutes": 30,
                "workflow": {...},  # 完整的工作流定义
                "suggestions": [...],
                "risks": [...]
            }
        """
        # 1. 分析需求
        analysis = await self._analyze_requirement(
            requirement=requirement,
            available_agents=available_agents,
        )

        # 2. 生成工作流
        workflow_def = await self._generate_workflow(
            requirement=requirement,
            analysis=analysis,
            available_agents=available_agents,
            examples=get_relevant_examples(requirement),
        )

        # 3. 验证工作流
        validation = self._validate_generated_workflow(workflow_def)

        # 4. 估算步骤和时长
        nodes = workflow_def.get("nodes", [])
        # 过滤掉 Start/End 节点
        work_nodes = [n for n in nodes if n.get("type") not in ["Start", "End"]]
        estimated_steps = len(work_nodes)

        # 简单估算：每个节点平均 5-10 分钟
        estimated_duration = estimated_steps * 7

        # 5. 生成建议和风险
        suggestions = analysis.get("suggestions", [])

        risks = []
        if analysis.get("complexity") == "high":
            risks.append("任务复杂度较高，建议分阶段执行")
        if analysis.get("need_human"):
            risks.append("需要人工介入，可能增加执行时间")
        if validation.get("warnings"):
            risks.extend([f"工作流警告: {w}" for w in validation.get("warnings", [])])

        return {
            "task_name": analysis.get("suggested_name", "AI 生成的任务"),
            "task_description": analysis.get("summary", requirement),
            "estimated_steps": estimated_steps,
            "estimated_duration_minutes": estimated_duration,
            "workflow": workflow_def,
            "suggestions": suggestions,
            "risks": risks,
        }
