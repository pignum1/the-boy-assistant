"""Mode 3 工作流执行验证脚本

创建包含所有节点类型的测试工作流，验证执行正确性。

工作流结构:
  Start → Agent（编写代码）→ Condition（代码质量检查）
                            ├─ true  → Agent（代码优化）
                            │           └─ Validation（检查优化结果）
                            │               ├─ pass → Agent（最终输出）→ End
                            │               └─ fail (retry) → Agent（代码优化）
                            └─ false → HITL（人工审核）

执行:
  cd backend && PYTHONPATH=. python scripts/test_mode3_workflow.py
"""

import asyncio
import json
import uuid
import sys
from datetime import datetime, timezone

from app.core.database import async_session
from app.models.agent import Agent
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.services.team_mode_service import TeamModeService


TEST_WORKFLOW_ID = uuid.uuid4()
TEST_TEAM_NAME = "Mode3验证团队"
TEST_TEAM_ID = uuid.uuid4()


async def get_agents(db):
    """获取已存在的 agents。"""
    result = await db.execute(
        __import__('sqlalchemy').select(Agent).limit(10)
    )
    agents = result.scalars().all()
    agent_map = {}
    for a in agents:
        # 解析 persona 角色
        persona_name = ""
        try:
            if a.persona_id:
                from app.models.persona import Persona
                pr = await db.execute(
                    __import__('sqlalchemy').select(Persona).where(Persona.id == a.persona_id)
                )
                p = pr.scalar_one_or_none()
                if p:
                    persona_name = p.name
        except Exception:
            pass
        key = persona_name or a.name
        agent_map[key] = a
        print(f"  Agent: {a.name} ({persona_name}) id={a.id}")
    return agent_map


async def create_workflow(db, agent_map):
    """创建测试工作流：Agent → Condition → Agent | HITL → Validation → Agent → End"""
    print("\n📐 创建工作流...")

    wf = Workflow(
        id=TEST_WORKFLOW_ID,
        name="Mode3 完整性验证工作流",
        description="测试 Condition + Validation + HITL + Router 全部节点类型",
        template_type="custom",
        version=1,
        status="active",
        definition={
            "nodes": [],
            "edges": [],
        },
    )
    db.add(wf)

    # 节点定义
    node_keys = {
        "start":       "start_node",
        "coder":       "code_writer",
        "condition":   "quality_check",
        "good_path":   "code_optimizer",
        "bad_path":    "hitl_review",
        "validator":   "validate_result",
        "final":       "final_output",
        "end":         "end_node",
    }

    # (node_key, type, label, config, x, y)
    nodes_data = [
        (node_keys["start"],     "Start",     "开始",     {}, 0, 0),
        (node_keys["coder"],     "Agent",     "代码编写",   {"instruction": "请编写一个Python函数，计算两个数的最大公约数。要求：包含类型注解、文档字符串、错误处理。输出完整的代码文件 backend/app/gcd.py"}, 200, 100),
        (node_keys["condition"], "Condition", "质量检查",   {"expression": "contains:def gcd", "on_true_node_key": node_keys["good_path"], "on_false_node_key": node_keys["bad_path"]}, 400, 100),
        (node_keys["good_path"], "Agent",     "代码优化",   {"instruction": "请优化前面编写的最大公约数函数，添加单元测试代码 tests/test_gcd.py。"}, 600, 50),
        (node_keys["bad_path"],  "HITL",      "人工审核",   {"instruction": "代码质量不达标，请人工审核并给出修改意见。", "timeout": 300}, 600, 200),
        (node_keys["validator"], "Validation","优化校验",   {"validator": "llm_check", "criteria": "代码必须包含单元测试和类型注解", "on_fail": "retry", "max_retries": 2}, 800, 100),
        (node_keys["final"],    "Agent",     "最终输出",   {"instruction": "请将所有代码整合到最终输出中，并添加使用说明 README.md。"}, 1000, 100),
        (node_keys["end"],      "End",       "结束",     {}, 1200, 100),
    ]

    node_map = {}
    for nkey, ntype, nlabel, nconfig, nx, ny in nodes_data:
        nid = uuid.uuid4()
        node = WorkflowNode(
            id=nid,
            workflow_id=TEST_WORKFLOW_ID,
            type=ntype,
            label=nlabel,
            node_key=nkey,
            config=nconfig,
            position_x=nx,
            position_y=ny,
        )
        db.add(node)
        node_map[nkey] = node
        print(f"  节点: [{ntype}] {nlabel} (key={nkey})")

    await db.flush()  # 先让节点落地，边才能引用

    # 边（Forward + Validation → Reject）
    edges_data = [
        (node_keys["start"],     node_keys["coder"],     "Forward"),
        (node_keys["coder"],     node_keys["condition"], "Forward"),
        (node_keys["condition"], node_keys["good_path"], "Forward"),
        (node_keys["condition"], node_keys["bad_path"],  "Forward"),
        (node_keys["good_path"], node_keys["validator"], "Forward"),
        (node_keys["validator"], node_keys["good_path"], "Reject"),   # retry 回路
        (node_keys["validator"], node_keys["final"],     "Forward"),  # pass 前进
        (node_keys["bad_path"],  node_keys["final"],     "Forward"),  # HITL 后前进
        (node_keys["final"],     node_keys["end"],       "Forward"),
    ]
    for src_key, tgt_key, etype in edges_data:
        edge = WorkflowEdge(
            id=uuid.uuid4(),
            workflow_id=TEST_WORKFLOW_ID,
            source_id=node_map[src_key].id,
            target_id=node_map[tgt_key].id,
            type=etype,
        )
        db.add(edge)
    print(f"  Edges: {len(edges_data)} 条 (含 1 条 Reject)")

    await db.commit()
    print(f"  ✅ 工作流创建完成: id={TEST_WORKFLOW_ID}")
    return node_map, node_keys


