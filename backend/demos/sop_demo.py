"""SOP Engine CLI Demo — 完整演示 SOP 任务启动 / HITL 暂停 / 恢复"""

import asyncio
import httpx
import sys
import json
import time

BASE = "http://localhost:8000/api/v1"


def pp(data):
    """Pretty print JSON"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def find_or_create_team(client: httpx.AsyncClient) -> str:
    """Get first team or create one"""
    r = await client.get(f"{BASE}/teams")
    teams = r.json()
    if teams:
        return teams[0]["id"]

    # Create team
    r = await client.post(f"{BASE}/teams", json={
        "name": "DemoTeam",
        "description": "SOP演示团队",
        "mode": "supervisor",
        "exec_mode": "sop",
    })
    team = r.json()
    team_id = team["id"]
    print(f"  Created team: {team_id}")

    # Add architect
    agents_r = await client.get(f"{BASE}/agents")
    agents = agents_r.json()
    for a in agents:
        if "architect" in a["name"].lower():
            await client.post(f"{BASE}/teams/{team_id}/members",
                              json={"agent_id": a["id"], "role_slot": "architect"})
            print(f"  Added {a['name']} as architect")
        elif "coder" in a["name"].lower():
            await client.post(f"{BASE}/teams/{team_id}/members",
                              json={"agent_id": a["id"], "role_slot": "coder"})
            print(f"  Added {a['name']} as coder")

    return team_id


async def find_or_create_sop(client: httpx.AsyncClient, team_id: str) -> str:
    """Get first SOP or create the full dev SOP"""
    r = await client.get(f"{BASE}/sops")
    sops = r.json()
    for s in sops:
        if "完整" in s["name"]:
            return s["id"]

    r = await client.post(f"{BASE}/sops", json={
        "team_id": team_id,
        "name": "完整开发流程",
        "description": "架构设计 → 人工确认 → 代码实现 → 验证",
        "nodes": [
            {"id": "n1", "type": "agent_action", "role_slot": "architect"},
            {"id": "n2", "type": "hitl", "message": "请确认架构方案",
             "config": {"timeout": 300, "require_human": True}},
            {"id": "n3", "type": "agent_action", "role_slot": "coder"},
            {"id": "n4", "type": "validation", "checks": ["lint"], "pass_threshold": 80},
            {"id": "n5", "type": "end"},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3", "condition": "hitl_result == approve"},
            {"from": "n2", "to": "n1", "condition": "hitl_result == reject"},
            {"from": "n3", "to": "n4"},
            {"from": "n4", "to": "n5", "condition": "validations.passed"},
            {"from": "n4", "to": "n3", "condition": "not validations.passed"},
        ],
    })
    sop = r.json()
    print(f"  Created SOP: {sop['id']}")
    return sop["id"]


async def demo_auto_approve(client: httpx.AsyncClient, team_id: str, sop_id: str):
    """Demo 1: Auto-approve mode — full pipeline without human"""
    print("\n" + "=" * 60)
    print("Demo 1: Auto-approve mode (auto_approve_hitl=true)")
    print("=" * 60)

    t0 = time.time()
    r = await client.post(f"{BASE}/tasks", json={
        "sop_id": sop_id,
        "team_id": team_id,
        "input": {"requirements": "实现一个简单的计算器类，支持加减乘除"},
        "auto_approve_hitl": True,
    }, timeout=300)
    task = r.json()
    elapsed = time.time() - t0

    print(f"\nTask: {task['id'][:8]}... | Status: {task['status']} | Time: {elapsed:.1f}s")

    artifacts = task.get("artifacts", {})
    for node_id, art in artifacts.items():
        agent = art.get("agent", "?")
        lat = art.get("latency", "?")
        model = art.get("model", "?")
        output_preview = art.get("output", "")[:100].replace("\n", " ")
        print(f"\n  [{node_id}] {agent} ({model}, {lat}s):")
        print(f"    {output_preview}...")

    messages = task.get("state", {}).get("messages", [])
    for m in messages:
        if m["role"] == "system":
            print(f"  [system] {m['content'][:80]}")


async def demo_hitl(client: httpx.AsyncClient, team_id: str, sop_id: str):
    """Demo 2: HITL mode — pause for human, then resume"""
    print("\n" + "=" * 60)
    print("Demo 2: HITL mode (pause → approve → continue)")
    print("=" * 60)

    # Step 1: Start task (will pause at HITL)
    print("\n[Step 1] Starting task (will pause at HITL node)...")
    r = await client.post(f"{BASE}/tasks", json={
        "sop_id": sop_id,
        "team_id": team_id,
        "input": {"requirements": "写一个快速排序函数"},
        "auto_approve_hitl": False,
    }, timeout=300)
    task = r.json()
    task_id = task["id"]

    print(f"  Task: {task_id[:8]}... | Status: {task['status']}")
    print(f"  Current node: {task['state']['current_node']}")
    print(f"  HITL pending: {task['state']['hitl_pending']}")
    hitl_data = task['state'].get('hitl_data', {})
    print(f"  HITL message: {hitl_data.get('message', 'N/A')}")

    # Show architect output
    artifacts = task.get("artifacts", {})
    for node_id, art in artifacts.items():
        output_preview = art.get("output", "")[:120].replace("\n", " ")
        print(f"\n  Architect output: {output_preview}...")

    # Step 2: Check pending HITL
    print("\n[Step 2] Checking pending HITL tasks...")
    r = await client.get(f"{BASE}/tasks/pending-hitl")
    pending = r.json()
    print(f"  Pending HITL tasks: {len(pending)}")
    for p in pending:
        print(f"    Task {p['id'][:8]}... | {p.get('hitl_data', {}).get('message', '')}")

    # Step 3: Approve
    print(f"\n[Step 3] Approving task {task_id[:8]}...")
    t0 = time.time()
    r = await client.post(f"{BASE}/tasks/{task_id}/resume", json={
        "action": "approve",
        "comment": "架构方案确认通过",
    }, timeout=300)
    task = r.json()
    elapsed = time.time() - t0

    print(f"  Status: {task['status']} | Resume time: {elapsed:.1f}s")

    artifacts = task.get("artifacts", {})
    for node_id, art in artifacts.items():
        agent = art.get("agent", "?")
        lat = art.get("latency", "?")
        output_preview = art.get("output", "")[:100].replace("\n", " ")
        print(f"\n  [{node_id}] {agent} ({lat}s):")
        print(f"    {output_preview}...")


async def demo_list_tasks(client: httpx.AsyncClient):
    """Demo 3: List all tasks"""
    print("\n" + "=" * 60)
    print("Demo 3: Task history")
    print("=" * 60)

    r = await client.get(f"{BASE}/tasks")
    tasks = r.json()
    print(f"\nTotal tasks: {len(tasks)}\n")
    for t in tasks:
        task_id = t["id"][:8]
        status = t["status"]
        req = t.get("input", {}).get("requirements", "N/A")[:40]
        updated = t.get("updated_at", "")[:19]
        print(f"  {task_id} | {status:10s} | {updated} | {req}")


async def main():
    print("SOP Engine CLI Demo")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30) as client:
        # Health check
        r = await client.get("http://localhost:8000/health")
        if r.status_code != 200:
            print("ERROR: Server not running at localhost:8000")
            sys.exit(1)
        print(f"Server: {r.json()}")

        # Setup
        team_id = await find_or_create_team(client)
        sop_id = await find_or_create_sop(client, team_id)
        print(f"\nTeam: {team_id[:8]}... | SOP: {sop_id[:8]}...")

        # Run demos
        await demo_auto_approve(client, team_id, sop_id)
        await demo_hitl(client, team_id, sop_id)
        await demo_list_tasks(client)

        print("\n" + "=" * 60)
        print("All demos completed!")


if __name__ == "__main__":
    asyncio.run(main())
