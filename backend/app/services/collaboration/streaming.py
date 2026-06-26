"""WebSocket event streaming — translates LangGraph events to frontend format.

Extracted from graph.py to keep concerns separated:
- graph.py: graph structure + routing
- streaming.py: event serialization + WebSocket push

Frontend event format (unchanged for compatibility):
- agent_message: {agent, content, type, model, latency}
- thinking_update: {agent, step, detail}
- reasoning_complete: {agent, thinking_steps, tool_calls, ...}
- hitl_request: {type, message, options}
- phase_update: {phases, current}
- routing_decision: {mode, agent_name}
- message_complete: {message}
"""

import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Type alias for the WebSocket send function
SendFn = Callable[[dict], Awaitable[None]]


# ── Node name → display name mapping ──

NODE_DISPLAY_NAMES: dict[str, str] = {
    "m0_intent": "",  # routing decision only, no thinking display
    "m1_analyze": "",
    "m1_rebalance": "",
    "m2_clarify": "",
    "m3_orchestrate": "",
    "m4_decompose": "",
    "m6_execute": "",
    "m6_execute_worker": "",
    # Delegation pipeline
    "m6_org_loader": "",
    "m6_delegate_root": "",
    "m6_delegate_sub": "",
    "m6_plan_validate": "",
    "m6_delegate_push": "",
    "m6_collect": "",
    "m6_escalate": "",
    "m7_verify": "",
}

# Nodes whose `_content` is real, user-facing agent output → emitted as `agent_message`
# chat bubbles. Pipeline orchestration nodes (org_loader / delegate_* / plan_validate /
# collect) only emit internal progress logs ("算法分配", "压栈", "验证通过"…) and must NOT
# appear as chat bubbles (they also leak raw role ids like "pm"/"architect").
CHAT_CONTENT_NODES: set[str] = {
    "m0_intent", "m1_analyze", "m1_requirement_analyzer", "m1_rebalance",
    "m2_clarify", "m2_clarification",
    "m3_orchestrate", "m3_agent_orchestrator",
    "m4_decompose",
    "m6_execute", "m6_level_execute", "m6_execute_worker", "m6_level_review",
    "m6_escalate",
    "m7_verify",
}


