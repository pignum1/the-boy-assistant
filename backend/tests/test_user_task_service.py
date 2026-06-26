"""UserTaskService 测试：用户任务管理服务测试

测试：
1. 任务 CRUD
2. 任务生命周期管理
3. 问题记录管理
4. 任务迭代
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_task import UserTask, TaskIssue
from app.services.user_task_service import UserTaskService


class TestUserTaskCRUD:
    """用户任务 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_task(self, db: AsyncSession):
        """测试创建任务"""
        svc = UserTaskService(db)
        task = await svc.create_task(
            title="测试任务",
            requirement="这是测试需求",
            priority="high",
        )

        assert task.id is not None
        assert task.title == "测试任务"
        assert task.requirement == "这是测试需求"
        assert task.status == "planning"
        assert task.priority == "high"
        assert task.progress_percentage == 0

    @pytest.mark.asyncio
    async def test_get_task(self, db: AsyncSession):
        """测试获取任务"""
        svc = UserTaskService(db)
        created = await svc.create_task(
            title="获取测试",
            requirement="测试需求",
        )

        task = await svc.get_task(created.id)
        assert task is not None
        assert task.id == created.id
        assert task.title == "获取测试"

    @pytest.mark.asyncio
    async def test_list_tasks(self, db: AsyncSession):
        """测试列出任务"""
        svc = UserTaskService(db)
        await svc.create_task(title="任务1", requirement="需求1")
        await svc.create_task(title="任务2", requirement="需求2")
        await svc.create_task(title="任务3", requirement="需求3")

        tasks = await svc.list_tasks(limit=10)
        assert len(tasks) >= 3

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, db: AsyncSession):
        """测试按状态筛选任务"""
        svc = UserTaskService(db)
        task1 = await svc.create_task(title="运行中", requirement="需求1")
        task2 = await svc.create_task(title="已完成", requirement="需求2")

        # 更新状态
        await svc.update_task(task1.id, status="running")
        await svc.update_task(task2.id, status="completed")

        running_tasks = await svc.list_tasks(status="running")
        assert len(running_tasks) >= 1
        assert all(t.status == "running" for t in running_tasks)

    @pytest.mark.asyncio
    async def test_update_task(self, db: AsyncSession):
        """测试更新任务"""
        svc = UserTaskService(db)
        task = await svc.create_task(title="原标题", requirement="需求")

        updated = await svc.update_task(
            task.id,
            title="新标题",
            progress_percentage=50,
        )

        assert updated.title == "新标题"
        assert updated.progress_percentage == 50

    @pytest.mark.asyncio
    async def test_delete_task(self, db: AsyncSession):
        """测试删除任务"""
        svc = UserTaskService(db)
        task = await svc.create_task(title="待删除", requirement="需求")

        success = await svc.delete_task(task.id)
        assert success is True

        deleted = await svc.get_task(task.id)
        assert deleted is None


