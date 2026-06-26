"""Mode 3 工作流执行集成测试

直接调用 langgraph_engine.run()，验证完整执行流程。
"""

import asyncio
import json
import uuid
from datetime import datetime
from collections import defaultdict, deque

from app.core.database import async_session
from app.models.team import Team
from app.models.agent import Agent
from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
from app.models.team_mode_configs import TeamLanggraphConfig
from app.services.team_mode_service import TeamModeService
from app.services.collaboration.engines import langgraph_engine


async def main():
    # 1. 加载已创建的测试数据
    async with async_session() as db:
        # 查找团队
        from sqlalchemy import select as sl
        teams = (await db.execute(
            sl(Team).where(Team.name == "Mode3验证团队").order_by(Team.created_at.desc()).limit(1)
        )).scalars().all()
        if not teams:
            print("❌ 未找到测试团队，请先运行 test_mode3_workflow.py")
            return
        team = teams[0]
        print(f"Team: {team.name} mode={team.collaboration_mode}")

        # 查找工作流
        cfg = await TeamModeService(db).get_langgraph_config(team.id)
        if not cfg:
            print("❌ 未找到 langgraph 配置")
            return
        wf = await db.get(Workflow, cfg.workflow_id)
        if not wf:
            print("❌ 工作流不存在")
            return
        print(f"Workflow: {wf.name} nodes={len(wf.definition.get('nodes', []))}")

        # 加载 agents
        agents = (await db.execute(sl(Agent))).scalars().all()
        agent_list = [{"id": str(a.id), "name": a.name} for a in agents]
        print(f"Agents: {len(agent_list)}")

        # 事件收集器
        events = []

        async def collect_events(event: dict):
            etype = event.get("type", "?")
            payload = event.get("payload", {})
            if etype == "task_status":
                tid = payload.get("task_id", "")[:8]
                status = payload.get("status", "?")
                error = payload.get("error", "")
                print(f"  📌 task_status: {tid} → {status}" + (f" ({error})" if error else ""))
            elif etype == "agent_message":
                agent = payload.get("agent", "?")
                content_len = len(payload.get("content", ""))
                print(f"  💬 agent_message: {agent} ({content_len} chars)")
            elif etype == "files_changed":
                files = payload.get("files", [])
                for f in files:
                    print(f"  📁 file: {f['name']} ({f['status']})")
            elif etype == "error":
                print(f"  ❌ error: {payload.get('message', '?')}")
            elif etype in ("routing_decision", "task_dag", "message_complete",
                           "request_clarification", "reasoning_complete"):
                pass  # skip verbose events
            else:
                print(f"  ❓ {etype}: {json.dumps(payload, ensure_ascii=False)[:100]}")
            events.append(event)

        print("\n🚀 开始执行工作流...")
        print("=" * 50)

        session_id = str(uuid.uuid4())
        try:
            await langgraph_engine.run(
                session_id=session_id,
                team=team,
                user_message="请编写一个计算最大公约数的Python函数，包含类型注解和错误处理。",
                team_agents=agent_list,
                available_roles=[],
                send_fn=collect_events,
            )
        except Exception as e:
            print(f"\n❌ 执行异常: {e}")
            import traceback
            traceback.print_exc()

        print("=" * 50)

        # 统计结果
        task_events = [e for e in events if e["type"] == "task_status"]
        done = [e for e in task_events if e["payload"].get("status") == "done"]
        failed = [e for e in task_events if e["payload"].get("status") == "failed"]
        skipped = [e for e in task_events if e["payload"].get("status") == "skipped"]

        print(f"\n📊 执行统计:")
        print(f"   总事件数: {len(events)}")
        print(f"   完成节点: {len(done)}")
        print(f"   失败节点: {len(failed)}")
        print(f"   跳过节点: {len(skipped)}")

        if done:
            print(f"\n✅ 成功完成的节点:")
            for e in done:
                tid = e["payload"].get("task_id", "")[:8]
                dur = e["payload"].get("duration", 0)
                err = e["payload"].get("error", "")
                print(f"   - {tid} ({dur}ms)" + (f" {err}" if err else ""))

        if failed:
            print(f"\n❌ 失败的节点:")
            for e in failed:
                tid = e["payload"].get("task_id", "")[:8]
                err = e["payload"].get("error", "")
                print(f"   - {tid}: {err[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