async def stream_to_websocket(
    graph,
    config: dict,
    user_message: str,
    websocket_send_fn: SendFn,
    team_agents: list = None,
    available_roles: list = None,
    team_id: str = "",
) -> None:
    """Stream LangGraph events to WebSocket client.

    Translates internal node events into frontend-compatible format.
    """
    from .types import CollabState

    session_id = config.get("configurable", {}).get("thread_id", "")
    initial_state: dict[str, Any] = {
        "messages": [{"role": "user", "content": user_message}],
        "team_id": team_id,
        "session_id": session_id,
        "available_roles": available_roles or [],
        "team_agents": team_agents or [],
        "status": "init",
        "current_phase": 0,
        "retry_count": 0,
    }

    # Track whether we've emitted routing decision
    routing_emitted = False

    async for event in graph.astream_events(
        initial_state,
        config,
        version="v2",
    ):
        event_type = event.get("event", "")

        # ── Node start → thinking status ──
        if event_type == "on_chain_start":
            node_name = event.get("name", "")
            display = NODE_DISPLAY_NAMES.get(node_name, node_name)
            # Use real team agent name when available
            team_agents_list = initial_state.get("team_agents", [])
            think_agent_name = team_agents_list[0].get("name", display) if team_agents_list else display
            if node_name in NODE_DISPLAY_NAMES:
                display = NODE_DISPLAY_NAMES.get(node_name, "")
                # Skip nodes without display name (pipeline stages, not agents)
                if not display:
                    continue
                # Emit routing decision on first node start
                if not routing_emitted:
                    routing_emitted = True

                await websocket_send_fn({
                    "type": "agent_status",
                    "source": "system",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "agent_id": node_name,
                        "agent_name": think_agent_name,
                        "status": "thinking",
                        "summary": f"{think_agent_name} 正在分析需求...",
                    },
                })

        # ── Node end → emit messages ──
        elif event_type == "on_chain_end":
            node_name = event.get("name", "")
            output = event.get("data", {}).get("output", {})
            if not isinstance(output, dict):
                continue

            # 只处理已知的 M-stage 节点，跳过 wrapper/parent chains（避免重复消息）
            if node_name not in NODE_DISPLAY_NAMES:
                continue

            # Debug: log reasoning presence for M1/M3
            if node_name in ("m1_analyze", "m3_orchestrate", "m4_decompose", "m6_execute",
                             "m6_level_execute", "m6_level_review", "m6_escalate",
                             "m6_delegate_root", "m6_delegate_sub", "m6_execute_worker", "m6_collect"):
                logger.info(f"[STREAM] {node_name} output keys: {list(output.keys())[:12]}, has_task_dag: {'task_dag' in output}, has_files: {'files_changed' in output}")

            timestamp = datetime.now().isoformat()
            agent_name = output.get("_agent_name", NODE_DISPLAY_NAMES.get(node_name, "System"))
            content = output.get("_content") or output.get("hitl_message", "")
            reasoning_data = output.get("_reasoning", {})
            model_name = output.get("_model", "")
            # _latency 在后端 LLM adapter 中是秒，前端统一用毫秒展示
            latency_raw = output.get("_latency", 0) or 0
            latency = int(latency_raw * 1000) if latency_raw and latency_raw < 1000 else int(latency_raw)

            # ── Emit routing decision event ──
            routing_decision = output.get("routing_decision", "")
            if routing_decision:
                await websocket_send_fn({
                    "type": "routing_decision",
                    "source": "system",
                    "timestamp": timestamp,
                    "payload": {
                        "mode": routing_decision,
                        "agent_name": agent_name,
                    },
                })

            # ── Emit stage transition message for multi-agent pipeline ──
            if node_name.startswith("m") and routing_decision != "single_agent":
                status_agent_name = output.get("_agent_name") or agent_name
                if content:
                    # Node produced actual content → will be emitted as agent_message below
                    pass
                else:
                    # Node completed without visible content → emit a status update
                    await websocket_send_fn({
                        "type": "agent_status",
                        "source": "system",
                        "timestamp": timestamp,
                        "payload": {
                            "agent_id": node_name,
                            "agent_name": status_agent_name,
                            "status": "done",
                            "summary": f"{status_agent_name} 完成",
                        },
                    })

            # Emit content only if there's something to show
            if content:
                # Thinking update — send supervisor_analysis for M1/M3 thinking display
                if reasoning_data:
                    # Determine step name for frontend recognition
                    thinking_step = node_name
                    if node_name in ("m1_analyze", "m1_requirement_analyzer", "m3_orchestrate", "m3_agent_orchestrator"):
                        thinking_step = "supervisor_analysis"

                    await websocket_send_fn({
                        "type": "thinking_update",
                        "source": "system",
                        "timestamp": timestamp,
                        "payload": {
                            "agent": agent_name,
                            "step": thinking_step,
                            "detail": reasoning_data.get("supervisor_analysis", ""),
                        },
                    })

                # Reasoning complete
                if reasoning_data:
                    await websocket_send_fn({
                        "type": "reasoning_complete",
                        "source": node_name,
                        "timestamp": timestamp,
                        "payload": {
                            "agent": agent_name,
                            "thinking_steps": reasoning_data.get("thinking_steps", ""),
                            "model_routing": reasoning_data.get("model_routing", {}),
                            "tool_calls": reasoning_data.get("tool_calls", []),
                            "decision_summary": reasoning_data.get("supervisor_analysis", ""),
                            "latency": latency,
                        },
                    })

                # Agent message (chat bubble) — only for nodes with real agent output.
                # Pipeline orchestration nodes are suppressed to keep chat clean.
                if node_name in CHAT_CONTENT_NODES:
                    await websocket_send_fn({
                        "type": "agent_message",
                        "source": node_name,
                        "timestamp": timestamp,
                        "payload": {
                            "agent": agent_name,
                            "content": content,
                            "type": "message",
                            "model": model_name,
                            "latency": latency,
                        },
                    })

            # HITL request
            hitl_type = output.get("hitl_type", "")
            if hitl_type in ("clarification", "confirmation", "agent_invite", "review"):
                await websocket_send_fn({
                    "type": "hitl_request",
                    "source": "system",
                    "timestamp": timestamp,
                    "payload": {
                        "type": hitl_type,
                        "message": output.get("hitl_message", ""),
                        "options": output.get("hitl_options", []),
                    },
                })

            # Phase update
            phases_plan = output.get("phases_plan", [])
            if phases_plan:
                await websocket_send_fn({
                    "type": "phase_update",
                    "source": "system",
                    "timestamp": timestamp,
                    "payload": {
                        "phases": [
                            p.get("name", p) if isinstance(p, dict) else p
                            for p in phases_plan
                        ],
                        "current": 0,
                    },
                })

            # Files changed
            files_changed = output.get("files_changed", [])
            if files_changed:
                await websocket_send_fn({
                    "type": "files_changed",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {"files": files_changed},
                })

            # ── Task DAG (M4 完成时推送细版任务图) ──
            task_dag = output.get("task_dag")
            if task_dag and isinstance(task_dag, dict):
                phases = task_dag.get("phases", [])
                logger.info(f"[STREAM] task_dag detected from {node_name}: {len(phases)} phases, sample keys: {list(phases[0].keys()) if phases else []}")
                if phases:
                    # 转换为前端需要的扁平结构：phases[].tasks[] 携带 agent_id/agent_name/agent_emoji
                    normalized_phases = []
                    total_tasks = 0
                    for phase in phases:
                        ph_id = phase.get("id") or f"phase-{len(normalized_phases) + 1}"
                        ph_name = phase.get("name", "")
                        tasks = []
                        for t in phase.get("tasks", []):
                            tasks.append({
                                "id": t.get("id", ""),
                                "name": t.get("title") or t.get("name") or t.get("description", ""),
                                "agent_id": t.get("assigned_to") or t.get("agent_id") or t.get("assigned_role", ""),
                                "agent_name": t.get("agent_name") or t.get("assigned_role", "Worker"),
                                "agent_emoji": t.get("agent_emoji", "🤖"),
                                "depends_on": t.get("depends_on", []),
                            })
                            total_tasks += 1
                        normalized_phases.append({
                            "id": ph_id,
                            "name": ph_name,
                            "tasks": tasks,
                        })
                    await websocket_send_fn({
                        "type": "task_dag",
                        "source": node_name,
                        "timestamp": timestamp,
                        "payload": {
                            "phases": normalized_phases,
                            "total_tasks": total_tasks,
                        },
                    })

            # ── delta_plan（M1' rebalance 输出，PR5 介入闭环） ──
            delta_plan = output.get("delta_plan")
            if delta_plan and isinstance(delta_plan, dict):
                await websocket_send_fn({
                    "type": "delta_plan",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {
                        "summary": delta_plan.get("summary", ""),
                        "keep": delta_plan.get("keep", []),
                        "modify": delta_plan.get("modify", []),
                        "add": delta_plan.get("add", []),
                        "cancel": delta_plan.get("cancel", []),
                        "version": delta_plan.get("version", 2),
                    },
                })

            # ── execution_state（介入状态变化） ──
            if output.get("status") == "interrupted":
                await websocket_send_fn({
                    "type": "execution_state",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {"state": "interrupting", "reason": "user_interrupt"},
                })
            elif node_name in ("m6_execute", "m6_level_dispatch",
                               "m6_delegate_root", "m6_delegate_sub") and output.get("status") == "completed":
                # M6 完成 → 回到 executing 态（让前端清理 interrupting 状态）
                await websocket_send_fn({
                    "type": "execution_state",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {"state": "executing", "reason": "m6_done"},
                })

        # ── HITL interrupt ──
        elif event_type == "on_interrupt":
            interrupt_data = event.get("data", {})
            await websocket_send_fn({
                "type": "hitl_request",
                "source": "system",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "type": interrupt_data.get("type", "confirmation"),
                    "message": interrupt_data.get("message", ""),
                    "options": interrupt_data.get("options", []),
                },
            })
            return  # Stop processing after HITL interrupt

    # ── Done ──
    await websocket_send_fn({
        "type": "message_complete",
        "source": "system",
        "timestamp": datetime.now().isoformat(),
        "payload": {"message": "协作流程完成"},
    })


