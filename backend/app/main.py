from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health, personas, keys, tools, agents, memories, knowledge, skills, model_router, models, teams, sops, tasks, mcp_servers, workflows, workflow_generator, workflow_events, user_tasks
from app.api.v1 import sessions as sessions_api
from app.api.v1 import scheduler as scheduler_api
from app.api.v1 import system as system_api
from app.api.v1 import ws as ws_api
from app.api.v1 import observer as observer_api
from app.core.database import async_session, engine


# ── Configure application logging ──
# Without this, `app.*` loggers have no handler and INFO records are silently
# dropped (Python's lastResort only emits WARNING+), which made the delegation
# pipeline (M0–M7) unobservable. Wire root + `app` loggers to stderr.
def _configure_logging() -> None:
    try:
        from app.core.config import get_settings
        level_name = (get_settings().LOG_LEVEL or "INFO").upper()
    except Exception:
        level_name = "INFO"
    level = getattr(logging, level_name, logging.INFO)

    _fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_fmt)

    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)

    # Ensure app + collaboration loggers propagate at the configured level
    for name in ("app", "app.services", "app.services.collaboration"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = True


_configure_logging()
logger = logging.getLogger(__name__)


async def _seed_data():
    """Seed preset data on startup（使用 async with 保证连接生命周期）"""
    try:
        async with async_session() as db:
            from app.services.persona_service import seed_preset_personas
            from app.services.tool_registry import seed_preset_tools
            from app.services.model_router import seed_preset_models
            await seed_preset_personas(db)
            await seed_preset_tools(db)
            await seed_preset_models(db)

            from app.services.skill_registry import SkillRegistry
            skill_svc = SkillRegistry(db)
            await skill_svc.scan_skills_dir()

            logger.info("Preset personas, tools, models and skills seeded")
    except Exception as e:
        logger.warning(f"Failed to seed data (DB not ready?): {e}")
    finally:
        # 启动完成后 dispose 引擎，让后续请求重新获取连接
        # 避免 seed 阶段的连接残留影响后续请求
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _seed_data()

    # 启动 Scheduler 后台循环
    from app.services.scheduler import scheduler
    scheduler.start()
    logger.info("Scheduler started")

    # 连接 Blackboard（Redis 可选，无 Redis 时降级为内存模式）
    from app.services.blackboard import blackboard
    await blackboard.connect()
    logger.info("Blackboard connected")

    # 初始化告警 Webhook（Slack / Discord / Custom）
    from app.services.alert_webhook import init_alerts_from_config
    init_alerts_from_config()

    # 启动 WS Broadcaster（Blackboard → WebSocket 桥接）
    from app.services.ws_broadcaster import create_broadcaster
    global broadcaster_instance
    broadcaster_instance = create_broadcaster()
    await broadcaster_instance.start()

    # 启动 Observer 事件总线（注册持久化 handler）
    from app.services.observer.bus import bus as event_bus
    from app.services.observer.persister import ensure_table, persist
    from app.services.observer.events import EventType
    async def _persist_handler(event):
        from app.core.database import async_session as _sess
        async with _sess() as db:
            await ensure_table(db)
            await persist(db, event)
    event_bus.subscribe_all(_persist_handler)

    yield

    # 关闭
    await scheduler.stop()
    if broadcaster_instance:
        await broadcaster_instance.stop()
    await blackboard.disconnect()
    await engine.dispose()


broadcaster_instance = None

app = FastAPI(
    title="The Boy Assistant",
    description="Enterprise AI Multi-Agent Collaboration Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# 速率限制中间件（最早添加 → 最内层）
from app.core.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# API Key 认证中间件
from app.core.auth import ApiKeyMiddleware
app.add_middleware(ApiKeyMiddleware)

# Observer trace 中间件
from app.services.observer.middleware import TraceMiddleware
app.add_middleware(TraceMiddleware)

# CORS 中间件（最外层 — 最后添加，先处理预检请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(personas.router, prefix="/api/v1/personas", tags=["Personas"])
app.include_router(tools.router, prefix="/api/v1/tools", tags=["Tools"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
app.include_router(keys.router, prefix="/api/v1", tags=["Keys"])
app.include_router(memories.router, prefix="/api/v1/memories", tags=["Memories"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["Knowledge"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["Skills"])
app.include_router(model_router.router, prefix="/api/v1/router", tags=["Model Router"])
app.include_router(models.router, prefix="/api/v1/models", tags=["Models"])
app.include_router(teams.router, prefix="/api/v1/teams", tags=["Teams"])
app.include_router(sops.router, prefix="/api/v1/sops", tags=["SOPs"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["Workflows"])
app.include_router(workflow_generator.router, prefix="/api/v1/workflow-generator", tags=["Workflow Generator"])
app.include_router(workflow_events.router, prefix="/api/v1/workflow-events", tags=["Workflow Events"])
app.include_router(user_tasks.router, prefix="/api/v1/user-tasks", tags=["User Tasks"])

app.include_router(mcp_servers.router, prefix="/api/v1/mcp-servers", tags=["MCP Servers"])
app.include_router(sessions_api.router, prefix="/api/v1/sessions", tags=["Sessions"])
app.include_router(scheduler_api.router, prefix="/api/v1/scheduler", tags=["Scheduler"])
app.include_router(system_api.router, tags=["System"])
app.include_router(ws_api.router)
app.include_router(observer_api.router, prefix="/api/v1", tags=["Observer"])
