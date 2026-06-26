"""Observer API：Trace 查询 + Token 统计 + 事件查询"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.observer import trace_manager, token_tracker
from app.services.observer import persister as event_persister

router = APIRouter()


@router.get("/observer/trace/{task_id}")
async def get_trace(task_id: str):
    """获取任务的完整调用树"""
    tree = trace_manager.get_trace_by_task(task_id)
    if not tree:
        return {"error": "Trace not found", "task_id": task_id}
    return tree


@router.get("/observer/tokens")
async def get_token_usage(time_range: str = "24h"):
    """Token 消耗汇总"""
    summary = token_tracker.get_usage_summary(time_range)
    by_model = token_tracker.get_usage_by_model()
    return {
        **summary,
        "by_model_detail": by_model,
    }


@router.get("/observer/status")
async def get_observer_status():
    """Observer 状态"""
    return {
        "active_traces": trace_manager.active_traces,
        "total_spans": trace_manager.total_spans,
        "token_records": token_tracker.total_records,
    }


# ── 事件查询 API ──

@router.get("/events")
async def list_events(
    type: Optional[str] = Query(None, alias="type"),
    session_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """查询系统事件列表（支持按类型、会话、时间过滤）。"""
    await event_persister.ensure_table(db)
    events = await event_persister.query(
        db, event_type=type, session_id=session_id,
        since=since, limit=limit, offset=offset,
    )
    return {"events": events, "total": len(events)}


@router.get("/events/summary")
async def events_summary(
    since: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """按类型分组统计事件数量。"""
    await event_persister.ensure_table(db)
    return await event_persister.summary(db, since=since)


@router.get("/events/task/{task_id}")
async def task_events(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取特定任务的所有事件。"""
    await event_persister.ensure_table(db)
    events = await event_persister.query(
        db, session_id=None, limit=100, offset=0,
    )
    # 在 payload 中筛选 task_id
    task_events = [
        e for e in events
        if e.get("task_id") == task_id or e.get("payload", {}).get("task_id") == task_id
    ]
    return {"task_id": task_id, "events": task_events, "total": len(task_events)}
