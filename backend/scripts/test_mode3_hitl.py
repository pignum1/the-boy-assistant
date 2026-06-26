"""Mode 3 HITL 暂停/恢复 + Condition false 分支验证"""

import asyncio, uuid, json
from collections import defaultdict, deque
from sqlalchemy import select

from app.core.database import async_session
from app.models.agent import Agent
from app.models.team import Team
from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.team_mode_configs import TeamLanggraphConfig
from app.services.team_mode_service import TeamModeService
from app.services.collaboration.engines import langgraph_engine

WF_ID = uuid.uuid4()
TEAM_ID = uuid.uuid4()


async def setup(db):
    """创建测试工作流：Condition 必定走 false → HITL → resume → 继续"""
    wf = Workflow(id=WF_ID, name="HITL验证工作流", template_type="custom", version=1, status="active")
    db.add(wf)

    nkeys = {"start": "s", "coder": "c1", "cond": "check", "hitl": "h1", "final": "c2", "end": "e"}
    nodes = [
        (nkeys["start"], "Start", "开始", 0, 0),
        (nkeys["coder"], "Agent", "代码编写",
         {"instruction": "写一个简单的Python hello world函数到 backend/app/hello.py。"}, 200, 100),
        (nkeys["cond"], "Condition", "检查结果",
         {"expression": "contains:MISSING_FUNCTION_NAME", "on_true_node_key": nkeys["final"], "on_false_node_key": nkeys["hitl"]}, 400, 100),
        (nkeys["hitl"], "HITL", "人工审核",
         {"instruction": "代码质量需要人工审核，请检查并批准或拒绝。", "timeout": 120}, 600, 100),
        (nkeys["final"], "Agent", "最终输出",
         {"instruction": "整理所有产出，输出到 README.md。"}, 800, 100),
        (nkeys["end"], "End", "结束", 1000, 100),
    ]
    node_map = {}
    for nk, nt, nl, nx, ny in nodes:
        cfg = nodes[3][3] if isinstance(nodes[3][3], dict) else {}  # HITL config
        ncfg = (nodes[3][3]) if nk == nkeys["hitl"] else (nodes[2][3] if nk == nkeys["cond"] else (nodes[1][3] if nk in (nkeys["coder"], nkeys["final"]) else {}))
        # Actually just use explicit config
        nid = uuid.uuid4()
        ncfg = {}
        if nk == nkeys["coder"]:
            ncfg = {"instruction": "写一个简单的Python hello world函数到 backend/app/hello.py。"}
        elif nk == nkeys["cond"]:
            ncfg = {"expression": "contains:MISSING_FUNCTION_NAME", "on_true_node_key": nkeys["final"], "on_false_node_key": nkeys["hitl"]}
        elif nk == nkeys["hitl"]:
            ncfg = {"instruction": "代码质量需要人工审核，请检查并批准或拒绝。", "timeout": 120}
        elif nk == nkeys["final"]:
            ncfg = {"instruction": "整理所有产出，输出到 README.md。"}
        node = WorkflowNode(id=nid, workflow_id=WF_ID, type=nt, label=nl, node_key=nk,
                           config=ncfg, position_x=nx, position_y=ny)
        db.add(node)
        node_map[nk] = node
    await db.flush()

    edges = [
        (nkeys["start"], nkeys["coder"], "Forward"),
        (nkeys["coder"], nkeys["cond"], "Forward"),
        (nkeys["cond"], nkeys["final"], "Forward"),   # true path
        (nkeys["cond"], nkeys["hitl"], "Forward"),    # false path
        (nkeys["hitl"], nkeys["final"], "Forward"),
        (nkeys["final"], nkeys["end"], "Forward"),
    ]
    for s, t, et in edges:
        e = WorkflowEdge(id=uuid.uuid4(), workflow_id=WF_ID,
                         source_id=node_map[s].id, target_id=node_map[t].id, type=et)
        db.add(e)
    await db.flush()

    # Team
    team = Team(id=TEAM_ID, name="HITL验证团队", collaboration_mode="langgraph", status="active")
    db.add(team)
    cfg = TeamLanggraphConfig(id=uuid.uuid4(), team_id=TEAM_ID, workflow_id=WF_ID)
    db.add(cfg)
    await db.flush()

    # Bind agents (use first 2 agents)
    agents = (await db.execute(select(Agent).limit(2))).scalars().all()
    svc = TeamModeService(db)
    for nk, ag in [(nkeys["coder"], agents[0]), (nkeys["final"], agents[1])]:
        await svc.set_node_binding(team_id=TEAM_ID, node_key=nk, agent_id=ag.id)
    await db.commit()

    print(f"✅ 工作流创建完成: {len(nodes)} 节点, {len(edges)} 边")
    print(f"   Condition: contains:MISSING_FUNCTION_NAME → 必定走 false → HITL")
    return team, agents


async def test_run_and_resume(team, agents):
    """运行工作流，验证 HITL 暂停 → resume。"""
    session_id = str(uuid.uuid4())
    events = []

    async def collect(event):
        etype = event.get("type", "?")
        p = event.get("payload", {})
        if etype == "task_status":
            tid = p.get("task_id", "")[:8]
            print(f"  📌 {tid} → {p.get('status')} {p.get('error', '')}")
        elif etype == "agent_message":
            print(f"  💬 {p.get('agent')} ({len(p.get('content', ''))} chars)")
        elif etype == "request_clarification":
            print(f"  ⏸️  HITL暂停: {p.get('label')} - {p.get('message', '')[:80]}")
        elif etype == "message_complete":
            print(f"  ✅ {p.get('message', '')}")
        events.append(event)

    agent_list = [{"id": str(a.id), "name": a.name} for a in agents]

    print("\n🚀 第一阶段：执行直到 HITL 暂停...")
    await langgraph_engine.run(
        session_id=session_id, team=team,
        user_message="写一个Python hello world函数",
        team_agents=agent_list, available_roles=[],
        send_fn=collect,
    )

    # 检查是否暂停
    paused = langgraph_engine.has_paused(session_id)
    print(f"\n   HITL paused: {paused}")

    if paused:
        print("\n▶️ 第二阶段：模拟人工输入并 resume...")
        user_input = {"content": "人工审核通过：代码符合要求，可以继续。"}
        await langgraph_engine.resume(session_id, user_input, collect)
        paused2 = langgraph_engine.has_paused(session_id)
        print(f"\n   再次暂停: {paused2}")

    # 统计
    done = [e for e in events if e["type"] == "task_status" and e["payload"].get("status") == "done"]
    failed = [e for e in events if e["type"] == "task_status" and e["payload"].get("status") == "failed"]
    skipped = [e for e in events if e["type"] == "task_status" and e["payload"].get("status") == "skipped"]
    hitls = [e for e in events if e["type"] == "request_clarification"]

    print(f"\n📊 结果: {len(done)} done, {len(failed)} failed, {len(skipped)} skipped, {len(hitls)} HITL pauses")
    return len(done) >= 2 and len(hitls) >= 1


async def main():
    async with async_session() as db:
        team, agents = await setup(db)
    success = await test_run_and_resume(team, agents)
    if success:
        print("\n✅ HITL 暂停/恢复 + Condition false 分支验证通过！")
    else:
        print("\n❌ 验证失败")


if __name__ == "__main__":
    asyncio.run(main())
