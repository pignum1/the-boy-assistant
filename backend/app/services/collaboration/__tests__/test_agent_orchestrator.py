"""Tests for M3 AgentOrchestrator."""
from app.services.collaboration.m3_agent_orchestrator import (
    check_agent_availability,
    generate_missing_agent_message,
)


class TestCheckAvailability:
    def make_agent(self, agent_id, role, status="idle"):
        return {"agent_id": agent_id, "name": f"{role}-Agent", "role": role, "status": status}

    def test_all_available(self):
        agents = [
            self.make_agent("a1", "architect"),
            self.make_agent("a2", "backend_dev"),
        ]
        available, missing = check_agent_availability(
            ["architect", "backend_dev"], agents
        )
        assert len(available) == 2
        assert len(missing) == 0

    def test_missing_role(self):
        agents = [self.make_agent("a1", "backend_dev")]
        available, missing = check_agent_availability(
            ["architect", "backend_dev"], agents
        )
        assert "architect" in missing
        assert "backend_dev" in available
        assert len(missing) == 1

    def test_busy_agent_still_counted(self):
        agents = [self.make_agent("a1", "architect", status="busy")]
        available, missing = check_agent_availability(["architect"], agents)
        # Busy agent is still returned (considered available, just busy)
        assert len(available) == 1
        assert len(missing) == 0

    def test_all_missing(self):
        agents = []
        available, missing = check_agent_availability(
            ["architect", "tester"], agents
        )
        assert len(available) == 0
        assert len(missing) == 2


class TestMissingAgentMessage:
    def test_generates_message(self):
        msg = generate_missing_agent_message(["tester", "devops"])
        assert "测试员" in msg
        assert "部署运维" in msg
        assert "邀请" in msg

    def test_empty_returns_empty(self):
        assert generate_missing_agent_message([]) == ""
