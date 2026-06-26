"""Session Manager：Agent-Team 会话隔离与生命周期管理

职责：
1. 每个任务执行时创建独立的 Agent Session
2. 管理对话上下文、记忆视图、有状态工具实例
3. Session 超时 GC（后台扫描清理）
4. 注入上下文到 agent_chat 调用
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SessionStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


@dataclass
class AgentSession:
    """Agent 运行时会话"""
    session_id: str
    team_id: str
    agent_id: str
    task_id: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    context: dict = field(default_factory=dict)       # 对话上下文
    memory_view: dict = field(default_factory=dict)    # 四层记忆引用
    tool_instances: dict[str, Any] = field(default_factory=dict)  # 有状态工具
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionManager:
    """Session 生命周期管理器"""

    def __init__(self, db: AsyncSession, ttl_seconds: int = 3600):
        self.db = db
        self._sessions: dict[str, AgentSession] = {}
        self._session_tools: dict[str, set[str]] = {}  # session_id → tool names
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._gc_task: Optional[asyncio.Task] = None

    async def create_session(
        self,
        team_id: str,
        agent_id: str,
        task_id: Optional[str] = None,
    ) -> AgentSession:
        """创建新 Session，加载记忆视图"""
        from app.services.memory_manager import MemoryManager

        session_id = str(uuid.uuid4())

        # 加载四层记忆
        memory_mgr = MemoryManager(self.db)
        try:
            memory_view = await memory_mgr.get_agent_view(
                agent_id=uuid.UUID(agent_id),
                team_id=uuid.UUID(team_id) if team_id else None,
            )
        except Exception as e:
            logger.warning(f"Failed to load memory view for session: {e}")
            memory_view = {}

        session = AgentSession(
            session_id=session_id,
            team_id=team_id,
            agent_id=agent_id,
            task_id=task_id,
            memory_view=memory_view,
        )

        async with self._lock:
            self._sessions[session_id] = session
            self._session_tools[session_id] = set()

        logger.info(f"Session created: {session_id} agent={agent_id} team={team_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取 Session"""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_or_create_session(
        self,
        team_id: str,
        agent_id: str,
        task_id: Optional[str] = None,
    ) -> AgentSession:
        """查找活跃 Session 或创建新的"""
        async with self._lock:
            for s in self._sessions.values():
                if (s.agent_id == agent_id and s.team_id == team_id
                        and s.status == SessionStatus.ACTIVE):
                    s.last_active = datetime.now(timezone.utc)
                    return s

        return await self.create_session(team_id, agent_id, task_id)

    async def close_session(self, session_id: str) -> bool:
        """关闭 Session：工具 cleanup + 记忆 flush"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.status == SessionStatus.CLOSED:
                return False

            # 清理有状态工具
            tool_names = self._session_tools.pop(session_id, set())
            for tool_name in tool_names:
                tool_instance = session.tool_instances.pop(tool_name, None)
                if tool_instance and hasattr(tool_instance, "cleanup"):
                    try:
                        await tool_instance.cleanup()
                    except Exception as e:
                        logger.warning(f"Tool cleanup failed for {tool_name}: {e}")

            # flush 上下文记忆
            if session.context:
                try:
                    await self._flush_context_memory(session)
                except Exception as e:
                    logger.warning(f"Memory flush failed for session {session_id}: {e}")

            session.status = SessionStatus.CLOSED
            del self._sessions[session_id]
            logger.info(f"Session closed: {session_id}")
            return True

    async def inject_context(self, session: AgentSession, task_state: dict) -> dict:
        """将 Session 上下文注入到 agent_chat 调用参数

        返回增强后的参数 dict，包含记忆和上下文信息
        """
        context = {
            "session_id": session.session_id,
            "team_id": session.team_id,
            "agent_id": session.agent_id,
        }

        # 注入记忆摘要
        if session.memory_view:
            context["memory_summary"] = self._summarize_memory(session.memory_view)

        # 合入任务状态中的关键信息
        if task_state:
            context["task_artifacts"] = task_state.get("artifacts", [])
            context["task_input"] = task_state.get("input", {})

        session.last_active = datetime.now(timezone.utc)
        return context

    def register_tool(self, session_id: str, tool_name: str, instance: Any) -> None:
        """为 Session 注册有状态工具实例"""
        session = self._sessions.get(session_id)
        if session:
            session.tool_instances[tool_name] = instance
            if session_id in self._session_tools:
                self._session_tools[session_id].add(tool_name)

    async def start_gc_loop(self, interval: int = 300) -> None:
        """启动后台 GC 循环，定期清理超时 Session"""
        self._gc_task = asyncio.create_task(self._gc_loop(interval))

    async def stop_gc_loop(self) -> None:
        """停止 GC 循环"""
        if self._gc_task:
            self._gc_task.cancel()
            self._gc_task = None

    async def _gc_loop(self, interval: int) -> None:
        """定期扫描超时 Session"""
        while True:
            try:
                await asyncio.sleep(interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session GC error: {e}")

    async def _cleanup_expired(self) -> int:
        """清理超时 Session"""
        now = datetime.now(timezone.utc)
        expired = []

        async with self._lock:
            for sid, session in self._sessions.items():
                if session.status == SessionStatus.CLOSED:
                    continue
                age = (now - session.last_active).total_seconds()
                if age > self._ttl:
                    expired.append(sid)

        for sid in expired:
            await self.close_session(sid)

        if expired:
            logger.info(f"Session GC: cleaned up {len(expired)} expired sessions")
        return len(expired)

    async def _flush_context_memory(self, session: AgentSession) -> None:
        """将 Session 上下文刷新到持久化记忆"""
        from app.services.memory_manager import MemoryManager

        memory_mgr = MemoryManager(self.db)
        for key, value in session.context.items():
            if isinstance(value, str) and value:
                await memory_mgr.save_memory(
                    level="context",
                    content=value[:500],
                    type="session_flush",
                    agent_id=uuid.UUID(session.agent_id),
                    team_id=uuid.UUID(session.team_id) if session.team_id else None,
                    session_id=session.session_id,
                    importance=0.3,
                )

    def _summarize_memory(self, memory_view: dict) -> str:
        """将四层记忆视图摘要为字符串"""
        parts = []
        for level, memories in memory_view.items():
            if isinstance(memories, list) and memories:
                count = len(memories)
                latest = memories[0].content[:100] if hasattr(memories[0], "content") else ""
                parts.append(f"{level}: {count} items, latest: {latest}")
        return "\n".join(parts) if parts else "No memories"

    def list_sessions(self, status: Optional[str] = None) -> list[dict]:
        """列出所有 Session"""
        result = []
        for s in self._sessions.values():
            if status and s.status.value != status:
                continue
            result.append({
                "session_id": s.session_id,
                "team_id": s.team_id,
                "agent_id": s.agent_id,
                "task_id": s.task_id,
                "status": s.status.value,
                "tool_count": len(s.tool_instances),
                "created_at": s.created_at.isoformat(),
                "last_active": s.last_active.isoformat(),
            })
        return result

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.status == SessionStatus.ACTIVE)


# Global session manager (lazy-initialized per request with db session)
_global_session_manager: Optional[SessionManager] = None


def get_session_manager(db: AsyncSession) -> SessionManager:
    """获取全局 SessionManager（单例，db session 注入）"""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager(db)
    else:
        _global_session_manager.db = db
    return _global_session_manager
