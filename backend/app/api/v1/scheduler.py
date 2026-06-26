"""Scheduler API：任务调度状态查询"""

from fastapi import APIRouter

from app.services.scheduler import scheduler

router = APIRouter()


@router.get("/status")
async def get_scheduler_status():
    """获取调度器运行时状态"""
    return scheduler.get_status()
