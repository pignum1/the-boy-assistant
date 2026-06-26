"""System API：综合系统状态"""

from fastapi import APIRouter

from app.services.agent_pool import agent_pool
from app.services.scheduler import scheduler
from app.services.blackboard import blackboard

router = APIRouter()


@router.get("/api/v1/system/status")
async def get_system_status():
    """综合系统状态：Agent Pool + Scheduler + Blackboard"""
    return {
        "agent_pool": {
            "total": agent_pool.total_count,
            "available": agent_pool.get_available_count(),
            "busy": agent_pool.get_busy_count(),
            "agents": agent_pool.get_status(),
        },
        "scheduler": scheduler.get_status(),
        "blackboard": blackboard.get_status(),
    }
