"""UserTaskService：用户任务管理服务

职责：
1. 用户任务 CRUD（创建、查询、更新、删除）
2. AI 规划调用（调用 WorkflowGenerator 生成工作流）
3. 任务生命周期管理（启动、暂停、恢复、取消）
4. 问题记录管理
5. 进度追踪

DDD 设计原则：
1. 通过 ID 引用其他领域（Team、Session、Agent）
2. 跨领域操作的数据由调用方提供
3. 不直接查询其他领域的模型
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_task import UserTask, TaskIssue
from app.models.workflow import Workflow
from app.models.workflow_instance import WorkflowInstance
from app.schemas.user_task import (
    UserTaskCreate,
    UserTaskUpdate,
    TaskIssueCreate,
    TaskIssueUpdate,
    TaskPlanRequest,
)

logger = logging.getLogger(__name__)


class UserTaskService:
    """用户任务管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── UserTask CRUD ────────────────────────────────────────

    async def create_task(
        self,
        title: str,
        requirement: str,
        team_id: Optional[uuid.UUID] = None,
        session_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        priority: str = "medium",
    ) -> UserTask:
        """创建任务，进入规划状态"""
        task = UserTask(
            team_id=team_id,
            session_id=session_id,
            title=title,
            description=description,
            requirement=requirement,
            priority=priority,
            status="planning",
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Created UserTask {task.id}: {title}")
        return task

    async def get_task(self, task_id: uuid.UUID) -> Optional[UserTask]:
        """获取任务详情"""
        result = await self.db.execute(
            select(UserTask).where(UserTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        team_id: Optional[uuid.UUID] = None,
        session_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[UserTask]:
        """列出任务"""
        query = select(UserTask).order_by(UserTask.created_at.desc())

        if team_id:
            query = query.where(UserTask.team_id == team_id)
        if session_id:
            query = query.where(UserTask.session_id == session_id)
        if status:
            query = query.where(UserTask.status == status)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_task(
        self,
        task_id: uuid.UUID,
        **updates
    ) -> Optional[UserTask]:
        """更新任务"""
        task = await self.get_task(task_id)
        if not task:
            return None

        for key, value in updates.items():
            if hasattr(task, key) and value is not None:
                setattr(task, key, value)

        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        """删除任务"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # 级联删除关联的问题
        await self.db.execute(
            delete(TaskIssue).where(TaskIssue.user_task_id == task_id)
        )

        await self.db.delete(task)
        await self.db.commit()
        logger.info(f"Deleted UserTask {task_id}")
        return True

    # ── Task Lifecycle ────────────────────────────────────────

    async def plan_workflow(
        self,
        task_id: uuid.UUID,
        workflow_definition: dict,
        plan_summary: dict,
    ) -> Optional[Workflow]:
        """为任务规划并生成工作流

        Args:
            task_id: 任务ID
            workflow_definition: 工作流定义（节点和边）
            plan_summary: AI 规划摘要

        Returns:
            创建的 Workflow 对象
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        # 创建 Workflow
        workflow = Workflow(
            name=f"任务: {task.title}",
            description=task.description,
            template_type="custom",
            definition=workflow_definition,
            status="draft",
        )
        self.db.add(workflow)
        await self.db.flush()  # 获取 workflow.id

        # 更新任务状态
        task.workflow_id = workflow.id
        task.status = "generated"
        task.ai_plan_summary = plan_summary
        task.planned_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)
        logger.info(f"Generated Workflow {workflow.id} for UserTask {task_id}")
        return workflow

    async def start_task(
        self,
        task_id: uuid.UUID,
        instance_id: uuid.UUID,
    ) -> Optional[UserTask]:
        """启动任务执行

        Args:
            task_id: 任务ID
            instance_id: 工作流实例ID

        Returns:
            更新后的任务对象
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        task.workflow_instance_id = instance_id
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Started UserTask {task_id} with instance {instance_id}")
        return task

    async def pause_task(self, task_id: uuid.UUID) -> Optional[UserTask]:
        """暂停任务"""
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status not in ["running", "generated"]:
            raise ValueError(f"Cannot pause task in status: {task.status}")

        task.status = "paused"
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Paused UserTask {task_id}")
        return task

    async def resume_task(self, task_id: uuid.UUID) -> Optional[UserTask]:
        """恢复任务"""
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status != "paused":
            raise ValueError(f"Cannot resume task in status: {task.status}")

        task.status = "running"
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Resumed UserTask {task_id}")
        return task

    async def cancel_task(self, task_id: uuid.UUID) -> Optional[UserTask]:
        """取消任务"""
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status in ["completed", "failed", "cancelled"]:
            raise ValueError(f"Cannot cancel task in status: {task.status}")

        task.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Cancelled UserTask {task_id}")
        return task

    async def complete_task(
        self,
        task_id: uuid.UUID,
        final_percentage: int = 100,
    ) -> Optional[UserTask]:
        """标记任务完成"""
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.progress_percentage = final_percentage
        task.current_step = "已完成"

        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"Completed UserTask {task_id}")
        return task

    async def fail_task(
        self,
        task_id: uuid.UUID,
        error_message: str,
    ) -> Optional[UserTask]:
        """标记任务失败"""
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = "failed"
        task.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)
        logger.error(f"UserTask {task_id} failed: {error_message}")
        return task

    # ── Progress Tracking ───────────────────────────────────

    async def update_progress(
        self,
        task_id: uuid.UUID,
        current_step: str,
        progress_percentage: int,
    ) -> Optional[UserTask]:
        """更新任务进度"""
        task = await self.get_task(task_id)
        if not task:
            return None

        task.current_step = current_step
        task.progress_percentage = max(0, min(100, progress_percentage))
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_progress_summary(self, task_id: uuid.UUID) -> dict:
        """获取任务进度摘要"""
        task = await self.get_task(task_id)
        if not task:
            return {}

        # 查询关联的工作流实例状态
        instance_info = None
        if task.workflow_instance_id:
            result = await self.db.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.id == task.workflow_instance_id
                )
            )
            instance = result.scalar_one_or_none()
            if instance:
                instance_info = {
                    "id": str(instance.id),
                    "status": instance.status,
                    "current_node_id": str(instance.current_node_id) if instance.current_node_id else None,
                    "started_at": instance.started_at.isoformat() if instance.started_at else None,
                }

        return {
            "task_id": str(task.id),
            "title": task.title,
            "status": task.status,
            "current_step": task.current_step,
            "progress_percentage": task.progress_percentage,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "planned_at": task.planned_at.isoformat() if task.planned_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "workflow_instance": instance_info,
        }

    # ── Issue Management ──────────────────────────────────────

    async def record_issue(
        self,
        user_task_id: uuid.UUID,
        title: str,
        severity: str = "medium",
        description: Optional[str] = None,
        workflow_instance_id: Optional[uuid.UUID] = None,
        node_execution_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        created_by: str = "user",
    ) -> TaskIssue:
        """记录问题"""
        issue = TaskIssue(
            user_task_id=user_task_id,
            workflow_instance_id=workflow_instance_id,
            node_execution_id=node_execution_id,
            title=title,
            description=description,
            severity=severity,
            category=category,
            created_by=created_by,
            status="open",
        )
        self.db.add(issue)
        await self.db.commit()
        await self.db.refresh(issue)
        logger.info(f"Recorded TaskIssue {issue.id} for UserTask {user_task_id}")
        return issue

    async def list_issues(
        self,
        user_task_id: uuid.UUID,
        status: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[TaskIssue]:
        """列出任务的问题"""
        query = select(TaskIssue).where(
            TaskIssue.user_task_id == user_task_id
        ).order_by(TaskIssue.created_at.desc())

        if status:
            query = query.where(TaskIssue.status == status)
        if severity:
            query = query.where(TaskIssue.severity == severity)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_issue(self, issue_id: uuid.UUID) -> Optional[TaskIssue]:
        """获取问题详情"""
        result = await self.db.execute(
            select(TaskIssue).where(TaskIssue.id == issue_id)
        )
        return result.scalar_one_or_none()

    async def update_issue(
        self,
        issue_id: uuid.UUID,
        **updates
    ) -> Optional[TaskIssue]:
        """更新问题"""
        issue = await self.get_issue(issue_id)
        if not issue:
            return None

        for key, value in updates.items():
            if hasattr(issue, key) and value is not None:
                setattr(issue, key, value)

        # 如果状态变为 resolved，记录解决时间
        if updates.get("status") == "resolved" and not issue.resolved_at:
            issue.resolved_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(issue)
        logger.info(f"Updated TaskIssue {issue_id}")
        return issue

    async def resolve_issue(
        self,
        issue_id: uuid.UUID,
        resolution: str,
    ) -> Optional[TaskIssue]:
        """解决问题"""
        return await self.update_issue(
            issue_id,
            status="resolved",
            resolution=resolution,
            resolved_at=datetime.now(timezone.utc),
        )

    # ── Task Iteration ────────────────────────────────────────

    async def iterate_task(
        self,
        task_id: uuid.UUID,
        feedback: str,
    ) -> UserTask:
        """创建任务的迭代版本

        Args:
            task_id: 原任务ID
            feedback: 用户反馈

        Returns:
            新的迭代任务
        """
        original_task = await self.get_task(task_id)
        if not original_task:
            raise ValueError(f"Original task {task_id} not found")

        # 创建新任务作为迭代版本
        new_requirement = f"""原始需求：{original_task.requirement}

用户反馈（迭代原因）：
{feedback}

请基于上述反馈优化执行方案。"""

        new_task = UserTask(
            team_id=original_task.team_id,
            session_id=original_task.session_id,
            title=f"{original_task.title} (迭代)",
            description=f"基于用户反馈的迭代版本\n\n原始任务: {task_id}",
            requirement=new_requirement,
            priority=original_task.priority,
            status="planning",
            iteration_count=original_task.iteration_count + 1,
            previous_task_id=task_id,
        )

        self.db.add(new_task)
        await self.db.commit()
        await self.db.refresh(new_task)

        logger.info(f"Created iteration task {new_task.id} from {task_id}")
        return new_task

    # ── Statistics ───────────────────────────────────────────

    async def get_task_statistics(
        self,
        team_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """获取任务统计信息"""
        base_query = select(func.count(UserTask.id))
        if team_id:
            base_query = base_query.where(UserTask.team_id == team_id)

        # 按状态统计
        result = await self.db.execute(
            select(UserTask.status, func.count(UserTask.id))
            .group_by(UserTask.status)
            .where(UserTask.team_id == team_id if team_id else True)
        )
        status_counts = {row[0]: row[1] for row in result.all()}

        # 按优先级统计
        result = await self.db.execute(
            select(UserTask.priority, func.count(UserTask.id))
            .group_by(UserTask.priority)
            .where(UserTask.team_id == team_id if team_id else True)
        )
        priority_counts = {row[0]: row[1] for row in result.all()}

        # 问题统计
        if team_id:
            # 关联查询获取该团队的开放问题数
            open_issues_result = await self.db.execute(
                select(func.count(TaskIssue.id))
                .join(UserTask, TaskIssue.user_task_id == UserTask.id)
                .where(TaskIssue.status == "open", UserTask.team_id == team_id)
            )
            open_issues_count = open_issues_result.scalar() or 0
        else:
            open_issues_result = await self.db.execute(
                select(func.count(TaskIssue.id)).where(TaskIssue.status == "open")
            )
            open_issues_count = open_issues_result.scalar() or 0

        return {
            "by_status": status_counts,
            "by_priority": priority_counts,
            "open_issues": open_issues_count,
        }
