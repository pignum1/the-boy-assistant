"""Tests for M8 PeerMailbox — agent-to-agent communication."""

import pytest
from app.services.collaboration.m8_peer_mailbox import PeerMailbox


class TestPeerMailbox:
    """Verify peer-to-peer messaging between agents."""

    def setup_method(self):
        self.mailbox = PeerMailbox()

    def test_send_direct_message(self):
        msg_id = self.mailbox.send(
            session_id="s1",
            from_agent="后端工程师",
            to_agent="架构师",
            msg_type="challenge",
            content="users表缺少email UNIQUE约束",
        )
        assert msg_id is not None

        msgs = self.mailbox.receive("s1", "架构师")
        assert len(msgs) == 1
        assert msgs[0].from_agent == "后端工程师"
        assert msgs[0].msg_type == "challenge"
        assert "UNIQUE" in msgs[0].content

    def test_broadcast_to_all(self):
        self.mailbox.send(
            session_id="s1",
            from_agent="架构师",
            to_agent="__all__",
            msg_type="share",
            content="DB设计完成，所有表结构在DB_DESIGN.md",
        )

        # Everyone should receive it (use unread_only=False for broadcast)
        for agent in ["后端工程师", "前端工程师", "测试员"]:
            msgs = self.mailbox.receive("s1", agent, unread_only=False)
            assert len(msgs) == 1, f"Agent {agent} should receive broadcast"
            assert msgs[0].from_agent == "架构师"

    def test_unread_filter(self):
        self.mailbox.send("s1", "A", "B", "share", "msg1")
        self.mailbox.send("s1", "C", "B", "share", "msg2")

        # First receive — both unread
        msgs = self.mailbox.receive("s1", "B", unread_only=True)
        assert len(msgs) == 2

        # Second receive — both now read
        msgs = self.mailbox.receive("s1", "B", unread_only=True)
        assert len(msgs) == 0

    def test_message_types(self):
        for msg_type in ["challenge", "share", "question", "response"]:
            self.mailbox.send("s1", "A", "B", msg_type, f"test {msg_type}")

        msgs = self.mailbox.receive("s1", "B")
        assert len(msgs) == 4
        types = {m.msg_type for m in msgs}
        assert types == {"challenge", "share", "question", "response"}

    def test_format_for_context(self):
        self.mailbox.send("s1", "后端", "前端", "challenge", "API路径不对")
        self.mailbox.send("s1", "测试员", "__all__", "share", "测试完成")

        formatted = self.mailbox.format_for_context("s1", "前端")

        # Returns list[dict] for M5 context injection
        assert isinstance(formatted, list)
        assert len(formatted) >= 1
        assert any(msg["from"] == "后端" for msg in formatted)
        assert any("API路径不对" in msg["content"] for msg in formatted)

    def test_session_isolation(self):
        self.mailbox.send("s1", "A", "B", "share", "s1 message")
        self.mailbox.send("s2", "A", "B", "share", "s2 message")

        s1_msgs = self.mailbox.receive("s1", "B")
        s2_msgs = self.mailbox.receive("s2", "B")

        assert len(s1_msgs) == 1
        assert len(s2_msgs) == 1
        assert s1_msgs[0].content != s2_msgs[0].content

    def test_clear_removes_session_messages(self):
        self.mailbox.send("s1", "A", "B", "share", "test")
        assert len(self.mailbox.receive("s1", "B")) == 1

        self.mailbox.clear("s1")
        assert len(self.mailbox.receive("s1", "B")) == 0

    def test_message_with_references(self):
        self.mailbox.send(
            "s1", "后端", "架构师", "challenge",
            "需要加索引",
            references=["task_1", "DB_DESIGN.md"],
        )

        msgs = self.mailbox.receive("s1", "架构师")
        assert len(msgs[0].references) == 2
        assert "task_1" in msgs[0].references