async def resume_after_hitl(
    graph,
    config: dict,
    user_response: str,
    websocket_send_fn: SendFn,
) -> None:
    """Resume graph execution after HITL interrupt."""
    from langgraph.types import Command

    async for event in graph.astream_events(
        Command(resume=user_response),
        config,
        version="v2",
    ):
        event_type = event.get("event", "")

        if event_type == "on_chain_start":
            node_name = event.get("name", "")
            display = NODE_DISPLAY_NAMES.get(node_name, node_name)
            team_agents_list = config.get("configurable", {}).get("team_agents", [])
            think_agent_name = team_agents_list[0].get("name", display) if team_agents_list else display
            if node_name in NODE_DISPLAY_NAMES:
                await websocket_send_fn({
                    "type": "agent_status",
                    "source": "system",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "agent_id": node_name,
                        "agent_name": think_agent_name,
                        "status": "thinking",
                        "summary": f"{think_agent_name} 正在分析需求...",
                    },
                })

        elif event_type == "on_chain_end":
            node_name = event.get("name", "")
            output = event.get("data", {}).get("output", {})
            if not isinstance(output, dict):
                continue

            # 只处理已知的 M-stage 节点，跳过 LangGraph parent chain（避免 System 重复）
            if node_name not in NODE_DISPLAY_NAMES:
                continue

            timestamp = datetime.now().isoformat()
            content = output.get("_content") or output.get("hitl_message", "")
            agent_name = output.get("_agent_name", NODE_DISPLAY_NAMES.get(node_name, "System"))

            if content:
                await websocket_send_fn({
                    "type": "agent_message",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {
                        "agent": agent_name,
                        "content": content,
                        "type": "message",
                    },
                })

            # 同主流程：M4 完成时也推送 task_dag（resume 路径覆盖）
            task_dag = output.get("task_dag")
            if task_dag and isinstance(task_dag, dict):
                phases = task_dag.get("phases", [])
                if phases:
                    normalized_phases = []
                    total_tasks = 0
                    for phase in phases:
                        ph_id = phase.get("id") or f"phase-{len(normalized_phases) + 1}"
                        tasks_norm = []
                        for t in phase.get("tasks", []):
                            tasks_norm.append({
                                "id": t.get("id", ""),
                                "name": t.get("title") or t.get("name") or t.get("description", ""),
                                "agent_id": t.get("assigned_to") or t.get("agent_id") or t.get("assigned_role", ""),
                                "agent_name": t.get("agent_name") or t.get("assigned_role", "Worker"),
                                "agent_emoji": t.get("agent_emoji", "🤖"),
                                "depends_on": t.get("depends_on", []),
                            })
                            total_tasks += 1
                        normalized_phases.append({
                            "id": ph_id, "name": phase.get("name", ""), "tasks": tasks_norm,
                        })
                    await websocket_send_fn({
                        "type": "task_dag",
                        "source": node_name,
                        "timestamp": timestamp,
                        "payload": {"phases": normalized_phases, "total_tasks": total_tasks},
                    })

            # Files changed
            files_changed = output.get("files_changed", [])
            if files_changed:
                await websocket_send_fn({
                    "type": "files_changed",
                    "source": node_name,
                    "timestamp": timestamp,
                    "payload": {"files": files_changed},
                })

            hitl_type = output.get("hitl_type", "")
            if hitl_type in ("clarification", "confirmation", "agent_invite", "review", "delta_plan"):
                await websocket_send_fn({
                    "type": "hitl_request",
                    "source": "system",
                    "timestamp": timestamp,
                    "payload": {
                        "type": hitl_type,
                        "message": output.get("hitl_message", ""),
                        "options": output.get("hitl_options", []),
                    },
                })

        elif event_type == "on_interrupt":
            interrupt_data = event.get("data", {})
            await websocket_send_fn({
                "type": "hitl_request",
                "source": "system",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "type": interrupt_data.get("type", "confirmation"),
                    "message": interrupt_data.get("message", ""),
                    "options": interrupt_data.get("options", []),
                },
            })
            return

    await websocket_send_fn({
        "type": "message_complete",
        "source": "system",
        "timestamp": datetime.now().isoformat(),
        "payload": {"message": "协作流程完成"},
    })
