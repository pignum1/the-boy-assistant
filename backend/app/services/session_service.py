"""SessionService：会话持久化 CRUD + 业务逻辑

职责：
1. 创建/查询/更新/归档 Session 持久化记录
2. 会话级别的工作空间管理（默认路径 / 用户自定义）
3. 与 MemoryManager 协作查询历史消息
4. 与 WorkspaceManager 协作管理工作空间目录
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, desc, func, and_
from sqlalchemy.ext.asyncio import AsyncSession as DBAsyncSession

from app.core.config import get_settings
from app.models.session import Session
from app.models.session_task import SessionTask
from app.models.team import Team
from app.models.memory import Memory

logger = logging.getLogger(__name__)

# ws.py 保存用户消息时会附加一个纳秒时间戳标记 f"[{time.time_ns()}]" 作为持久化
# 去重 key（使每轮用户消息内容唯一，避免 get_session_messages 的按内容去重把
# 重复/配对消息合并）。该标记只用于去重，绝不能展示给用户——读取时统一剥离。
# 18 位以上数字几乎不可能是用户输入（纳秒时间戳为 18~19 位），故阈值取 18。
_DIALOG_TAG_RE = re.compile(r"\[\d{18,}\]$")


def _strip_dialog_tag(content: str | None) -> str:
    """剥离用户消息末尾的去重时间戳标记，例如 'hi[1782892302613548000]' -> 'hi'。

    仅影响展示；调用方仍以原始 content 作为去重 key。
    """
    if not content:
        return content or ""
    return _DIALOG_TAG_RE.sub("", content)


class SessionService:
    """会话 CRUD 服务"""

    def __init__(self, db: DBAsyncSession):
        self.db = db
        self._settings = get_settings()

    # ── 工作空间路径计算 ──

    def _resolve_workspace_path(self, session_id: uuid.UUID, custom_path: Optional[str] = None) -> str:
        """解析工作空间路径：用户指定 > 默认路径（自动创建目录）"""
        if custom_path:
            path = os.path.expanduser(custom_path)
        else:
            base = os.path.expanduser(self._settings.WORKSPACE_BASE_PATH)
            path = os.path.join(base, str(session_id))
        os.makedirs(path, exist_ok=True)
        return path

    # ── CRUD ──

    async def create_session(
        self,
        team_id: uuid.UUID,
        title: str = "新对话",
        workspace_path: Optional[str] = None,
        mode: str = "discussion",
    ) -> Session:
        """创建会话：写入 DB 记录 + 初始化工作空间目录"""
        session = Session(
            team_id=team_id,
            title=title or "新对话",
            mode=mode,
            workspace_path=workspace_path,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        # 初始化工作空间目录
        from app.services.workspace.manager import workspace_manager

        resolved_path = self._resolve_workspace_path(session.id, workspace_path)
        # 总是用解析后的路径创建/获取工作空间
        ws = workspace_manager.get_workspace(str(session.id))
        if ws:
            # 已有工作空间但路径不一致（用户切换了路径），先清理再重建
            if ws.path != resolved_path:
                workspace_manager.clean_workspace(str(session.id))
                workspace_manager.create_workspace(str(session.id), custom_path=resolved_path)
        else:
            workspace_manager.create_workspace(str(session.id), custom_path=resolved_path)

        logger.info(
            f"Session created: id={session.id} team={team_id} mode={mode}"
        )
        return session

    async def get_session(self, session_id: uuid.UUID) -> Optional[Session]:
        """获取单个会话"""
        return await self.db.get(Session, session_id)

    async def get_session_with_team(self, session_id: uuid.UUID) -> Optional[dict]:
        """获取会话详情（含团队名称）"""
        stmt = (
            select(Session, Team.name.label("team_name"))
            .join(Team, Session.team_id == Team.id, isouter=True)
            .where(Session.id == session_id)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if not row:
            return None
        session, team_name = row
        return self._session_to_response(session, team_name)

    async def list_sessions(
        self,
        team_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出会话（按 updated_at 降序）"""
        conditions = []
        if team_id:
            conditions.append(Session.team_id == team_id)
        if status:
            conditions.append(Session.status == status)

        from sqlalchemy import func as sqlfunc
        task_count_sub = select(
            SessionTask.session_id,
            sqlfunc.count(SessionTask.id).label('total'),
            sqlfunc.count(SessionTask.id).filter(SessionTask.status == 'done').label('done'),
        ).group_by(SessionTask.session_id).subquery()

        stmt = (
            select(Session, Team.name.label("team_name"),
                   sqlfunc.coalesce(task_count_sub.c.total, 0).label('total'),
                   sqlfunc.coalesce(task_count_sub.c.done, 0).label('done'))
            .join(Team, Session.team_id == Team.id, isouter=True)
            .join(task_count_sub, Session.id == task_count_sub.c.session_id, isouter=True)
            .order_by(desc(Session.updated_at))
            .limit(limit)
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self.db.execute(stmt)
        return [
            self._session_to_response(s, team_name, total or 0, done or 0)
            for s, team_name, total, done in result.all()
        ]

    async def update_session(
        self, session_id: uuid.UUID, **kwargs
    ) -> Optional[Session]:
        """更新会话字段"""
        session = await self.get_session(session_id)
        if not session:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(session, key):
                setattr(session, key, value)

        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def archive_session(self, session_id: uuid.UUID) -> bool:
        """归档会话（软删除）"""
        session = await self.get_session(session_id)
        if not session:
            return False
        session.status = "archived"
        session.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(f"Session archived: {session_id}")
        return True

    async def delete_session_completely(self, session_id: uuid.UUID) -> bool:
        """完全删除会话及其所有相关数据（硬删除）

        删除包括：
        - Memory 记录（对话记忆）
        - Session 自身
        """
        # 1. 删除所有相关的 Memory 记录
        try:
            from sqlalchemy import delete
            stmt = delete(Memory).where(Memory.session_id == str(session_id))
            await self.db.execute(stmt)
            logger.info(f"Deleted memories for session: {session_id}")
        except Exception as e:
            logger.warning(f"Failed to delete memories for session {session_id}: {e}")

        # 2. 删除 Session 记录
        session = await self.get_session(session_id)
        if not session:
            return False

        try:
            await self.db.delete(session)
            await self.db.commit()
            logger.info(f"Session completely deleted: {session_id}")

            # 3. 清理工作空间目录
            from app.services.workspace.manager import workspace_manager
            workspace_manager.clean_workspace(str(session_id))

            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            await self.db.rollback()
            return False

    async def increment_message_count(self, session_id: uuid.UUID) -> None:
        """原子递增消息计数"""
        session = await self.get_session(session_id)
        if session:
            session.message_count = (session.message_count or 0) + 1
            session.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

    # ── 历史消息查询 ──

    async def get_session_messages(
        self,
        session_id: uuid.UUID,
        limit: int = 100,
    ) -> list[dict]:
        """获取会话的历史消息（从 Memory 表 level=context 查询）

        解析 save_dialog_memory 格式："用户: xxx\n助手: yyy" → 两条独立消息
        """
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.session_id == str(session_id),
                    Memory.level == "context",
                )
            )
            .order_by(Memory.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        messages = []
        seen_user_contents = set()  # 去重用户消息
        for m in memories:
            content = m.content or ""
            # 解析组合格式 "用户: ...\n助手: ..."
            if "\n助手: " in content:
                parts = content.split("\n助手: ", 1)
                user_part = parts[0]
                assistant_part = parts[1] if len(parts) > 1 else ""

                # 用户消息（支持 "用户: " 和 "用户[N]: " 两种格式）
                import re as _re
                user_match = _re.match(r"用户(?:\[\d+\])?: ", user_part)
                if user_match:
                    user_content = user_part[user_match.end():]
                    # 跳过内部系统标记（worker / resume 等场景占位的伪 user 消息）
                    is_internal = (
                        user_content.startswith("[Worker:")
                        or user_content.startswith("[System")
                        or user_content.startswith("[Internal")
                    )
                    if not is_internal and user_content not in seen_user_contents:
                        seen_user_contents.add(user_content)
                        # 剥离去重时间戳标记后再展示（去重仍用原始 user_content）
                        display_content = _strip_dialog_tag(user_content)
                        messages.append({
                            "id": f"{m.id}_user",
                            "role": "user",
                            "content": display_content,
                            "agent_name": "我",
                            "timestamp": m.created_at.isoformat() if m.created_at else "",
                        })
                # 助手消息
                if assistant_part:
                    # 提取 agent_name（从 metadata 中获取，或从内容推断）
                    meta = m.metadata_ or {}
                    agent_name = meta.get("agent") if isinstance(meta, dict) else None
                    messages.append({
                        "id": f"{m.id}_assistant",
                        "role": "assistant",
                        "content": assistant_part,
                        "agent_name": agent_name,
                        "timestamp": m.created_at.isoformat() if m.created_at else "",
                        "metadata": meta,
                    })
            else:
                # 简单格式：根据 created_by 判断角色
                role = "user" if m.created_by == "user" else "system"
                if role == "user":
                    if content in seen_user_contents:
                        continue  # 跳过重复的简单格式用户消息
                    seen_user_contents.add(content)
                meta = m.metadata_ or {}
                # 去重以原始 content（含标记）为准；展示时剥离标记
                display_content = _strip_dialog_tag(content)
                messages.append({
                    "id": str(m.id),
                    "role": role,
                    "content": display_content,
                    "agent_name": "我" if role == "user" else None,
                    "timestamp": m.created_at.isoformat() if m.created_at else "",
                    "metadata": meta if isinstance(meta, dict) else {},
                })

        return messages

    # ── 工作空间查询 ──

    async def get_workspace_info(self, session_id: uuid.UUID) -> Optional[dict]:
        """获取会话的工作空间信息"""
        from app.services.workspace.manager import workspace_manager

        session = await self.get_session(session_id)
        if not session:
            return None

        ws = workspace_manager.get_or_create(str(session_id))
        resolved_path = self._resolve_workspace_path(session_id, session.workspace_path)

        # 统计文件
        file_count = 0
        total_size = 0
        if os.path.isdir(resolved_path):
            for root, _, files in os.walk(resolved_path):
                file_count += len(files)
                for f in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass

        return {
            "session_id": str(session_id),
            "path": resolved_path,
            "status": ws.status.value if ws else "active",
            "created_at": ws.created_at if ws else "",
            "last_accessed": ws.last_accessed if ws else "",
            "file_count": file_count,
            "total_size_bytes": total_size,
        }

    # ── 上下文窗口查询 ──

    async def get_context_window(
        self,
        session_id: uuid.UUID,
        limit: int = 200,
    ) -> dict:
        """获取会话的完整上下文窗口信息

        返回 LLM 视角的完整上下文，包括：
        - 会话元信息
        - 所有消息（含完整 reasoning metadata）
        - 系统提示词（从团队 Agent 的 Persona 中获取）
        - 汇总统计（token 用量、记忆注入次数、RAG 块数）
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        # 1. 获取所有消息（含完整 metadata）
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.session_id == str(session_id),
                    Memory.level == "context",
                )
            )
            .order_by(Memory.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        # 2. 解析消息
        messages = []
        total_tokens = 0
        total_memories_injected = 0
        total_rag_chunks = 0
        total_tool_calls = 0

        for m in memories:
            content = m.content or ""
            meta = m.metadata_ or {}

            # 提取统计信息
            if isinstance(meta, dict):
                ctx = meta.get("context_used", {})
                if isinstance(ctx, dict):
                    total_tokens += ctx.get("total_tokens", 0) or 0
                    total_memories_injected += ctx.get("memories_injected", 0) or 0
                    total_rag_chunks += ctx.get("rag_chunks", 0) or 0
                tools = meta.get("tool_calls", [])
                if isinstance(tools, list):
                    total_tool_calls += len(tools)

            # 解析组合格式 "用户: ...\n助手: ..."
            if "\n助手: " in content:
                parts = content.split("\n助手: ", 1)
                user_part = parts[0]
                assistant_part = parts[1] if len(parts) > 1 else ""

                import re as _re
                user_match = _re.match(r"用户(?:\[\d+\])?: ", user_part)
                if user_match:
                    user_content = user_part[user_match.end():]
                    # 剥离去重时间戳标记后再展示
                    display_content = _strip_dialog_tag(user_content)
                    messages.append({
                        "id": f"{m.id}_user",
                        "role": "user",
                        "content": display_content,
                        "agent_name": "我",
                        "timestamp": m.created_at.isoformat() if m.created_at else "",
                        "metadata": None,
                    })
                if assistant_part:
                    messages.append({
                        "id": f"{m.id}_assistant",
                        "role": "assistant",
                        "content": assistant_part,
                        "agent_name": meta.get("agent") if isinstance(meta, dict) else None,
                        "timestamp": m.created_at.isoformat() if m.created_at else "",
                        "metadata": meta if isinstance(meta, dict) else {},
                    })
            else:
                messages.append({
                    "id": str(m.id),
                    "role": "system" if m.type == "system" else "assistant",
                    "content": _strip_dialog_tag(content),
                    "agent_name": meta.get("agent") if isinstance(meta, dict) else None,
                    "timestamp": m.created_at.isoformat() if m.created_at else "",
                    "metadata": meta if isinstance(meta, dict) else {},
                })

        # 3. 获取团队 Agent 的系统提示词
        system_prompts = await self._get_team_system_prompts(session.team_id)

        # 4. 汇总统计
        stats = {
            "message_count": len(messages),
            "memory_count": len(memories),
            "total_tokens_estimate": total_tokens,
            "total_memories_injected": total_memories_injected,
            "total_rag_chunks": total_rag_chunks,
            "total_tool_calls": total_tool_calls,
        }

        return {
            "session": {
                "id": str(session.id),
                "title": session.title,
                "mode": session.mode,
                "status": session.status,
            },
            "stats": stats,
            "system_prompts": system_prompts,
            "messages": messages,
        }

    async def _get_team_system_prompts(self, team_id: uuid.UUID) -> list[dict]:
        """获取团队所有 Agent 的系统提示词"""
        from app.models.team_member import TeamMember
        from app.models.agent import Agent

        result = await self.db.execute(
            select(TeamMember).where(TeamMember.team_id == team_id)
        )
        members = result.scalars().all()

        prompts = []
        from app.services.agent_factory import build_system_prompt
        seen_agents = set()

        for member in members:
            if member.agent_id in seen_agents:
                continue
            seen_agents.add(member.agent_id)

            agent = await self.db.get(Agent, member.agent_id)
            if not agent:
                continue

            try:
                system_prompt = await build_system_prompt(
                    self.db, agent, user_message=""
                )
                prompts.append({
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "role_name": member.role_name,
                    "system_prompt": system_prompt,
                })
            except Exception:
                # 如果获取提示词失败，跳过该 Agent
                pass

        return prompts

    # ── 辅助方法 ──

    def _session_to_response(self, session: Session, team_name: Optional[str] = None, task_total: int = 0, task_completed: int = 0) -> dict:
        """将 ORM 对象转为响应字典"""
        return {
            "id": str(session.id),
            "team_id": str(session.team_id),
            "title": session.title,
            "status": session.status,
            "mode": session.mode,
            "workspace_path": session.workspace_path,
            "message_count": session.message_count or 0,
            "task_total": task_total,
            "task_completed": task_completed,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
            "team_name": team_name,
        }
