"""TaskProgressService：任务进度追踪服务

职责：
1. 计算工作流执行进度百分比
2. 获取当前执行步骤详情
3. 获取执行时间线
4. 追踪最后活跃时间
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow, WorkflowNode
from app.models.workflow_instance import WorkflowInstance, NodeExecution

logger = logging.getLogger(__name__)


class TaskProgressService:
    """任务进度追踪服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Progress Calculation ──────────────────────────────────

    async def calculate_progress(
        self,
        instance_id: uuid.UUID,
    ) -> int:
        """计算工作流完成百分比

        策略：
        1. 统计已完成的节点数
        2. 除以总节点数（不包括 Start/End）
        3. 返回百分比
        """
        # 获取工作流实例
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            return 0

        # 获取工作流定义中的节点数
        workflow_result = await self.db.execute(
            select(Workflow).where(Workflow.id == instance.workflow_id)
        )
        workflow = workflow_result.scalar_one_or_none()
        if not workflow:
            return 0

        # 从 definition 中获取节点数
        definition = workflow.definition or {}
        nodes = definition.get("nodes", [])

        # 过滤掉 Start/End 节点，只计算实际工作节点
        work_nodes = [
            n for n in nodes
            if n.get("type") not in ["Start", "End"]
        ]
        total_nodes = len(work_nodes)

        if total_nodes == 0:
            return 100 if instance.status == "completed" else 0

        # 统计已完成的执行记录
        completed_result = await self.db.execute(
            select(func.count(NodeExecution.id))
            .where(
                NodeExecution.instance_id == instance_id,
                NodeExecution.status == "completed",
            )
        )
        completed_count = completed_result.scalar() or 0

        # 计算百分比
        percentage = int((completed_count / total_nodes) * 100)

        # 如果实例已完成，返回100
        if instance.status == "completed":
            percentage = 100
        # 如果实例失败，根据已完成节点返回百分比
        elif instance.status == "failed":
            percentage = min(percentage, 99)

        return max(0, min(100, percentage))

    async def get_current_step(
        self,
        instance_id: uuid.UUID,
    ) -> Optional[dict]:
        """获取当前执行步骤

        返回当前正在执行的节点信息
        """
        # 获取实例
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            return None

        # 如果实例已完成或失败，返回最终状态
        if instance.status in ["completed", "failed", "cancelled"]:
            return {
                "status": instance.status,
                "node_id": str(instance.current_node_id) if instance.current_node_id else None,
                "message": f"工作流已{instance.status}",
            }

        # 获取当前节点的执行记录
        execution_result = await self.db.execute(
            select(NodeExecution)
            .where(
                NodeExecution.instance_id == instance_id,
                NodeExecution.status == "running",
            )
            .order_by(NodeExecution.started_at.desc())
            .limit(1)
        )
        execution = execution_result.scalar_one_or_none()

        if execution:
            return {
                "status": "running",
                "node_id": str(execution.node_id),
                "node_type": execution.node_type,
                "node_label": execution.node_label,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "output_summary": str(execution.output)[:200] if execution.output else None,
            }

        # 如果没有正在运行的节点，检查下一个待执行的节点
        pending_result = await self.db.execute(
            select(NodeExecution)
            .where(
                NodeExecution.instance_id == instance_id,
                NodeExecution.status == "pending",
            )
            .order_by(NodeExecution.created_at.asc())
            .limit(1)
        )
        pending = pending_result.scalar_one_or_none()

        if pending:
            return {
                "status": "pending",
                "node_id": str(pending.node_id),
                "node_type": pending.node_type,
                "node_label": pending.node_label,
                "message": "等待执行",
            }

        # 默认返回实例状态
        return {
            "status": instance.status,
            "message": f"工作流状态: {instance.status}",
        }

    async def get_execution_timeline(
        self,
        instance_id: uuid.UUID,
    ) -> list[dict]:
        """获取执行时间线

        返回所有节点的执行记录，按时间排序
        """
        result = await self.db.execute(
            select(NodeExecution)
            .where(NodeExecution.instance_id == instance_id)
            .order_by(NodeExecution.started_at.asc(), NodeExecution.created_at.asc())
        )
        executions = result.scalars().all()

        timeline = []
        for exec in executions:
            timeline.append({
                "node_id": str(exec.node_id),
                "node_type": exec.node_type,
                "node_label": exec.node_label,
                "status": exec.status,
                "started_at": exec.started_at.isoformat() if exec.started_at else None,
                "completed_at": exec.completed_at.isoformat() if exec.completed_at else None,
                "duration_seconds": (
                    (exec.completed_at - exec.started_at).total_seconds()
                    if exec.started_at and exec.completed_at
                    else None
                ),
                "agent_id": str(exec.agent_id) if exec.agent_id else None,
                "agent_name": exec.agent_name,
                "error_message": exec.error_message,
                "output_summary": str(exec.output)[:200] if exec.output else None,
            })

        return timeline

    async def update_last_activity(
        self,
        instance_id: uuid.UUID,
    ) -> None:
        """更新最后活跃时间"""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if instance:
            instance.last_activity_at = now
            await self.db.commit()

    async def check_stalled_tasks(
        self,
        timeout_minutes: int = 30,
    ) -> list[WorkflowInstance]:
        """检查停滞的任务

        返回超过指定时间没有活跃的任务实例
        """
        from datetime import timedelta

        timeout = timedelta(minutes=timeout_minutes)
        cutoff_time = datetime.now(timezone.utc) - timeout

        result = await self.db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.status == "running",
                WorkflowInstance.last_activity_at < cutoff_time,
            )
        )
        return list(result.scalars().all())

    # ── Detailed Progress Info ──────────────────────────────────

    async def get_detailed_progress(
        self,
        instance_id: uuid.UUID,
    ) -> dict:
        """获取详细的进度信息"""
        # 基础进度
        progress = await self.calculate_progress(instance_id)
        current_step = await self.get_current_step(instance_id)
        timeline = await self.get_execution_timeline(instance_id)

        # 获取实例信息
        result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            return {}

        # 获取工作流定义
        workflow_result = await self.db.execute(
            select(Workflow).where(Workflow.id == instance.workflow_id)
        )
        workflow = workflow_result.scalar_one_or_none()

        # 构建节点列表（按执行顺序）
        nodes_status = []
        if workflow and workflow.definition:
            definition_nodes = workflow.definition.get("nodes", [])
            node_map = {n["id"]: n for n in definition_nodes}

            # 按边确定节点顺序
            edges = workflow.definition.get("edges", [])
            ordered_node_ids = []

            # 简单拓扑排序：从 Start 节点开始
            start_nodes = [n for n in definition_nodes if n.get("type") == "Start"]
            if start_nodes:
                ordered_node_ids.append(start_nodes[0]["id"])

                # 跟随 Forward 边
                current_id = start_nodes[0]["id"]
                visited = {current_id}

                while current_id:
                    found = False
                    for edge in edges:
                        if edge.get("source") == current_id and edge.get("type") == "Forward":
                            target = edge.get("target")
                            if target and target not in visited:
                                ordered_node_ids.append(target)
                                visited.add(target)
                                current_id = target
                                found = True
                                break

                    if not found:
                        break

            # 为每个节点添加状态
            for node_id in ordered_node_ids:
                node_def = node_map.get(node_id)
                if not node_def:
                    continue

                # 查找执行记录
                exec_result = await self.db.execute(
                    select(NodeExecution).where(
                        NodeExecution.instance_id == instance_id,
                        NodeExecution.node_id == node_id,
                    )
                )
                execution = exec_result.scalar_one_or_none()

                nodes_status.append({
                    "node_id": node_id,
                    "node_type": node_def.get("type"),
                    "node_label": node_def.get("label"),
                    "status": execution.status if execution else "pending",
                    "started_at": execution.started_at.isoformat() if execution and execution.started_at else None,
                    "completed_at": execution.completed_at.isoformat() if execution and execution.completed_at else None,
                })

        # 计算预计完成时间（简单估算）
        estimated_completion = None
        if instance.started_at and progress < 100:
            # 基于已用时间和进度百分比估算
            from datetime import timedelta
            elapsed = (datetime.now(timezone.utc) - instance.started_at).total_seconds()
            if progress > 0:
                estimated_total = elapsed * 100 / progress
                remaining_seconds = estimated_total - elapsed
                if remaining_seconds > 0:
                    estimated_completion = datetime.now(timezone.utc) + \
                        timedelta(seconds=remaining_seconds)

        return {
            "instance_id": str(instance.id),
            "workflow_id": str(instance.workflow_id),
            "status": instance.status,
            "progress_percentage": progress,
            "current_step": current_step,
            "nodes_status": nodes_status,
            "timeline": timeline,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "estimated_completion_at": estimated_completion.isoformat() if estimated_completion else None,
            "last_activity_at": instance.last_activity_at.isoformat() if instance.last_activity_at else None,
            "issues_count": instance.issues_count if hasattr(instance, 'issues_count') else 0,
        }
