"""数据库基础设施：异步引擎 + 会话工厂

设计原则：
1. 连接池启用 pre_ping，自动淘汰失效连接
2. get_db() 保证异常时回滚 + 关闭，避免脏连接回池
3. 支持 TESTING 模式切换 NullPool（无连接池，每次新建连接）
"""

import os
import logging

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 是否为测试环境
TESTING = os.getenv("TESTING", "false").lower() in ("true", "1", "yes")

settings = get_settings()

# 测试环境使用 NullPool（无连接池），生产使用连接池 + pre_ping
_engine_kwargs = {
    "echo": settings.LOG_LEVEL == "DEBUG",
}
if TESTING:
    _engine_kwargs["poolclass"] = NullPool
    logger.info("Database: NullPool mode (TESTING=true)")
else:
    _engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,    # 每次从池中取连接前先 ping，自动淘汰断连
        "pool_recycle": 1800,     # 30 分钟回收，避免数据库侧主动断开
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入的数据库会话工厂

    保证：
    - 正常流程：yield session → commit 由调用方控制 → close 归还连接
    - 异常流程：rollback + close，避免脏连接被回收到池中
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