async def create_team(db, agent_map, node_map, node_keys):
    """创建 langgraph 模式团队，绑定 agents 到 Agent 节点。"""
    print("\n👥 创建团队...")

    # 删除旧的同名团队
    from app.models.team import Team as T
    from app.models.team_mode_configs import TeamLanggraphConfig
    old = (await db.execute(
        __import__('sqlalchemy').select(T).where(T.name == TEST_TEAM_NAME)
    )).scalars().all()
    for o in old:
        await db.execute(__import__('sqlalchemy').delete(T).where(T.id == o.id))
    await db.flush()

    team = Team(
        id=TEST_TEAM_ID,
        name=TEST_TEAM_NAME,
        description="Mode 3 工作流验证团队",
        collaboration_mode="langgraph",
        status="active",
    )
    db.add(team)
    await db.flush()

    # 设置 langgraph 配置
    svc = TeamModeService(db)
    cfg = TeamLanggraphConfig(
        id=uuid.uuid4(),
        team_id=TEST_TEAM_ID,
        workflow_id=TEST_WORKFLOW_ID,
    )
    db.add(cfg)
    await db.flush()

    # 节点绑定：将 agent 绑定到 Agent 类型节点
    agents_by_role = list(agent_map.values())
    agent_bindings = [
        (node_keys["coder"],     "后端工程师",  0),  # 后端工程师-Agent
        (node_keys["good_path"], "后端工程师",  0),  # 同一个 agent
        (node_keys["final"],     "架构师",      1),  # 架构师-Agent
    ]
    for nkey, role, agent_idx in agent_bindings:
        if agent_idx < len(agents_by_role):
            await svc.set_node_binding(
                team_id=TEST_TEAM_ID,
                node_key=nkey,
                agent_id=agents_by_role[agent_idx].id,
            )
            print(f"  绑定: {nkey} -> {agents_by_role[agent_idx].name}")

    await db.commit()
    print(f"  ✅ 团队创建完成: id={TEST_TEAM_ID}")
    return team


