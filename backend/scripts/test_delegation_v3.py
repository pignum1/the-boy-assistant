"""Test delegation v3 flow — proper HITL handling for both clarification & confirmation."""
import asyncio
import json
import sys
import websockets

SESSION_ID = "0a73859c-7118-4656-8607-a407b895ef34"
WS_URL = f"ws://127.0.0.1:8000/ws/sessions/{SESSION_ID}"

# Detailed message so M1 doesn't need to clarify
MSG = (
    "请帮我设计并实现一个用户注册+登录模块。"
    "技术栈：后端FastAPI + 前端React + 数据库PostgreSQL。"
    "功能：邮箱注册(含昵称，密码8位含字母+数字)，邮箱+密码登录，"
    "忘记密码(通过邮箱发送重置链接)，不需要邮箱验证和验证码。"
    "输出：API接口设计、前端登录/注册/忘记密码页面、数据库表设计。"
    "团队分工完成，直接开始实施。"
)

# Answers for clarification HITLs
CLARIFY_ANSWER = (
    "后端FastAPI、前端React、PostgreSQL。"
    "邮箱注册+密码登录，密码8位含字母数字。"
    "忘记密码通过邮箱重置链接实现。不需要验证码和邮箱验证。"
    "直接输出全部：API设计、前端页面、数据库表设计。"
    "请直接开始分工执行。"
)


async def test():
    events = 0
    node_trace = []
    hitl_count = 0
    max_hitl = 10  # Safety limit

    print(f"Session: {SESSION_ID}")
    print(f"Message: {MSG[:100]}...\n")

    async with websockets.connect(WS_URL, open_timeout=10) as ws:
        # Trigger collaboration flow
        await ws.send(json.dumps({"type": "chat", "message": MSG, "mode": "collab"}))
        print(">>> Sent collab chat\n")

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=300.0)
            except asyncio.TimeoutError:
                print("\n⏰ Timeout - no events for 300s")
                break

            evt = json.loads(raw)
            events += 1
            t = evt.get("type", "?")
            p = evt.get("payload", {})

            # ── Track node transitions ──
            if t == "agent_status":
                status = p.get("status", "?")
                name = p.get("agent_name", "?")
                nid = p.get("agent_id", "?")
                node_trace.append(f"{status}:{name}")
                summary = p.get("summary", "") or ""
                # Print only known nodes
                if "M" in name or name in ("Supervisor", "Worker", "Leader·委派",
                    "主管·委派", "委派验证", "委派压栈", "主管·审核", "升级处理",
                    "验证员", "审核员", "架构师", "调度器"):
                    print(f"  [{events}] {status} | {name} | {summary[:100]}")

            elif t == "agent_message":
                c = (p.get("content", "") or "")[:300]
                print(f"  [{events}] 💬 {p.get('agent','?')}: {c}")

            elif t == "hitl_request":
                hitl_count += 1
                if hitl_count > max_hitl:
                    print(f"\n  ⚠️ HITL LOOP ({hitl_count} HITLs) — STOPPING")
                    break

                opts = p.get("options", []) or evt.get("options", [])
                opt_vals = [o.get("value", "") for o in opts]
                hitl_type = evt.get("hitl_type", "select")
                hitl_id = evt.get("hitl_id", "")
                print(f"\n  [{events}] ⏸ HITL#{hitl_count} type={hitl_type} opts={opt_vals}")

                await asyncio.sleep(0.5)

                if "approve" in opt_vals:
                    resp = {"type": "hitl_resume", "hitl_id": hitl_id,
                            "hitl_type": "select", "values": ["approve"]}
                    print(f"  ↪ → approve")
                elif "answer" in opt_vals:
                    resp = {"type": "hitl_resume", "hitl_id": hitl_id,
                            "hitl_type": "answer", "feedback": CLARIFY_ANSWER,
                            "response": CLARIFY_ANSWER}
                    print(f"  ↪ → answer (with details)")
                else:
                    resp = {"type": "hitl_resume", "hitl_id": hitl_id,
                            "hitl_type": "select", "values": [opt_vals[0]] if opt_vals else ["approve"]}
                    print(f"  ↪ → default: {resp['values']}")
                await ws.send(json.dumps(resp))

            elif t == "message_complete":
                print(f"  [{events}] ✅ message_complete\n")

            elif t == "thinking_update":
                detail = (p.get("detail", "") or "")[:120]
                step = p.get("step", "?")
                print(f"  [{events}] 🧠 [{step}] {detail}")

            elif t == "error":
                print(f"  [{events}] ❌ ERROR: {p.get('message','?')}")
                break

    print(f"\n{'='*60}")
    print(f"SUMMARY: {events} events, {hitl_count} HITLs")
    print(f"Node trace: {' → '.join(node_trace[:50])}")


if __name__ == "__main__":
    asyncio.run(test())
