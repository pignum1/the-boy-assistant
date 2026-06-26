import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.schemas.memory import MemoryLevel, MemoryType

logger = logging.getLogger(__name__)

# Redis key pattern for active session memories
SESSION_KEY = "memory:session:{session_id}"


class MemoryManager:
    """四层记忆管理器：L1 System / L2 Team / L3 Agent Global / L4 Context"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_memory(
        self,
        level: str,
        content: str,
        type: str = "standard",
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        session_id: Optional[str] = None,
        importance: float = 0.5,
        created_by: Optional[str] = None,
        metadata_: Optional[dict] = None,
    ) -> Memory:
        """写入一条记忆"""
        memory = Memory(
            level=level,
            type=type,
            content=content,
            importance=importance,
            team_id=team_id,
            agent_id=agent_id,
            session_id=session_id,
            created_by=created_by,
            metadata_=metadata_,
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        logger.info(f"Memory saved: level={level} type={type} id={memory.id}")
        return memory

    async def get_memories(
        self,
        level: str,
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        type: Optional[str] = None,
        limit: int = 20,
        order_by_importance: bool = False,
    ) -> list[Memory]:
        """按条件查询记忆"""
        conditions = [Memory.level == level]
        if team_id is not None:
            conditions.append(Memory.team_id == team_id)
        if agent_id is not None:
            conditions.append(Memory.agent_id == agent_id)
        if type is not None:
            conditions.append(Memory.type == type)

        stmt = select(Memory).where(and_(*conditions))
        if order_by_importance:
            stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc())
        else:
            stmt = stmt.order_by(Memory.created_at.desc())
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_agent_view(
        self,
        agent_id: uuid.UUID,
        team_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """获取 Agent 的四层记忆视图
        规则：L1 全局 + L2(team_id) + L3(agent_id) + L4(agent_id+team_id)
        """
        # L1 System Memory: 所有 Agent 可见
        l1 = await self.get_memories(level=MemoryLevel.system, limit=50)

        # L2 Team Memory: 同 team_id 可见
        l2 = []
        if team_id:
            l2 = await self.get_memories(
                level=MemoryLevel.team, team_id=team_id, limit=50
            )

        # L3 Agent Global: agent_id 匹配
        l3 = await self.get_memories(
            level=MemoryLevel.agent_global, agent_id=agent_id, limit=50
        )

        # L4 Context: agent_id + team_id 唯一确定（无 team_id 时返回空）
        l4 = []
        if team_id:
            l4_conditions = [Memory.level == MemoryLevel.context, Memory.agent_id == agent_id, Memory.team_id == team_id]
            stmt = (
                select(Memory)
                .where(and_(*l4_conditions))
                .order_by(Memory.created_at.desc())
                .limit(50)
            )
            result = await self.db.execute(stmt)
            l4 = list(result.scalars().all())

        return {
            "L1_system": l1,
            "L2_team": l2,
            "L3_agent_global": l3,
            "L4_context": l4,
        }

    async def get_memory(self, memory_id: uuid.UUID) -> Optional[Memory]:
        """获取单条记忆"""
        return await self.db.get(Memory, memory_id)

    async def delete_memory(self, memory_id: uuid.UUID) -> bool:
        """删除单条记忆"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        await self.db.delete(memory)
        await self.db.commit()
        logger.info(f"Memory deleted: {memory_id}")
        return True

    
    async def cleanup_old_memories(self, days: int = 30) -> int:
        """清理指定天数前的短期记忆。返回删除条数。"""
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            delete(Memory).where(
                Memory.level == MemoryLevel.short_term,
                Memory.created_at < cutoff,
            )
        )
        deleted = result.rowcount
        await self.db.commit()
        logger.info(f"Cleaned up {deleted} memories older than {days} days")
        return deleted

    async def delete_memories(
        self,
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        level: Optional[str] = None,
    ) -> int:
        """按条件批量删除记忆，返回删除条数"""
        conditions = []
        if team_id:
            conditions.append(Memory.team_id == team_id)
        if agent_id:
            conditions.append(Memory.agent_id == agent_id)
        if level:
            conditions.append(Memory.level == level)
        if not conditions:
            return 0

        stmt = delete(Memory).where(and_(*conditions))
        result = await self.db.execute(stmt)
        await self.db.commit()
        logger.info(f"Deleted {result.rowcount} memories")
        return result.rowcount

    async def compute_importance(
        self,
        memory: Memory,
        freshness_weight: float = 0.3,
        authority_weight: float = 0.3,
        base_weight: float = 0.4,
    ) -> float:
        """自动计算重要性分数
        - freshness: 创建时间越近越高
        - authority: 写入者角色权重 (system > leader > member)
        """
        # Freshness: 过去7天=1.0, 30天=0.5, 更久=0.2
        now = datetime.now(timezone.utc)
        age_hours = (now - memory.created_at).total_seconds() / 3600
        if age_hours < 168:  # 7 days
            freshness = 1.0 - (age_hours / 168) * 0.3
        elif age_hours < 720:  # 30 days
            freshness = 0.7 - ((age_hours - 168) / 552) * 0.2
        else:
            freshness = max(0.1, 0.5 - (age_hours / 8760) * 0.1)

        # Authority: system=1.0, leader=0.8, member=0.5, None=0.6
        authority_map = {"system": 1.0, "leader": 0.8, "member": 0.5}
        authority = authority_map.get(memory.created_by or "", 0.6)

        # Base: existing importance
        score = (
            freshness * freshness_weight
            + authority * authority_weight
            + memory.importance * base_weight
        )
        return round(min(1.0, max(0.0, score)), 3)

    async def refresh_importance(
        self,
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
    ) -> int:
        """批量重新计算重要性"""
        conditions = []
        if team_id:
            conditions.append(Memory.team_id == team_id)
        if agent_id:
            conditions.append(Memory.agent_id == agent_id)

        stmt = select(Memory)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.db.execute(stmt)
        memories = list(result.scalars().all())

        count = 0
        for m in memories:
            m.importance = await self.compute_importance(m)
            count += 1
        await self.db.commit()
        logger.info(f"Refreshed importance for {count} memories")
        return count

    async def save_dialog_memory(
        self,
        agent_id: uuid.UUID,
        team_id: Optional[uuid.UUID],
        user_message: str,
        assistant_message: str,
        session_id: Optional[str] = None,
        reasoning_meta: Optional[dict] = None,
    ) -> Memory:
        """对话后自动保存 L4 Context Memory

        reasoning_meta: 可选的推理元数据（路由决策、工具调用、上下文注入等）
        """
        content = f"用户: {user_message}\n助手: {assistant_message}"
        return await self.save_memory(
            level=MemoryLevel.context,
            content=content,
            type=MemoryType.context,
            agent_id=agent_id,
            team_id=team_id,
            session_id=session_id,
            importance=0.4,
            created_by="system",
            metadata_=reasoning_meta,
        )