async def verify_workflow_integrity(db):
    """验证工作流完整性：拓扑排序、循环检测、节点绑定。"""
    print("\n🔍 验证工作流完整性...")

    from app.models.workflow import WorkflowNode, WorkflowEdge
    from collections import defaultdict, deque

    nodes = (await db.execute(
        __import__('sqlalchemy').select(WorkflowNode).where(
            WorkflowNode.workflow_id == TEST_WORKFLOW_ID
        )
    )).scalars().all()
    edges = (await db.execute(
        __import__('sqlalchemy').select(WorkflowEdge).where(
            WorkflowEdge.workflow_id == TEST_WORKFLOW_ID
        )
    )).scalars().all()

    # 1. 检查节点类型完整性
    type_counts = defaultdict(int)
    for n in nodes:
        type_counts[n.type] += 1
    print(f"  节点类型分布: {dict(type_counts)}")

    # 2. 检查边类型完整性
    edge_type_counts = defaultdict(int)
    for e in edges:
        edge_type_counts[e.type] += 1
    print(f"  边类型分布: {dict(edge_type_counts)}")

    # 3. 拓扑排序（排除 Start/End，只考虑 Forward 边）
    NON_EXEC = frozenset({"start", "end"})
    exec_nodes = [n for n in nodes if n.type.lower() not in NON_EXEC]
    node_by_id = {str(n.id): n for n in exec_nodes}
    in_degree = defaultdict(int)
    adj = defaultdict(list)
    for e in edges:
        if (e.type or "").lower() != "forward":
            continue  # Reject/Escalate/Timeout/Fallback 不参与拓扑排序
        sid, tid = str(e.source_id), str(e.target_id)
        if sid in node_by_id and tid in node_by_id:
            adj[sid].append(tid)
            in_degree[tid] += 1

    q = deque([nid for nid in node_by_id if in_degree[nid] == 0])
    order = []
    while q:
        nid = q.popleft()
        order.append(nid)
        for nxt in adj[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                q.append(nxt)

    has_cycle = len(order) < len(node_by_id)
    print(f"  拓扑排序: {'❌ 有循环!' if has_cycle else '✅ 无循环'} "
          f"({len(order)}/{len(node_by_id)} 个节点)")

    # 4. 打印执行顺序
    for i, nid in enumerate(order):
        n = node_by_id[nid]
        deps = []
        for e in edges:
            if str(e.target_id) == nid and str(e.source_id) in node_by_id:
                deps.append(node_by_id[str(e.source_id)].label)
        print(f"    Level {i}: [{n.type}] {n.label} (key={n.node_key}) depends_on={deps}")

    return not has_cycle, nodes, edges, exec_nodes


async def main():
    print("=" * 60)
    print("Mode 3 工作流执行验证")
    print("=" * 60)

    async with async_session() as db:
        # Step 1: 获取 agents
        print("\n1️⃣  获取已有 Agents...")
        agent_map = await get_agents(db)
        if len(agent_map) < 3:
            print("❌ Agent 不足，需要至少 3 个 Agent")
            return
        print(f"  共 {len(agent_map)} 个 Agent 可用")

        # Step 2: 创建工作流
        node_map, node_keys = await create_workflow(db, agent_map)

        # Step 3: 创建团队 + 绑定
        team = await create_team(db, agent_map, node_map, node_keys)

        # Step 4: 验证完整性
        ok, nodes, edges, exec_nodes = await verify_workflow_integrity(db)

        if not ok:
            print("\n❌ 工作流存在循环依赖，无法执行")
            return

        print("\n" + "=" * 60)
        print("✅ 工作流结构验证通过！")
        print(f"   工作流 ID: {TEST_WORKFLOW_ID}")
        print(f"   团队 ID:   {TEST_TEAM_ID}")
        print(f"   团队名称:   {TEST_TEAM_NAME}")
        print(f"   节点数:     {len(nodes)} ({len(exec_nodes)} 个可执行)")
        print(f"   边数:       {len(edges)}")
        print(f"   节点类型:   Agent, Condition, HITL, Validation, Start, End")
        print(f"   边类型:     Forward, Reject")
        print("=" * 60)
        print("\n💡 下一步：通过 API 触发执行")
        print(f"   POST /api/v1/sessions")
        print(f"   Body: {{")
        print(f'     "team_id": "{TEST_TEAM_ID}",')
        print(f'     "message": "编写最大公约数函数"')
        print(f"   }}")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
