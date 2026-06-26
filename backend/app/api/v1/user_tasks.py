"""UserTasks API：用户任务管理接口

提供：
1. 任务 CRUD
2. AI 规划调用
3. 任务生命周期管理（启动、暂停、恢复、取消）
4. 进度查询
5. 问题记录管理
6. 任务迭代
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.user_task_service import UserTaskService
from app.services.task_progress_service import TaskProgressService
from app.services.workflow_engine import WorkflowEngine
from app.services.workflow_generator import WorkflowGenerator
from app.schemas.user_task import (
    UserTaskCreate,
    UserTaskUpdate,
    UserTaskResponse,
    TaskIssueCreate,
    TaskIssueUpdate,
    TaskIssueResponse,
    TaskProgressDetailResponse,
    TaskPlanRequest,
    TaskPlanResponse,
    TaskStartRequest,
    TaskIterationRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Task CRUD ────────────────────────────────────────────────

@router.post("", response_model=UserTaskResponse)
async def create_task(
    req: UserTaskCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建用户任务"""
    svc = UserTaskService(db)
    try:
        task = await svc.create_task(
            title=req.title,
            requirement=req.requirement,
            team_id=req.team_id,
            session_id=req.session_id,
            description=req.description,
            priority=req.priority,
        )
        return UserTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[UserTaskResponse])
