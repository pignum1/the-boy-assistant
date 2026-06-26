"""Tool Registry：工具注册与管理"""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool
from app.schemas.tool import ToolCreate, ToolUpdate


class ToolRegistry:
    """Tool 领域服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: ToolCreate) -> Tool:
        tool = Tool(
            name=data.name,
            description=data.description,
            param_schema=data.param_schema,
            server_id=data.server_id,
            is_stateful=data.is_stateful,
            config=data.config,
        )
        self.db.add(tool)
        await self.db.commit()
        await self.db.refresh(tool)
        return tool

    async def get(self, tool_id: uuid.UUID) -> Optional[Tool]:
        result = await self.db.execute(select(Tool).where(Tool.id == tool_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Tool]:
        result = await self.db.execute(select(Tool).where(Tool.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Tool]:
        result = await self.db.execute(select(Tool).order_by(Tool.created_at))
        return list(result.scalars().all())

    async def list_by_server(self, server_id: uuid.UUID) -> list[Tool]:
        result = await self.db.execute(
            select(Tool).where(Tool.server_id == server_id).order_by(Tool.name)
        )
        return list(result.scalars().all())

    async def update(self, tool_id: uuid.UUID, data: ToolUpdate) -> Optional[Tool]:
        tool = await self.get(tool_id)
        if not tool:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tool, field, value)
        await self.db.commit()
        await self.db.refresh(tool)
        return tool

    async def delete(self, tool_id: uuid.UUID) -> bool:
        tool = await self.get(tool_id)
        if not tool:
            return False
        await self.db.delete(tool)
        await self.db.commit()
        return True

    @staticmethod
    def get_effective_tools(
        persona_declared: list[str],
        team_whitelist: Optional[list[str]] = None,
    ) -> list[str]:
        if team_whitelist is None:
            return list(persona_declared)
        return [t for t in persona_declared if t in team_whitelist]


async def seed_preset_tools(db: AsyncSession) -> None:
    """预设工具已移除 — 所有工具通过 MCP 服务器发现"""
    pass


# ── 向后兼容的模块级函数 ──

async def register_tool(db: AsyncSession, data: ToolCreate) -> Tool:
    return await ToolRegistry(db).register(data)


async def get_tool(db: AsyncSession, tool_id: uuid.UUID) -> Optional[Tool]:
    return await ToolRegistry(db).get(tool_id)


async def get_tool_by_name(db: AsyncSession, name: str) -> Optional[Tool]:
    return await ToolRegistry(db).get_by_name(name)


async def list_tools(db: AsyncSession) -> list[Tool]:
    return await ToolRegistry(db).list_all()


async def update_tool(
    db: AsyncSession, tool_id: uuid.UUID, data: ToolUpdate
) -> Optional[Tool]:
    return await ToolRegistry(db).update(tool_id, data)


async def delete_tool(db: AsyncSession, tool_id: uuid.UUID) -> bool:
    return await ToolRegistry(db).delete(tool_id)


def get_effective_tools(
    persona_declared: list[str],
    team_whitelist: Optional[list[str]] = None,
) -> list[str]:
    return ToolRegistry.get_effective_tools(persona_declared, team_whitelist)
