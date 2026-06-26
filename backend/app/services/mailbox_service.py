"""Mailbox Service：Agent 间直接通信系统

对标 Claude Code Agent Team 的 Mailbox。

支持 5 种通信模式:
1. 直接消息: Agent A → Agent B (@AgentName)
2. 广播: Agent → @all
3. 质疑: Agent 挑战另一个 Agent 的假设
4. 辩论: 多 Agent 讨论线程
5. 求助: Agent → @help (任意可用 Agent)
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MailboxMessageType(str, Enum):
    DIRECT = "direct"       # @AgentName 直接消息
    BROADCAST = "broadcast" # @all 广播
    CHALLENGE = "challenge" # 质疑假设
    DEBATE = "debate"       # 辩论参与
    HELP = "help"           # @help 求助


@dataclass
class MailboxMessage:
    """Mailbox 消息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    from_agent_id: str = ""
    from_agent_name: str = ""
    to_agent_id: str = ""       # 空字符串 = 广播
    to_agent_name: str = ""     # 空字符串 = 广播
    message_type: MailboxMessageType = MailboxMessageType.DIRECT
    content: str = ""
    thread_id: Optional[str] = None  # 辩论线程 ID
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MailboxService:
    """Mailbox 路由服务

    职责:
    1. 解析 Agent 回复中的 @mention 模式
    2. 路由消息到目标 Agent 的上下文
    3. 管理辩论线程
    4. 格式化为 DiscussionEngine 事件
    """

    def __init__(self):
        # session_id -> list[MailboxMessage]
        self._messages: dict[str, list[MailboxMessage]] = {}
        # thread_id -> list[MailboxMessage]
        self._threads: dict[str, list[MailboxMessage]] = {}
        # session_id -> set[agent_id] (被 @ 但未回复的 agent)
        self._pending_mentions: dict[str, set[str]] = {}

    def detect_mentions(self, content: str) -> list[tuple[str, MailboxMessageType, str]]:
        """从 Agent 回复中检测 @mention 模式

        Returns:
            list of (target_name, message_type, extracted_content)
        """
        mentions = []
        import re

        # @AgentName: 直接消息
        direct_pattern = r'@([^\s,，。！？!?]+)'
        matches = re.findall(direct_pattern, content)
        for match in matches:
            if match.lower() == 'all':
                mentions.append(("all", MailboxMessageType.BROADCAST, content))
            elif match.lower() == 'help':
                mentions.append(("help", MailboxMessageType.HELP, content))
            elif match.lower() in ('challenge', '质疑', 'question'):
                mentions.append((match, MailboxMessageType.CHALLENGE, content))
            else:
                mentions.append((match, MailboxMessageType.DIRECT, content))

        return mentions

    def send(
        self,
        session_id: str,
        from_agent_id: str,
        from_agent_name: str,
        to_agent_id: str,
        to_agent_name: str,
        content: str,
        message_type: MailboxMessageType = MailboxMessageType.DIRECT,
        thread_id: Optional[str] = None,
    ) -> MailboxMessage:
        """发送 Mailbox 消息"""
        msg = MailboxMessage(
            session_id=session_id,
            from_agent_id=from_agent_id,
            from_agent_name=from_agent_name,
            to_agent_id=to_agent_id,
            to_agent_name=to_agent_name,
            message_type=message_type,
            content=content,
            thread_id=thread_id,
        )

        # Store in session messages
        if session_id not in self._messages:
            self._messages[session_id] = []
        self._messages[session_id].append(msg)

        # Store in thread if applicable
        if thread_id:
            if thread_id not in self._threads:
                self._threads[thread_id] = []
            self._threads[thread_id].append(msg)

        # Track pending mentions
        if to_agent_id and to_agent_id != from_agent_id:
            if session_id not in self._pending_mentions:
                self._pending_mentions[session_id] = set()
            self._pending_mentions[session_id].add(to_agent_id)

        logger.info(f"Mailbox: {from_agent_name} → {to_agent_name or 'all'} [{message_type.value}]")
        return msg

    def get_pending_mentions(self, session_id: str, agent_id: str) -> list[MailboxMessage]:
        """获取某个 Agent 的未读消息"""
        if session_id not in self._messages:
            return []
        pending = [
            m for m in self._messages[session_id]
            if m.to_agent_id == agent_id or (m.message_type == MailboxMessageType.BROADCAST and m.from_agent_id != agent_id)
        ]
        return pending[-10:]  # Last 10 pending

    def mark_read(self, session_id: str, agent_id: str):
        """标记消息已读"""
        if session_id in self._pending_mentions:
            self._pending_mentions[session_id].discard(agent_id)

    def get_recent(self, session_id: str, limit: int = 50) -> list[MailboxMessage]:
        """获取会话的最近消息"""
        if session_id not in self._messages:
            return []
        return self._messages[session_id][-limit:]

    def get_thread(self, thread_id: str) -> list[MailboxMessage]:
        """获取辩论线程"""
        return self._threads.get(thread_id, [])

    def format_for_agent_context(self, session_id: str, agent_id: str) -> str:
        """格式化为 Agent 上下文提示（注入到 system prompt）"""
        pending = self.get_pending_mentions(session_id, agent_id)
        if not pending:
            return ""

        lines = ["\n## 📬 Mailbox - 待处理消息\n"]
        for m in pending:
            type_icon = {
                "direct": "💬",
                "broadcast": "📢",
                "challenge": "⚡",
                "debate": "🗣️",
                "help": "🆘",
            }.get(m.message_type.value, "💬")

            lines.append(
                f"{type_icon} **{m.from_agent_name}** → {m.to_agent_name or '@all'}: "
                f"{m.content[:200]}"
            )
        return "\n".join(lines)

    def clear_session(self, session_id: str):
        """清理会话消息"""
        self._messages.pop(session_id, None)
        self._pending_mentions.pop(session_id, None)


# Global singleton
mailbox_service = MailboxService()
