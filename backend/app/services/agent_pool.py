"""Agent Pool：运行时 Agent 资源池，支持能力匹配与并发安全

职责：
1. 维护 Agent 的运行时状态（idle / busy / error）
2. 通过 role_slot 匹配合适的 Agent
3. acquire/release 状态转换，保证同一 Agent 不会被并发占用
4. 提供 role_slot → capabilities 的映射

并发安全：所有状态变更通过 asyncio.Lock 保护
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.persona import Persona

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class PoolEntry:
    """Pool 中每个 Agent 的运行时条目"""
    agent_id: str
    agent_name: str
    persona_id: str
    capabilities: dict = field(default_factory=dict)
    status: AgentStatus = AgentStatus.IDLE
    acquired_at: Optional[datetime] = None
    acquired_by: Optional[str] = None  # task_id
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# role_slot → capabilities 的默认映射
ROLE_CAPABILITY_MAP: dict[str, list[str]] = {
    "architect": ["system_design", "architecture", "code_review"],
    "coder": ["coding", "debugging", "testing"],
    "reviewer": ["code_review", "quality_assurance"],
    "tester": ["testing", "validation"],
    "leader": ["coordination", "planning", "decision_making"],
}


class AgentPool:
    """运行时 Agent 资源池"""

    def __init__(self):
        self._entries: dict[str, PoolEntry] = {}
        self._lock = asyncio.Lock()
        self._agent_load: dict[str, int] = {}  # agent_id → 当前任务数
        self._agent_success_rate: dict[str, float] = {}  # agent_id → 成功率

    async def register(self, db: AsyncSession, agent: Agent) -> None:
        """注册 Agent 到池中"""
        persona = await db.get(Persona, agent.persona_id)
        capabilities = {}

        entry = PoolEntry(
            agent_id=str(agent.id),
            agent_name=agent.name,
            persona_id=str(agent.persona_id),
            capabilities=capabilities,
        )
        async with self._lock:
            self._entries[str(agent.id)] = entry
        logger.info(f"AgentPool: registered {agent.name}")

    async def unregister(self, agent_id: str) -> bool:
        """从池中移除 Agent"""
        async with self._lock:
            if agent_id in self._entries:
                del self._entries[agent_id]
                logger.info(f"AgentPool: unregistered {agent_id}")
                return True
            return False

    async def register_team_agents(self, db: AsyncSession, team_id: uuid.UUID) -> int:
        """批量注册团队所有成员 Agent"""
        from app.models.team_member import TeamMember

        result = await db.execute(
            select(TeamMember).where(TeamMember.team_id == team_id)
        )
        members = list(result.scalars().all())

        count = 0
        for member in members:
            agent = await db.get(Agent, member.agent_id)
            if agent:
                await self.register(db, agent)
                count += 1

        logger.info(f"AgentPool: registered {count} agents for team {team_id}")
        return count

    async def acquire(
        self,
        agent_id: Optional[str] = None,
        required_capabilities: Optional[list[str]] = None,
        role_slot: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Optional[PoolEntry]:
        """获取一个空闲 Agent

        优先级：
        1. 指定 agent_id → 精确匹配
        2. 指定 role_slot → 通过 ROLE_CAPABILITY_MAP 映射能力
        3. 指定 required_capabilities → 直接能力匹配
        4. 无要求 → 返回任意空闲 Agent
        """
        async with self._lock:
            # 精确匹配
            if agent_id:
                entry = self._entries.get(agent_id)
                if entry and entry.status == AgentStatus.IDLE:
                    return self._do_acquire(entry, task_id)
                return None

            # 能力匹配：role_slot → capabilities
            caps = required_capabilities or []
            if role_slot and role_slot in ROLE_CAPABILITY_MAP:
                caps = ROLE_CAPABILITY_MAP[role_slot]

            # 收集所有匹配的候选 Agent
            candidates = []
            for entry in self._entries.values():
                if entry.status != AgentStatus.IDLE:
                    continue
                if caps and not self._match_capabilities(entry, caps):
                    continue
                candidates.append(entry)

            if not candidates:
                return None

            # 负载均衡：选当前任务最少的
            candidates.sort(key=lambda e: self._agent_load.get(e.agent_id, 0))

            # 优先选择成功率高的（预留接口）
            if len(candidates) > 1:
                best_load = self._agent_load.get(candidates[0].agent_id, 0)
                tied = [c for c in candidates if self._agent_load.get(c.agent_id, 0) == best_load]
                if len(tied) > 1:
                    tied.sort(key=lambda e: self._agent_success_rate.get(e.agent_id, 0.5), reverse=True)
                    return self._do_acquire(tied[0], task_id)

            return self._do_acquire(candidates[0], task_id)

    async def acquire_with_retry(
        self,
        max_retries: int = 3,
        interval: float = 2.0,
        **acquire_kwargs,
    ) -> Optional[PoolEntry]:
        """带重试的 acquire，间隔等待"""
        for attempt in range(max_retries):
            entry = await self.acquire(**acquire_kwargs)
            if entry:
                return entry
            if attempt < max_retries - 1:
                logger.info(f"AgentPool: acquire retry {attempt + 1}/{max_retries}")
                await asyncio.sleep(interval)
        return None

    def _do_acquire(self, entry: PoolEntry, task_id: Optional[str]) -> PoolEntry:
        """执行 acquire 状态转换（调用方已持有 _lock）"""
        entry.status = AgentStatus.BUSY
        entry.acquired_at = datetime.now(timezone.utc)
        entry.acquired_by = task_id
        self._agent_load[entry.agent_id] = self._agent_load.get(entry.agent_id, 0) + 1
        logger.info(f"AgentPool: acquired {entry.agent_name} (task={task_id}, load={self._agent_load[entry.agent_id]})")
        return entry

    async def release(self, agent_id: str, success: bool = True) -> bool:
        """释放 Agent（busy → idle），更新成功率"""
        async with self._lock:
            entry = self._entries.get(agent_id)
            if entry and entry.status == AgentStatus.BUSY:
                entry.status = AgentStatus.IDLE
                entry.acquired_at = None
                entry.acquired_by = None
                # 更新负载
                current_load = self._agent_load.get(agent_id, 1)
                self._agent_load[agent_id] = max(0, current_load - 1)
                # 更新成功率（指数移动平均）
                old_rate = self._agent_success_rate.get(agent_id, 0.5)
                new_rate = old_rate * 0.9 + (1.0 if success else 0.0) * 0.1
                self._agent_success_rate[agent_id] = round(new_rate, 3)
                logger.info(f"AgentPool: released {entry.agent_name} (load={self._agent_load[agent_id]}, rate={new_rate})")
                return True
            return False

    def get_agent_load(self, agent_id: str) -> int:
        """获取 agent 当前负载"""
        return self._agent_load.get(agent_id, 0)

    def get_pool_stats(self) -> dict:
        """获取池统计信息"""
        return {
            "total": len(self._entries),
            "idle": sum(1 for e in self._entries.values() if e.status == AgentStatus.IDLE),
            "busy": sum(1 for e in self._entries.values() if e.status == AgentStatus.BUSY),
            "error": sum(1 for e in self._entries.values() if e.status == AgentStatus.ERROR),
            "loads": {k: v for k, v in self._agent_load.items()},
            "success_rates": {k: v for k, v in self._agent_success_rate.items()},
        }

    async def mark_error(self, agent_id: str) -> bool:
        """标记 Agent 为错误状态"""
        async with self._lock:
            entry = self._entries.get(agent_id)
            if entry:
                entry.status = AgentStatus.ERROR
                entry.acquired_at = None
                entry.acquired_by = None
                logger.warning(f"AgentPool: {entry.agent_name} marked as error")
                return True
            return False

    async def reset(self, agent_id: str) -> bool:
        """从 error 恢复到 idle"""
        async with self._lock:
            entry = self._entries.get(agent_id)
            if entry and entry.status == AgentStatus.ERROR:
                entry.status = AgentStatus.IDLE
                logger.info(f"AgentPool: {entry.agent_name} reset to idle")
                return True
            return False

    def _match_capabilities(self, entry: PoolEntry, required: list[str]) -> bool:
        """检查 Agent 的 Persona capabilities 是否满足要求"""
        if not required:
            return True
        agent_caps = set(entry.capabilities.keys()) if entry.capabilities else set()
        # 匹配逻辑：Agent 的 capabilities 包含任一所需能力即可
        return any(cap in agent_caps for cap in required)

    def get_status(self, status_filter: Optional[str] = None) -> list[dict]:
        """获取池中所有 Agent 的状态"""
        result = []
        for entry in self._entries.values():
            if status_filter and entry.status.value != status_filter:
                continue
            result.append({
                "agent_id": entry.agent_id,
                "agent_name": entry.agent_name,
                "status": entry.status.value,
                "capabilities": list(entry.capabilities.keys()) if entry.capabilities else [],
                "acquired_by": entry.acquired_by,
                "acquired_at": entry.acquired_at.isoformat() if entry.acquired_at else None,
            })
        return result

    def get_available_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.status == AgentStatus.IDLE)

    def get_busy_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.status == AgentStatus.BUSY)

    @property
    def total_count(self) -> int:
        return len(self._entries)


# Global agent pool
agent_pool = AgentPool()
