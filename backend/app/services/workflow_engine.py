"""Workflow Engine：工作流执行引擎

DDD 设计原则：
1. 只依赖 Workflow 领域的模型
2. 通过 ID 引用其他领域实体
3. 节点执行器通过策略模式扩展
4. 执行状态通过 WorkflowInstance 持久化
5. 使用依赖注入，方便测试
"""

import logging
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional, Any, Callable
from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.workflow_instance import WorkflowInstance, NodeExecution
from app.models.agent import Agent
from app.core.database import async_sessionmaker

logger = logging.getLogger(__name__)


# 节点执行器抽象接口
class NodeExecutor(ABC):
    """节点执行器接口"""

    @abstractmethod
    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: "ExecutionContext",
    ) -> dict:
        """
        执行节点

        Args:
            node: 要执行的节点
            instance: 工作流实例
            state: 当前状态
            context: 执行上下文

        Returns:
            节点执行结果，包含 output 和 next_edges 等信息
        """
        pass


# 执行上下文
class ExecutionContext:
    """执行上下文：传递给节点执行器的运行时信息"""

    def __init__(
        self,
        db: AsyncSession,
        user_input: Optional[str] = None,
        session_id: Optional[uuid.UUID] = None,
        workspace_path: Optional[str] = None,
    ):
        self.db = db
        self.user_input = user_input
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.metadata = {}  # 额外的元数据

    async def get_agent(self, agent_id: uuid.UUID) -> Optional[dict]:
        """获取 Agent 信息

        通过 ID 引用其他领域，避免直接导入模型。
        返回字典而非模型对象。
        """
        result = await self.db.execute("""
            SELECT id, name, default_model_id, persona_id
            FROM agents
            WHERE id = :agent_id
        """, {"agent_id": str(agent_id)})
        row = result.one_or_none()
        if row:
            return {
                "id": str(row[0]),
                "name": row[1],
                "default_model_id": str(row[2]),
                "persona_id": str(row[3]),
            }
        return None


