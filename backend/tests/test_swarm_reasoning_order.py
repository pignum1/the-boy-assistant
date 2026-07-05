"""回归测试：swarm 讨论轮必须先发 reasoning_complete 再发 agent_message。

背景：ws.py 持久化 agent_message 时会合并「当时已就绪」的 reasoning_by_agent。
若 reasoning_complete 在 agent_message 之后发出，则持久化本条消息时
reasoning_by_agent 尚未填充，刷新页面后该消息会丢失思维链。

本测试用替身替换 DB / agent_executor / agent_chat，跑一遍 swarm.run()，
断言每个 agent 的 reasoning_complete 在其 agent_message 之前发出。
"""
import asyncio
import uuid

import pytest

from app.services.collaboration.engines import swarm_engine


# ── 替身对象 ──────────────────────────────────────────────

class _FakeAgent:
    def __init__(self, name):
        self.name = name
        self.id = uuid.uuid4()


class _FakeTM:
    def __init__(self, role):
        self.role_name = role
        self.capabilities = ["code"]
        self.is_required = True


class _FakeTeam:
    def __init__(self):
        self.id = uuid.uuid4()


class _Scalars:
    def __init__(self, rows):
        self._rows = rows
    def all(self):
        return self._rows
    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows):
        self._rows = rows
    def all(self):
        return self._rows
    def scalars(self):
        return _Scalars([r[1] for r in self._rows])


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
    async def execute(self, _stmt):
        return _Result(self._rows)
    async def commit(self):
        pass


class _FakeAsyncSession:
    """`async_session()` 用作 async context manager：`async with async_session() as db`"""
    def __init__(self, rows):
        self._rows = rows
    def __call__(self):
        return self
    async def __aenter__(self):
        return _FakeDB(self._rows)
    async def __aexit__(self, *a):
        return False


class _FakeExec:
    """agent_executor 替身。讨论轮(node_key=swarm_agent)返回带 reasoning 的内容；
    执行轮(node_key=swarm_execute)返回空内容以跳过文件写入等副作用。"""
    async def execute(self, *, prompt, agent, db, session_id, team_id, node_key):
        if node_key == "swarm_execute":
            return {"content": "", "reasoning": {}, "exec_mode": ""}
        return {
            "content": f"[{agent.name}] 我的发言",
            "reasoning": {
                "thinking_steps": "我先分析了需求……",
                "model_routing": {"selected_model": "test-model"},
                "tool_calls": [],
                "exec_mode": "react",
                "iterations": 2,
            },
            "exec_mode": "react",
            "iterations": 2,
        }


class _FakeSwarmConfig:
    max_rounds = 1
    speak_strategy = "auto"


class _FakeTeamModeService:
    def __init__(self, _db):
        pass
    async def get_swarm_config(self, _team_id):
        return _FakeSwarmConfig()


async def _fake_agent_chat(**_kw):
    return {"content": "ok"}


# ── 测试 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_swarm_emits_reasoning_before_agent_message(monkeypatch):
    rows = [
        (_FakeTM("前端"), _FakeAgent("前端工程师-Agent")),
        (_FakeTM("后端"), _FakeAgent("后端工程师-Agent")),
    ]

    # run() 内部用局部 import 取这些符号；patch 源模块即可在调用时生效
    import app.core.database as db_mod
    import app.services.team_mode_service as tms_mod
    import app.services.agent_chat as chat_mod
    import app.services.collaboration.agent_executor as exec_mod

    monkeypatch.setattr(db_mod, "async_session", _FakeAsyncSession(rows))
    monkeypatch.setattr(tms_mod, "TeamModeService", _FakeTeamModeService)
    monkeypatch.setattr(chat_mod, "agent_chat", _fake_agent_chat)
    monkeypatch.setattr(exec_mod, "agent_executor", _FakeExec())

    events: list[dict] = []

    async def send_fn(data: dict):
        events.append({"type": data.get("type"), "agent": (data.get("payload") or {}).get("agent")})

    await swarm_engine.run(
        session_id=str(uuid.uuid4()),
        team=_FakeTeam(),
        user_message="随便聊聊",
        team_agents=[],
        available_roles=[],
        send_fn=send_fn,
    )

    # 过滤出 agent_message / reasoning_complete
    paired = [e for e in events if e["type"] in ("agent_message", "reasoning_complete")]

    # 每个 agent 的 reasoning_complete 必须出现在其 agent_message 之前
    seen_reasoning: set[str] = set()
    for e in paired:
        agent = e["agent"]
        assert agent, f"event missing agent: {e}"
        if e["type"] == "reasoning_complete":
            seen_reasoning.add(agent)
        elif e["type"] == "agent_message":
            assert agent in seen_reasoning, (
                f"agent_message of '{agent}' emitted before its reasoning_complete "
                f"(→ 刷新后该消息会丢失思维链)"
            )

    # 至少应有一次配对（讨论轮产生了发言）
    assert any(e["type"] == "agent_message" for e in paired), "no agent_message emitted"
