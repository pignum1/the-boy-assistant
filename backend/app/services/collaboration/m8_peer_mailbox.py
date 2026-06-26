"""M8: Peer Mailbox — direct agent-to-agent communication.

PRINCIPLE: PEER-TO-PEER
- Workers can challenge each other's approaches
- Workers can share useful findings
- Workers can ask each other questions
- NOT just hierarchical reporting to Supervisor

Message types:
- challenge: 质疑另一个 Agent 的方案
- share: 分享有用的发现
- question: 向另一个 Agent 提问
- response: 回复消息

Lifecycle: messages are created during M6 execution,
consumed by the receiving worker via M5 context injection.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import uuid


MessageType = Literal["challenge", "share", "question", "response"]


@dataclass
class Message:
    """A peer-to-peer message between agents."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: str = ""          # agent_id or "__all__"
    msg_type: MessageType = "share"
    content: str = ""
    references: list[str] = field(default_factory=list)  # task_ids or artifact_ids
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    read: bool = False


class PeerMailbox:
    """In-memory peer-to-peer message system.

    For production, messages should be persisted to DB.
    This implementation uses in-memory storage per session.
    """

    def __init__(self):
        self._messages: dict[str, list[Message]] = {}  # session_id → messages

    def send(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType,
        content: str,
        references: list[str] | None = None,
    ) -> str:
        """Send a message. Returns message_id."""
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=msg_type,
            content=content,
            references=references or [],
        )

        if session_id not in self._messages:
            self._messages[session_id] = []

        self._messages[session_id].append(msg)
        return msg.id

    def receive(
        self,
        session_id: str,
        agent_name: str,
        unread_only: bool = True,
    ) -> list[Message]:
        """Get messages for an agent.

        Matches messages where to_agent == agent_name or to_agent == "__all__".
        """
        if session_id not in self._messages:
            return []

        result = []
        for msg in self._messages[session_id]:
            if msg.to_agent in (agent_name, "__all__"):
                if unread_only and msg.read:
                    continue
                result.append(msg)
                msg.read = True

        return result

    def to_context_list(self, messages: list[Message]) -> list[dict]:
        """Convert Message objects to dict list for M5 context injection."""
        return [
            {
                "type": msg.msg_type,
                "from": msg.from_agent,
                "to": msg.to_agent,
                "content": msg.content,
                "references": msg.references,
            }
            for msg in messages
        ]

    def format_for_context(
        self,
        session_id: str,
        agent_name: str,
    ) -> list[dict]:
        """Get unread messages formatted for M5 context injection.

        Called by M6 before building each worker's context.
        """
        messages = self.receive(session_id, agent_name)
        return self.to_context_list(messages)

    def clear(self, session_id: str) -> None:
        """Clear all messages for a session."""
        self._messages.pop(session_id, None)


# ── Module-level singleton ──

peer_mailbox = PeerMailbox()