# 工作流引擎
class WorkflowEngine:
    """工作流执行引擎

    职责：
    1. 加载工作流定义
    2. 管理执行状态
    3. 调度节点执行
    4. 处理边流转
    5. 持久化执行历史

    遵循 DDD 原则：
    - 只依赖 Workflow 领域模型
    - 通过 ID 引用其他领域实体
    - 使用策略模式扩展节点执行器
    """

    def __init__(
        self,
        db: AsyncSession,
        node_executors: Optional[dict[str, NodeExecutor]] = None,
        event_callback: Optional[Callable] = None,
    ):
        """
        Args:
            db: 数据库会话
            node_executors: 节点执行器映射，默认使用内置执行器
            event_callback: 事件回调函数，用于推送执行进度
        """
        self.db = db
        self.node_executors = node_executors or self._default_executors()
        self.event_callback = event_callback

    def _default_executors(self) -> dict[str, NodeExecutor]:
        """获取默认节点执行器"""
        # 延迟导入避免循环依赖
        from app.services.workflow_executors import (
            AgentNodeExecutor,
            StartNodeExecutor,
            EndNodeExecutor,
            RouterNodeExecutor,
            ParallelNodeExecutor,
            ConditionNodeExecutor,
            ValidationNodeExecutor,
            HITLNodeExecutor,
        )
        return {
            "Start": StartNodeExecutor(),
            "End": EndNodeExecutor(),
            "Agent": AgentNodeExecutor(),
            "Router": RouterNodeExecutor(),
            "Parallel": ParallelNodeExecutor(),
            "Condition": ConditionNodeExecutor(),
            "Validation": ValidationNodeExecutor(),
            "HITL": HITLNodeExecutor(),
        }

    async def create_instance(
        self,
        workflow_id: uuid.UUID,
        session_id: Optional[uuid.UUID] = None,
        initial_state: Optional[dict] = None,
    ) -> WorkflowInstance:
        """创建工作流执行实例"""
        instance = WorkflowInstance(
            workflow_id=workflow_id,
            session_id=session_id,
            status="pending",
            state=initial_state or {},
            retry_count=0,
        )
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)

        await self._emit_event("instance.created", {
            "instance_id": str(instance.id),
            "workflow_id": str(workflow_id),
            "session_id": str(session_id) if session_id else None,
        })

        return instance

    async def start_instance(
        self,
        instance_id: uuid.UUID,
        user_input: Optional[str] = None,
        workspace_path: Optional[str] = None,
    ) -> WorkflowInstance:
        """启动工作流实例"""
        instance = await self.db.get(WorkflowInstance, instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if instance.status != "pending":
            raise ValueError(f"Instance {instance_id} is not in pending status")

        instance.status = "running"
        instance.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._emit_event("instance.started", {
            "instance_id": str(instance_id),
            "workflow_id": str(instance.workflow_id),
        })

        # 在后台执行工作流
        asyncio.create_task(self._execute_workflow(
            instance=instance,
            user_input=user_input,
            workspace_path=workspace_path,
        ))

        return instance

    async def _execute_workflow(
        self,
        instance: WorkflowInstance,
        user_input: Optional[str] = None,
        workspace_path: Optional[str] = None,
    ):
        """执行工作流的内部方法"""
        try:
            # 加载工作流定义
            workflow = await self.db.get(Workflow, instance.workflow_id)
            if not workflow:
                raise ValueError(f"Workflow {instance.workflow_id} not found")

            # 获取节点和边
            nodes = await self._get_workflow_nodes(instance.workflow_id)
            edges = await self._get_workflow_edges(instance.workflow_id)

            # 构建节点映射和边索引
            node_map = {n.id: n for n in nodes}
            node_id_map = {n["id"]: n.id for n in workflow.definition.get("nodes", [])}

            # 找到开始节点
            start_node = self._find_start_node(nodes)
            if not start_node:
                raise ValueError("Workflow has no Start node")

            # 创建执行上下文
            context = ExecutionContext(
                db=self.db,
                user_input=user_input,
                session_id=instance.session_id,
                workspace_path=workspace_path,
            )

            current_node = start_node

            while current_node and instance.status == "running":
                # 执行节点
                result = await self._execute_node(
                    node=current_node,
                    instance=instance,
                    context=context,
                    edges=edges,
                )

                # 更新状态
                if result.get("output"):
                    instance.state.update(result["output"])

                # 确定下一个节点
                current_node = await self._determine_next_node(
                    current_node=current_node,
                    result=result,
                    instance=instance,
                    edges=edges,
                    node_map=node_map,
                )

            # 完成执行
            if instance.status == "running":
                instance.status = "completed"
                instance.completed_at = datetime.now(timezone.utc)
                await self.db.commit()

                await self._emit_event("instance.completed", {
                    "instance_id": str(instance.id),
                    "status": "completed",
                })

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            instance.status = "failed"
            instance.error_message = str(e)
            instance.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._emit_event("instance.failed", {
                "instance_id": str(instance.id),
                "error": str(e),
            })

    async def _execute_node(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        context: ExecutionContext,
        edges: list[WorkflowEdge],
    ) -> dict:
        """执行单个节点"""
        # 创建执行记录
        execution = NodeExecution(
            instance_id=instance.id,
            node_id=node.id,
            node_type=node.type,
            node_label=node.label,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        instance.current_node_id = node.id
        await self.db.commit()

        await self._emit_event("node.started", {
            "instance_id": str(instance.id),
            "node_id": str(node.id),
            "node_type": node.type,
            "node_label": node.label,
        })

        try:
            # 获取节点执行器
            executor = self.node_executors.get(node.type)
            if not executor:
                raise ValueError(f"No executor for node type: {node.type}")

            # 执行节点
            result = await executor.execute(
                node=node,
                instance=instance,
                state=instance.state,
                context=context,
            )

            # 更新执行记录
            execution.status = "completed"
            execution.output = result.get("output")
            execution.completed_at = datetime.now(timezone.utc)

            # 记录 Agent 信息（如果适用）
            if result.get("agent_id"):
                execution.agent_id = result["agent_id"]
                agent_info = await context.get_agent(result["agent_id"])
                if agent_info:
                    execution.agent_name = agent_info.get("name")

            await self.db.commit()

            await self._emit_event("node.completed", {
                "instance_id": str(instance.id),
                "node_id": str(node.id),
                "output": result.get("output"),
            })

            return result

        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            await self._emit_event("node.failed", {
                "instance_id": str(instance.id),
                "node_id": str(node.id),
                "error": str(e),
            })

            raise

    async def _determine_next_node(
        self,
        current_node: WorkflowNode,
        result: dict,
        instance: WorkflowInstance,
        edges: list[WorkflowEdge],
        node_map: dict,
    ) -> Optional[WorkflowNode]:
        """确定下一个执行的节点"""
        # 获取当前节点的出边
        outgoing_edges = [e for e in edges if e.source_id == current_node.id]

        if not outgoing_edges:
            return None

        # 根据执行结果选择边
        edge_type = result.get("next_edge_type", "Forward")

        # 选择匹配的边
        selected_edges = [e for e in outgoing_edges if e.type == edge_type]

        if not selected_edges:
            # 如果没有匹配的边，使用默认的 Forward 边
            selected_edges = [e for e in outgoing_edges if e.type == "Forward"]

        if not selected_edges:
            return None

        # 选择第一条边（简化处理，Router 节点可以返回具体的目标节点）
        next_edge = selected_edges[0]
        target_id = result.get("next_node_id") or next_edge.target_id

        return node_map.get(target_id)

    def _find_start_node(self, nodes: list[WorkflowNode]) -> Optional[WorkflowNode]:
        """找到开始节点"""
        for node in nodes:
            if node.type == "Start":
                return node
        return None

    async def _get_workflow_nodes(self, workflow_id: uuid.UUID) -> list[WorkflowNode]:
        """获取工作流的所有节点"""
        result = await self.db.execute(
            select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)
        )
        return list(result.scalars().all())

    async def _get_workflow_edges(self, workflow_id: uuid.UUID) -> list[WorkflowEdge]:
        """获取工作流的所有边"""
        result = await self.db.execute(
            select(WorkflowEdge).where(WorkflowEdge.workflow_id == workflow_id)
        )
        return list(result.scalars().all())

    async def _emit_event(self, event_type: str, data: dict):
        """发送事件"""
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error(f"Failed to emit event {event_type}: {e}")

    # ── 实例管理 ───────────────────────────────────────────

    async def pause_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """暂停工作流实例"""
        instance = await self.db.get(WorkflowInstance, instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if instance.status != "running":
            raise ValueError(f"Instance {instance_id} is not running")

        instance.status = "paused"
        await self.db.commit()

        await self._emit_event("instance.paused", {
            "instance_id": str(instance_id),
        })

        return instance

    async def resume_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """恢复工作流实例"""
        instance = await self.db.get(WorkflowInstance, instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        if instance.status != "paused":
            raise ValueError(f"Instance {instance_id} is not paused")

        instance.status = "running"
        await self.db.commit()

        await self._emit_event("instance.resumed", {
            "instance_id": str(instance_id),
        })

        # 继续执行
        asyncio.create_task(self._execute_workflow(
            instance=instance,
            user_input=None,
            workspace_path=None,
        ))

        return instance

    async def cancel_instance(self, instance_id: uuid.UUID) -> WorkflowInstance:
        """取消工作流实例"""
        instance = await self.db.get(WorkflowInstance, instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        instance.status = "cancelled"
        instance.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self._emit_event("instance.cancelled", {
            "instance_id": str(instance_id),
        })

        return instance
