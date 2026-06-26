from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.database import async_session
from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    checks = {"status": "ok"}

    # Database check
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis check
    try:
        settings = get_settings()
        redis = Redis.from_url(settings.REDIS_URL, max_connections=2)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "degraded"

    return checks