class TestTaskLifecycle:
    """任务生命周期管理测试"""

    @pytest.mark.asyncio
    async def test_plan_workflow(self, db: AsyncSession):
        """测试规划工作流"""
        from app.services.workflow_service import WorkflowService

        svc = UserTaskService(db)
        wf_svc = WorkflowService(db)

        task = await svc.create_task(title="规划测试", requirement="测试需求")

        # 创建工作流定义
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始"},
                {"id": "agent1", "type": "Agent", "label": "处理", "config": {"agent_id": str(uuid.uuid4())}},
                {"id": "end", "type": "End", "label": "结束"},
            ],
            "edges": [
                {"source": "start", "target": "agent1", "type": "Forward"},
                {"source": "agent1", "target": "end", "type": "Forward"},
            ],
        }

        plan_summary = {
            "task_name": "规划的任务",
            "estimated_steps": 1,
        }

        workflow = await svc.plan_workflow(
            task.id,
            workflow_def,
            plan_summary,
        )

        assert workflow is not None
        assert workflow.template_type == "custom"

        # 验证任务状态更新
        await db.refresh(task)
        assert task.status == "generated"
        assert task.workflow_id == workflow.id

    @pytest.mark.asyncio
    async def test_start_task(self, db: AsyncSession):
        """测试启动任务"""
        from app.models.workflow_instance import WorkflowInstance
        from app.models.workflow import Workflow

        svc = UserTaskService(db)

        # 先创建一个 workflow 和 workflow_instance
        workflow = Workflow(
            name="测试工作流",
            definition={"nodes": [], "edges": []},
            version=1,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        instance = WorkflowInstance(
            workflow_id=workflow.id,
            status="pending",
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        task = await svc.create_task(title="启动测试", requirement="需求")

        started = await svc.start_task(task.id, instance.id)

        assert started.status == "running"
        assert started.workflow_instance_id == instance.id
        assert started.started_at is not None

    @pytest.mark.asyncio
    async def test_pause_task(self, db: AsyncSession):
        """测试暂停任务"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="暂停测试", requirement="需求")
        await svc.update_task(task.id, status="running")

        paused = await svc.pause_task(task.id)

        assert paused.status == "paused"

    @pytest.mark.asyncio
    async def test_resume_task(self, db: AsyncSession):
        """测试恢复任务"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="恢复测试", requirement="需求")
        await svc.update_task(task.id, status="paused")

        resumed = await svc.resume_task(task.id)

        assert resumed.status == "running"

    @pytest.mark.asyncio
    async def test_cancel_task(self, db: AsyncSession):
        """测试取消任务"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="取消测试", requirement="需求")
        await svc.update_task(task.id, status="running")

        cancelled = await svc.cancel_task(task.id)

        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_complete_task(self, db: AsyncSession):
        """测试完成任务"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="完成测试", requirement="需求")
        await svc.update_task(task.id, status="running")

        completed = await svc.complete_task(task.id, 100)

        assert completed.status == "completed"
        assert completed.progress_percentage == 100
        assert completed.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_task(self, db: AsyncSession):
        """测试任务失败"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="失败测试", requirement="需求")
        await svc.update_task(task.id, status="running")

        failed = await svc.fail_task(task.id, "执行出错")

        assert failed.status == "failed"
        assert failed.completed_at is not None


class TestIssueManagement:
    """问题记录管理测试"""

    @pytest.mark.asyncio
    async def test_record_issue(self, db: AsyncSession):
        """测试记录问题"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="问题测试", requirement="需求")

        issue = await svc.record_issue(
            user_task_id=task.id,
            title="发现Bug",
            severity="high",
            description="功能异常",
        )

        assert issue.id is not None
        assert issue.user_task_id == task.id
        assert issue.title == "发现Bug"
        assert issue.severity == "high"
        assert issue.status == "open"

    @pytest.mark.asyncio
    async def test_list_issues(self, db: AsyncSession):
        """测试列出问题"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="问题列表测试", requirement="需求")
        await svc.record_issue(task.id, "问题1", "low")
        await svc.record_issue(task.id, "问题2", "medium")
        await svc.record_issue(task.id, "问题3", "high")

        issues = await svc.list_issues(task.id)
        assert len(issues) == 3

    @pytest.mark.asyncio
    async def test_list_issues_by_severity(self, db: AsyncSession):
        """测试按严重程度筛选问题"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="严重程度测试", requirement="需求")
        await svc.record_issue(task.id, "低危", "low")
        await svc.record_issue(task.id, "高危", "high")

        high_issues = await svc.list_issues(task.id, severity="high")
        assert len(high_issues) == 1
        assert high_issues[0].title == "高危"

    @pytest.mark.asyncio
    async def test_update_issue(self, db: AsyncSession):
        """测试更新问题"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="更新问题测试", requirement="需求")
        issue = await svc.record_issue(task.id, "原始标题", "medium")

        updated = await svc.update_issue(
            issue.id,
            title="新标题",
            status="in_progress",
        )

        assert updated.title == "新标题"
        assert updated.status == "in_progress"

    @pytest.mark.asyncio
    async def test_resolve_issue(self, db: AsyncSession):
        """测试解决问题"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="解决测试", requirement="需求")
        issue = await svc.record_issue(task.id, "待解决", "medium")

        resolved = await svc.resolve_issue(issue.id, "已修复")

        assert resolved.status == "resolved"
        assert resolved.resolution == "已修复"
        assert resolved.resolved_at is not None


class TestTaskIteration:
    """任务迭代测试"""

    @pytest.mark.asyncio
    async def test_iterate_task(self, db: AsyncSession):
        """测试创建迭代任务"""
        svc = UserTaskService(db)

        original = await svc.create_task(
            title="原始任务",
            requirement="原始需求",
        )
        await svc.update_task(original.id, status="completed")

        iteration = await svc.iterate_task(
            original.id,
            "需要优化性能",
        )

        assert iteration.id != original.id
        assert iteration.title == "原始任务 (迭代)"
        assert iteration.iteration_count == 1
        assert iteration.previous_task_id == original.id
        assert "需要优化性能" in iteration.requirement
        assert iteration.status == "planning"


class TestProgressTracking:
    """进度追踪测试"""

    @pytest.mark.asyncio
    async def test_update_progress(self, db: AsyncSession):
        """测试更新进度"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="进度测试", requirement="需求")

        updated = await svc.update_progress(
            task.id,
            current_step="步骤2",
            progress_percentage=60,
        )

        assert updated.current_step == "步骤2"
        assert updated.progress_percentage == 60

    @pytest.mark.asyncio
    async def test_get_progress_summary(self, db: AsyncSession):
        """测试获取进度摘要"""
        svc = UserTaskService(db)

        task = await svc.create_task(title="摘要测试", requirement="需求")
        await svc.update_progress(task.id, "步骤1", 30)

        summary = await svc.get_progress_summary(task.id)

        assert summary["task_id"] == str(task.id)
        assert summary["title"] == task.title
        assert summary["progress_percentage"] == 30
        assert summary["current_step"] == "步骤1"


class TestStatistics:
    """统计功能测试"""

    @pytest.mark.asyncio
    async def test_get_task_statistics(self, db: AsyncSession):
        """测试获取统计信息"""
        svc = UserTaskService(db)

        # 创建不同状态的任务
        task1 = await svc.create_task(title="任务1", requirement="需求1")
        await svc.update_task(task1.id, status="running")

        task2 = await svc.create_task(title="任务2", requirement="需求2")
        await svc.update_task(task2.id, status="completed")

        task3 = await svc.create_task(title="任务3", requirement="需求3", priority="high")

        stats = await svc.get_task_statistics()

        assert "by_status" in stats
        assert "by_priority" in stats
        assert "open_issues" in stats
