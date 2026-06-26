"""Model Router API：复杂度分类 + 模型路由"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.model_router import ModelRouter

router = APIRouter()


class ClassifyRequest(BaseModel):
    message: str
    history_length: Optional[int] = None


class RouteRequest(BaseModel):
    message: str
    default_model_id: str


@router.post("/classify")
async def classify_complexity(
    req: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """分类消息的任务复杂度"""
    router_svc = ModelRouter(db)
    history = [{"role": "user", "content": ""}] * (req.history_length or 0) if req.history_length else None
    complexity = await router_svc.classify_complexity(req.message, history)

    return {
        "message": req.message[:100],
        "complexity": complexity.value,
    }


@router.post("/route")
async def route_model(
    req: RouteRequest,
    db: AsyncSession = Depends(get_db),
):
    """根据复杂度选择最合适的模型"""
    router_svc = ModelRouter(db)
    try:
        model_id = uuid.UUID(req.default_model_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid model_id")

    complexity = await router_svc.classify_complexity(req.message)
    model = await router_svc.select_model(complexity, model_id)

    return {
        "complexity": complexity.value,
        "selected_model": {
            "id": str(model.id),
            "name": model.model_name,
            "provider": model.provider,
            "capabilities": model.capabilities,
            "context_window": model.context_window,
        },
    }
