"""共享测试 Fixtures：数据库会话工厂、种子数据辅助函数

测试环境通过 TESTING=true 环境变量自动启用 NullPool（无连接池）。
"""

import os
import pytest
import pytest_asyncio
import uuid

# 在导入 app 之前设置测试环境标记，触发 NullPool
os.environ["TESTING"] = "true"

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.sop_engine import SOPEngine
from app.services.sop_state import TaskState
from app.services.sop_router import SOPRouter
from app.services.sop_node_executor import SOPNodeExecutor
from app.services.team_manager import TeamManager
from app.services.sop_service import SOPService
from app.services.condition_router import ConditionRouter
from app.services.loop_controller import LoopController
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.sop import SOP
from app.models.task import Task
from app.models.persona import Persona
from app.models.model import Model
from app.models.agent import Agent


# ── 数据库 Session 工厂 ──────────────────────────────────

def _test_session_factory():
    """NullPool: 每次会话使用独立连接，避免 asyncpg 并发冲突"""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


test_session = _test_session_factory()


@pytest.fixture
def db():
    """获取一个独立的测试数据库会话"""
    return test_session()


# ── API 测试客户端 Fixture ────────────────────────────────

@pytest_asyncio.fixture
async def api_client():
    """创建测试用 HTTP 客户端，自动清理 dependency_overrides"""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.core.database import get_db

    # 用 NullPool 版本的 get_db 覆盖 FastAPI 的数据库依赖
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 测试结束后清理覆盖
    app.dependency_overrides.clear()


async def _override_get_db():
    """NullPool 版本的 get_db，用于 API 测试"""
    async with test_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── SOP 图 Fixtures ─────────────────────────────────────

@pytest.fixture
def sample_sop_nodes():
    """完整 6 节点 SOP 图"""
    return [
        {"id": "n1", "type": "start"},
        {"id": "n2", "type": "agent_action", "role_slot": "architect"},
        {"id": "n3", "type": "hitl", "message": "确认方案",
         "config": {"require_human": True, "timeout": 300}},
        {"id": "n4", "type": "agent_action", "role_slot": "coder"},
        {"id": "n5", "type": "validation", "checks": ["lint"], "pass_threshold": 80},
        {"id": "n6", "type": "end"},
    ]


@pytest.fixture
def sample_sop_edges():
    """完整 SOP 边（含条件路由）"""
    return [
        {"from": "n1", "to": "n2"},
        {"from": "n2", "to": "n3"},
        {"from": "n3", "to": "n4", "condition": "hitl_result == approve"},
        {"from": "n3", "to": "n2", "condition": "hitl_result == reject"},
        {"from": "n4", "to": "n5"},
        {"from": "n5", "to": "n6", "condition": "validations.passed"},
        {"from": "n5", "to": "n4", "condition": "not validations.passed"},
    ]


@pytest.fixture
def simple_sop_nodes():
    """简单 3 节点 SOP：agent → validation → end"""
    return [
        {"id": "s1", "type": "agent_action", "role_slot": "coder"},
        {"id": "s2", "type": "validation", "checks": ["lint"], "pass_threshold": 60},
        {"id": "s3", "type": "end"},
    ]


@pytest.fixture
def simple_sop_edges():
    return [
        {"from": "s1", "to": "s2"},
        {"from": "s2", "to": "s3", "condition": "validations.passed"},
        {"from": "s2", "to": "s1", "condition": "not validations.passed"},
    ]


# ── 种子数据辅助 ─────────────────────────────────────────

async def seed_team(session):
    """创建一个包含 architect + coder 成员的测试团队"""
    tag = uuid.uuid4().hex[:6]
    persona = Persona(name=f"P-{tag}", system_prompt="test")
    session.add(persona)
    await session.commit()
    await session.refresh(persona)

    model = Model(display_name=f"m-{tag}", provider="test", model_name=f"test-model-{tag}")
    session.add(model)
    await session.commit()
    await session.refresh(model)

    architect = Agent(name=f"Arc-{tag}", persona_id=persona.id, default_model_id=model.id)
    coder = Agent(name=f"Code-{tag}", persona_id=persona.id, default_model_id=model.id)
    session.add_all([architect, coder])
    await session.commit()
    await session.refresh(architect)
    await session.refresh(coder)

    tm = TeamManager(session)
    team = await tm.create_team(name=f"Team-{tag}", description="test", leader_id=architect.id)
    await tm.add_member(team.id, architect.id, "architect")
    await tm.add_member(team.id, coder.id, "coder")

    return {
        "team": team, "architect": architect, "coder": coder,
        "persona": persona, "model": model,
    }


async def seed_sop(session, team_id):
    """创建一个测试 SOP"""
    svc = SOPService(session)
    return await svc.create_sop(
        team_id=team_id,
        name=f"SOP-{uuid.uuid4().hex[:6]}",
        nodes=[
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "agent_action", "role_slot": "architect"},
            {"id": "n3", "type": "hitl", "message": "确认",
             "config": {"require_human": True, "timeout": 300}},
            {"id": "n4", "type": "agent_action", "role_slot": "coder"},
            {"id": "n5", "type": "validation", "checks": ["lint"], "pass_threshold": 80},
            {"id": "n6", "type": "end"},
        ],
        edges=[
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4", "condition": "hitl_result == approve"},
            {"from": "n3", "to": "n2", "condition": "hitl_result == reject"},
            {"from": "n4", "to": "n5"},
            {"from": "n5", "to": "n6", "condition": "validations.passed"},
            {"from": "n5", "to": "n4", "condition": "not validations.passed"},
        ],
    )
