"""SessionTaskService：会话任务 CRUD + 计数维护

职责：
1. 创建/查询/更新/删除 SessionTask
2. 自动维护 Session.task_total / task_completed 计数器
3. 供 DiscussionEngine 和 API 层使用
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_task import SessionTask
from app.models.session import Session

logger = logging.getLogger(__name__)


class SessionTaskService:
    """会话任务 CRUD 服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(
        self,
        session_id: uuid.UUID,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        assigned_agent_id: Optional[uuid.UUID] = None,
        assigned_agent_name: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        expected_output: Optional[str] = None,
    ) -> SessionTask:
        """创建任务 + 更新 session.task_total"""
        task = SessionTask(
            session_id=session_id,
            title=title,
            description=description,
            priority=priority,
            assigned_agent_id=assigned_agent_id,
            assigned_agent_name=assigned_agent_name,
            depends_on=depends_on,
            expected_output=expected_output,
        )
        self.db.add(task)
        await self.db.flush()

        # 更新 session.task_total
        await self._recalc_task_total(session_id)

        await self.db.commit()
        await self.db.refresh(task)
        logger.info(f"SessionTask created: {task.id} title='{title}'")
        return task

    async def update_task(
        self,
        task_id: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_agent_id: Optional[uuid.UUID] = None,
        assigned_agent_name: Optional[str] = None,
        actual_output: Optional[str] = None,
        artifacts: Optional[list[str]] = None,
    ) -> Optional[SessionTask]:
        """更新任务 + 更新计数器"""
        task = await self.db.get(SessionTask, task_id)
        if not task:
            return None

        old_status = task.status

        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
        if priority is not None:
            task.priority = priority
        if assigned_agent_id is not None:
            task.assigned_agent_id = assigned_agent_id
        if assigned_agent_name is not None:
            task.assigned_agent_name = assigned_agent_name
        if actual_output is not None:
            task.actual_output = actual_output
        if artifacts is not None:
            task.artifacts = artifacts

        # 状态变更时更新时间戳
        if status and status != old_status:
            task.updated_at = datetime.now(timezone.utc)
            if status == "claimed" and not task.claimed_at:
                task.claimed_at = datetime.now(timezone.utc)
            if status == "done":
                task.completed_at = datetime.now(timezone.utc)

        await self.db.flush()

        # 如果状态变更涉及 done，重新计算完成数
        if status and (old_status == "done" or status == "done"):
            await self._recalc_task_completed(task.session_id)

        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def list_tasks(self, session_id: uuid.UUID) -> list[SessionTask]:
        """列出会话所有任务（按创建时间排序）"""
        stmt = (
            select(SessionTask)
            .where(SessionTask.session_id == session_id)
            .order_by(SessionTask.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_task(self, task_id: uuid.UUID) -> Optional[SessionTask]:
        """获取单个任务"""
        return await self.db.get(SessionTask, task_id)

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        """删除任务 + 更新计数器"""
        task = await self.db.get(SessionTask, task_id)
        if not task:
            return False
        session_id = task.session_id
        await self.db.delete(task)
        await self.db.flush()
        await self._recalc_task_total(session_id)
        await self._recalc_task_completed(session_id)
        await self.db.commit()
        return True

    async def get_stats(self, session_id: uuid.UUID) -> dict:
        """获取任务统计"""
        stmt = select(
            func.count(SessionTask.id).label("total"),
            func.count(SessionTask.id).filter(SessionTask.status == "done").label("done"),
            func.count(SessionTask.id).filter(SessionTask.status == "in_progress").label("in_progress"),
        ).where(SessionTask.session_id == session_id)
        result = await self.db.execute(stmt)
        row = result.one()
        return {
            "total": row.total or 0,
            "done": row.done or 0,
            "in_progress": row.in_progress or 0,
        }

    async def _recalc_task_total(self, session_id: uuid.UUID):
        """重新计算 session.task_total"""
        stmt = select(func.count(SessionTask.id)).where(
            SessionTask.session_id == session_id
        )
        result = await self.db.execute(stmt)
        total = result.scalar() or 0

        session = await self.db.get(Session, session_id)
        if session:
            session.task_total = total

    async def _recalc_task_completed(self, session_id: uuid.UUID):
        """重新计算 session.task_completed"""
        stmt = select(func.count(SessionTask.id)).where(
            SessionTask.session_id == session_id,
            SessionTask.status == "done",
        )
        result = await self.db.execute(stmt)
        done = result.scalar() or 0

        session = await self.db.get(Session, session_id)
        if session:
            session.task_completed = done

    def task_to_dict(self, task: SessionTask) -> dict:
        """将 ORM 对象转为响应字典"""
        return {
            "id": str(task.id),
            "session_id": str(task.session_id),
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assigned_agent_id": str(task.assigned_agent_id) if task.assigned_agent_id else None,
            "assigned_agent_name": task.assigned_agent_name,
            "depends_on": task.depends_on,
            "expected_output": task.expected_output,
            "actual_output": task.actual_output,
            "artifacts": task.artifacts,
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": task.completed_at.isoformat() if task.completed_at else "",
        }
