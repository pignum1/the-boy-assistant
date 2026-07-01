"""Agent Service：Agent CRUD 操作"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.model import Model
from app.models.persona import Persona
from app.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)


class AgentService:
    """Agent 领域服务：负责 Agent 实体的 CRUD"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: AgentCreate) -> Agent:
        """创建 Agent：校验 Persona + Model → 组装 → 持久化"""
        persona = await self.db.get(Persona, data.persona_id)
        if not persona:
            raise ValueError(f"Persona {data.persona_id} not found")

        model = await self.db.get(Model, data.model_id)
        if not model:
            raise ValueError(f"Model {data.model_id} not found")

        tool_ids_str = [str(tid) for tid in (data.tool_ids or [])] or None

        agent = Agent(
            name=data.name,
            default_model_id=data.model_id,
            persona_id=data.persona_id,
            tools=tool_ids_str,
            status="idle",
            execution_mode=data.execution_mode or "single_pass",
            execution_config=data.execution_config,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get(self, agent_id: uuid.UUID) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Agent]:
        result = await self.db.execute(select(Agent).order_by(Agent.created_at))
        return list(result.scalars().all())

    async def update(self, agent_id: uuid.UUID, data: AgentUpdate) -> Optional[Agent]:
        agent = await self.get(agent_id)
        if not agent:
            return None
        update_data = data.model_dump(exclude_unset=True)

        # 映射字段名：schema 中的 model_id → 模型的 default_model_id
        if "model_id" in update_data:
            update_data["default_model_id"] = update_data.pop("model_id")

        if "tool_ids" in update_data and update_data["tool_ids"] is not None:
            update_data["tools"] = [str(tid) for tid in update_data.pop("tool_ids")]
        else:
            update_data.pop("tool_ids", None)
        for field, value in update_data.items():
            setattr(agent, field, value)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent_id: uuid.UUID) -> bool:
        agent = await self.get(agent_id)
        if not agent:
            return False
        await self.db.delete(agent)
        await self.db.commit()
        return True


# ── 向后兼容的模块级函数 ──────────────────────────────────

async def create_agent(db: AsyncSession, data: AgentCreate) -> Agent:
    return await AgentService(db).create(data)


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Optional[Agent]:
    return await AgentService(db).get(agent_id)


async def list_agents(db: AsyncSession) -> list[Agent]:
    return await AgentService(db).list_all()


async def update_agent(
    db: AsyncSession, agent_id: uuid.UUID, data: AgentUpdate
) -> Optional[Agent]:
    return await AgentService(db).update(agent_id, data)


async def delete_agent(db: AsyncSession, agent_id: uuid.UUID) -> bool:
    return await AgentService(db).delete(agent_id)
