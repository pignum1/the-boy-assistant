"""Tasks API：SOP 任务启动 / 恢复 / 查询

任务启动通过 Scheduler 入队，后台异步执行
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import Task
from app.services.sop_engine import SOPEngine
from app.services.scheduler import scheduler, Priority
from app.schemas.task import TaskStartRequest, TaskResumeRequest

router = APIRouter()


async def _run_sop_task(
    sop_id: uuid.UUID,
    sop_team_id: str,
    task_input: dict,
    auto_approve: bool,
    session_id: str = None,
) -> None:
    """Scheduler 执行的 SOP 任务函数"""
    from app.core.database import async_session

    async with async_session() as db:
        engine = SOPEngine(db)
        try:
            task = await engine.start_task(
                sop_id=sop_id,
                team_id=uuid.UUID(sop_team_id),
                task_input=task_input,
                auto_approve_hitl=auto_approve,
                session_id=uuid.UUID(session_id) if session_id else None,
            )
            await engine.run_until_paused(task.id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"SOP task execution failed: {e}")


@router.post("")
async def start_task(
    req: TaskStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """启动 SOP 任务（通过 Scheduler 入队）"""
    # 先验证 SOP 和 Team 存在
    engine = SOPEngine(db)

    try:
        task = await engine.start_task(
            sop_id=req.sop_id,
            team_id=req.team_id,
            task_input=req.input,
            auto_approve_hitl=req.auto_approve_hitl,
            session_id=req.session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 通过 Scheduler 异步执行（不阻塞 HTTP 请求）
    task_id = str(task.id)
    team_id_str = str(req.team_id)
    priority = Priority.NORMAL

    scheduler.enqueue(
        task_func=_run_sop_task,
        task_id=task_id,
        priority=priority,
        team_id=team_id_str,
        sop_id=req.sop_id,
        sop_team_id=team_id_str,
        task_input=req.input,
        auto_approve=req.auto_approve_hitl,
        session_id=str(req.session_id) if req.session_id else None,
    )

    return {
        **_task_response(task),
        "scheduler_status": "queued",
    }


@router.get("")
async def list_tasks(
    team_id: uuid.UUID = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """查询任务列表"""
    from app.models.sop import SOP

    q = select(Task).order_by(Task.created_at.desc())
    if team_id:
        q = q.where(Task.team_id == team_id)
    if status:
        q = q.where(Task.status == status)
    result = await db.execute(q)
    tasks = list(result.scalars().all())

    # 批量获取 SOP 名称
    sop_ids = {t.sop_id for t in tasks if t.sop_id}
    sop_names = {}
    for sop_id in sop_ids:
        sop = await db.get(SOP, sop_id)
        if sop:
            sop_names[str(sop_id)] = sop.name

    return [_task_response(t, sop_names.get(str(t.sop_id))) for t in tasks]


@router.get("/pending-hitl")
async def pending_hitl_tasks(db: AsyncSession = Depends(get_db)):
    """查询等待人工审批的任务"""
    q = select(Task).where(Task.status.in_(["paused", "running"])).order_by(Task.created_at.desc())
    result = await db.execute(q)
    tasks = list(result.scalars().all())

    pending = []
    for t in tasks:
        if t.state and t.state.get("hitl_pending"):
            pending.append({
                **_task_response(t),
                "hitl_data": t.state.get("hitl_data", {}),
            })
    return pending


@router.get("/{task_id}")
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # 获取 SOP 名称
    sop_name = None
    if task.sop_id:
        from app.models.sop import SOP
        sop = await db.get(SOP, task.sop_id)
        if sop:
            sop_name = sop.name
    return {**_task_response(task), "sop_name": sop_name}


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: uuid.UUID,
    req: TaskResumeRequest,
    db: AsyncSession = Depends(get_db),
):
    """从 HITL 暂停恢复任务"""
    engine = SOPEngine(db)

    try:
        task = await engine.resume_task(task_id, action=req.action, comment=req.comment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _task_response(task)


def _task_response(task: Task, sop_name: str = None) -> dict:
    response = {
        "id": str(task.id),
        "team_id": str(task.team_id),
        "sop_id": str(task.sop_id),
        "status": task.status,
        "input": task.input,
        "state": task.state,
        "artifacts": task.artifacts,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }
    if sop_name:
        response["sop_name"] = sop_name
    return response