async def list_tasks(
    team_id: Optional[uuid.UUID] = Query(None, description="按团队筛选"),
    session_id: Optional[uuid.UUID] = Query(None, description="按会话筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    limit: int = Query(100, ge=1, le=500, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
):
    """列出任务"""
    svc = UserTaskService(db)
    tasks = await svc.list_tasks(
        team_id=team_id,
        session_id=session_id,
        status=status,
        limit=limit,
    )
    return [UserTaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=UserTaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情"""
    svc = UserTaskService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return UserTaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=UserTaskResponse)
async def update_task(
    task_id: uuid.UUID,
    req: UserTaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新任务"""
    svc = UserTaskService(db)
    task = await svc.update_task(
        task_id, **req.model_dump(exclude_unset=True)
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return UserTaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除任务"""
    svc = UserTaskService(db)
    success = await svc.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")


# ── AI Planning ────────────────────────────────────────────────

@router.post("/{task_id}/plan", response_model=TaskPlanResponse)
async def plan_task_workflow(
    task_id: uuid.UUID,
    req: TaskPlanRequest,
    db: AsyncSession = Depends(get_db),
):
    """调用 AI 为任务生成执行方案

    1. 获取任务需求
    2. 调用 WorkflowGenerator 生成工作流
    3. 保存工作流定义
    4. 返回规划摘要
    """
    svc = UserTaskService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ["planning", "generated"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot plan task in status: {task.status}"
        )

    try:
        # 调用 AI 生成工作流
        generator = WorkflowGenerator(db)
        plan_result = await generator.plan_from_requirement(
            requirement=task.requirement,
            available_agents=req.available_agents,
            team_context=req.team_context,
        )

        # 保存工作流定义
        workflow = await svc.plan_workflow(
            task_id=task_id,
            workflow_definition=plan_result["workflow"],
            plan_summary={
                "task_name": plan_result["task_name"],
                "task_description": plan_result["task_description"],
                "estimated_steps": plan_result["estimated_steps"],
                "suggestions": plan_result.get("suggestions", []),
                "risks": plan_result.get("risks", []),
            },
        )

        return TaskPlanResponse(
            **plan_result,
            workflow=workflow.definition,
        )

    except Exception as e:
        logger.error(f"Failed to plan workflow for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Task Lifecycle ────────────────────────────────────────────

@router.post("/{task_id}/start", response_model=UserTaskResponse)
async def start_task(
    task_id: uuid.UUID,
    req: TaskStartRequest = TaskStartRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """启动任务执行

    1. 验证任务已生成工作流
    2. 创建工作流实例
    3. 启动后台执行
    4. 返回任务状态
    """
    svc = UserTaskService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.workflow_id:
        raise HTTPException(status_code=400, detail="Task must be planned first")

    if task.status != "generated":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start task in status: {task.status}"
        )

    try:
        # 创建工作流实例
        engine = WorkflowEngine(db)
        instance = await engine.create_instance(
            workflow_id=task.workflow_id,
            session_id=task.session_id,
            initial_state=req.initial_state or {},
        )

        # 更新任务状态
        await svc.start_task(task_id, instance.id)

        # 后台启动执行
        async def run_workflow():
            try:
                await engine.start_instance(
                    instance_id=instance.id,
                    user_input=req.user_input or task.requirement,
                )
            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                await svc.fail_task(task_id, str(e))

        background_tasks.add_task(run_workflow)

        return UserTaskResponse.model_validate(task)

    except Exception as e:
        logger.error(f"Failed to start task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/pause", response_model=UserTaskResponse)
async def pause_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """暂停任务"""
    svc = UserTaskService(db)
    try:
        task = await svc.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # 暂停工作流实例
        if task.workflow_instance_id:
            engine = WorkflowEngine(db)
            await engine.pause_instance(task.workflow_instance_id)

        # 更新任务状态
        updated = await svc.pause_task(task_id)
        return UserTaskResponse.model_validate(updated)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to pause task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume", response_model=UserTaskResponse)
async def resume_task(
    task_id: uuid.UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """恢复任务"""
    svc = UserTaskService(db)
    try:
        task = await svc.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # 恢复工作流实例
        if task.workflow_instance_id:
            engine = WorkflowEngine(db)

            async def run_workflow():
                try:
                    await engine.resume_instance(task.workflow_instance_id)
                except Exception as e:
                    logger.error(f"Workflow resume failed: {e}")
                    await svc.fail_task(task_id, str(e))

            background_tasks.add_task(run_workflow)

        # 更新任务状态
        updated = await svc.resume_task(task_id)
        return UserTaskResponse.model_validate(updated)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resume task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel", response_model=UserTaskResponse)
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """取消任务"""
    svc = UserTaskService(db)
    try:
        task = await svc.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # 取消工作流实例
        if task.workflow_instance_id:
            engine = WorkflowEngine(db)
            await engine.cancel_instance(task.workflow_instance_id)

        # 更新任务状态
        updated = await svc.cancel_task(task_id)
        return UserTaskResponse.model_validate(updated)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Progress Tracking ─────────────────────────────────────────

@router.get("/{task_id}/progress", response_model=TaskProgressDetailResponse)
async def get_task_progress(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取任务进度详情"""
    svc = UserTaskService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.workflow_instance_id:
        return TaskProgressDetailResponse(
            task_id=task.id,
            task_title=task.title,
            status=task.status,
            progress_percentage=task.progress_percentage,
            current_step=None,
            steps=[],
            issues_count=0,
            started_at=task.started_at,
        )

    progress_svc = TaskProgressService(db)
    detail = await progress_svc.get_detailed_progress(task.workflow_instance_id)

    # 统计问题数
    issues = await svc.list_issues(task_id)
    open_issues = [i for i in issues if i.status == "open"]

    return TaskProgressDetailResponse(
        task_id=task.id,
        task_title=task.title,
        status=task.status,
        progress_percentage=detail.get("progress_percentage", 0),
        current_step=detail.get("current_step"),
        steps=detail.get("nodes_status", []),
        issues_count=len(open_issues),
        started_at=task.started_at,
        estimated_completion=detail.get("estimated_completion_at"),
    )


# ── Issue Management ───────────────────────────────────────────

@router.get("/{task_id}/issues", response_model=list[TaskIssueResponse])
async def list_task_issues(
    task_id: uuid.UUID,
    status: Optional[str] = Query(None, description="按状态筛选"),
    severity: Optional[str] = Query(None, description="按严重程度筛选"),
    db: AsyncSession = Depends(get_db),
):
    """列出任务的问题"""
    svc = UserTaskService(db)
    # 验证任务存在
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    issues = await svc.list_issues(task_id, status=status, severity=severity)
    return [TaskIssueResponse.model_validate(i) for i in issues]


@router.post("/{task_id}/issues", response_model=TaskIssueResponse, status_code=201)
async def record_issue(
    task_id: uuid.UUID,
    req: TaskIssueCreate,
    db: AsyncSession = Depends(get_db),
):
    """记录问题"""
    svc = UserTaskService(db)
    # 验证任务存在
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        issue = await svc.record_issue(
            user_task_id=task_id,
            title=req.title,
            severity=req.severity,
            description=req.description,
            workflow_instance_id=req.workflow_instance_id,
            node_execution_id=req.node_execution_id,
            category=req.category,
            created_by=req.created_by,
        )
        return TaskIssueResponse.model_validate(issue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/issues/{issue_id}", response_model=TaskIssueResponse)
async def update_issue(
    issue_id: uuid.UUID,
    req: TaskIssueUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新问题"""
    svc = UserTaskService(db)
    try:
        issue = await svc.update_issue(
            issue_id, **req.model_dump(exclude_unset=True)
        )
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        return TaskIssueResponse.model_validate(issue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/issues/{issue_id}/resolve", response_model=TaskIssueResponse)
async def resolve_issue(
    issue_id: uuid.UUID,
    resolution: str = Query(..., description="解决方案描述"),
    db: AsyncSession = Depends(get_db),
):
    """解决问题"""
    svc = UserTaskService(db)
    try:
        issue = await svc.resolve_issue(issue_id, resolution)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        return TaskIssueResponse.model_validate(issue)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Task Iteration ────────────────────────────────────────────

@router.post("/{task_id}/iterate", response_model=UserTaskResponse)
async def iterate_task(
    task_id: uuid.UUID,
    req: TaskIterationRequest,
    db: AsyncSession = Depends(get_db),
):
    """基于反馈创建任务迭代版本

    1. 创建新的任务，关联原任务
    2. 将用户反馈合并到需求中
    3. 新任务进入规划状态
    """
    svc = UserTaskService(db)
    try:
        new_task = await svc.iterate_task(task_id, req.feedback)
        return UserTaskResponse.model_validate(new_task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to iterate task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Statistics ───────────────────────────────────────────────

@router.get("/stats/summary")
async def get_task_statistics(
    team_id: Optional[uuid.UUID] = Query(None, description="团队ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取任务统计信息"""
    svc = UserTaskService(db)
    stats = await svc.get_task_statistics(team_id)
    return stats
