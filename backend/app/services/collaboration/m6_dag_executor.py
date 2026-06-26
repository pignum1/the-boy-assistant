"""M6: DAG Executor — topological sort, parallel execution, progress push.

Executes tasks from M4's task_dag in dependency order:
- Same-level tasks run in parallel (asyncio.gather)
- Each task gets trimmed context via M5
- Results (artifacts) are accumulated for dependent tasks
- M8 peer messages flow between workers during execution
- Progress is reported via callback for WebSocket streaming
"""

import asyncio
import logging
from typing import Any, Callable, Awaitable

from .m4_task_decomposer import topological_sort
from .m5_context_pipeline import context_pipeline
from .m8_peer_mailbox import peer_mailbox
from .interrupt_coordinator import interrupt_coordinator
from .types import CollabState

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressFn = Callable[[str, str, str], Awaitable[None]]  # (task_id, status, message)


async def m6_execute_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M6 execute tasks from DAG.

    Uses topological sort for dependency order, parallel within each level.
    每个任务开始/结束时通过 ws_broadcaster 推送 task_status 事件。
    """
    task_dag = state.get("task_dag", {})
    requirements_anchor = state.get("requirements_anchor", "")
    agent_assignments = state.get("agent_assignments", {})
    session_id = state.get("session_id", "")
    team_id = state.get("team_id", "")

    phases = task_dag.get("phases", [])
    if not phases:
        return {
            "status": "completed",
            "artifacts": {},
            "files_changed": [],
        }

    # 主动 broadcast task_dag（兜底：M4 的 on_chain_end 可能没触发）
    try:
        from app.services.ws_broadcaster import manager
        from datetime import datetime
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
                "id": ph_id,
                "name": phase.get("name", ""),
                "tasks": tasks_norm,
            })
        await manager.broadcast_to_session(session_id, {
            "type": "task_dag",
            "source": "m6_execute",
            "timestamp": datetime.now().isoformat(),
            "payload": {"phases": normalized_phases, "total_tasks": total_tasks},
        })
        logger.info(f"M6 broadcast task_dag: {len(phases)} phases, {total_tasks} tasks")
    except Exception as e:
        logger.warning(f"M6 task_dag broadcast failed: {e}")

    # 建立 task_status 推送回调（按 session_id 广播）
    async def push_status(task_id: str, status: str, duration: int | None = None, error: str | None = None) -> None:
        try:
            from app.services.ws_broadcaster import manager
            from datetime import datetime
            payload: dict[str, Any] = {"task_id": task_id, "status": status}
            if duration is not None:
                payload["duration"] = duration
            if error:
                payload["error"] = error
            await manager.broadcast_to_session(session_id, {
                "type": "task_status",
                "source": "m6_execute",
                "timestamp": datetime.now().isoformat(),
                "payload": payload,
            })
        except Exception as e:
            logger.warning(f"M6 push_status failed: {e}")

    # 推送 worker 完成时的独立消息（含 reasoning + tool_calls，让用户看到每个 Agent 的思考链路）
    # 同时持久化到 Memory（否则刷新后丢失）
    async def push_worker_message(task: dict, llm_result: dict, files: list, agent_name: str, latency_s: float) -> None:
        try:
            from app.services.ws_broadcaster import manager
            from datetime import datetime
            import time as _time
            ts = datetime.now().isoformat()
            reasoning = llm_result.get("reasoning", {}) or {}
            content = llm_result.get("content", "") or ""

            # 持久化：把 worker 消息存到 Memory，刷新后能看到完整协作链路
            try:
                from app.core.database import async_session
                from app.services.memory_manager import MemoryManager
                from app.schemas.memory import MemoryLevel, MemoryType
                from app.services.session_service import SessionService
                import uuid as _uuid
                async with async_session() as db:
                    svc = SessionService(db)
                    sess = await svc.get_session(_uuid.UUID(session_id))
                    if sess and content:
                        tag = f"[{_time.time_ns()}]"
                        tid = task.get("id", "")
                        title = task.get("title") or task.get("name") or tid
                        combined = f"用户{tag}: [Worker:{tid}]\n助手: {content}"
                        meta = {
                            "agent": agent_name,
                            "source": "m6_execute",
                            "task_id": tid,
                            "task_title": title,
                            "model": (reasoning.get("model_routing") or {}).get("selected_model"),
                            "latency": int(latency_s * 1000) if latency_s else 0,
                            "thinking_steps": reasoning.get("thinking_steps", ""),
                            "tool_calls": reasoning.get("tool_calls", []),
                            "model_routing": reasoning.get("model_routing", {}),
                            "decision_summary": f"完成任务: {title}",
                        }
                        meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
                        await MemoryManager(db).save_memory(
                            level=MemoryLevel.context, content=combined,
                            type=MemoryType.context, team_id=sess.team_id,
                            session_id=session_id, importance=0.5, created_by="system",
                            metadata_=meta,
                        )
                        await db.commit()
            except Exception as e:
                logger.warning(f"M6 worker persistence failed for {task.get('id')}: {e}")

            # 1. agent_message：worker 主消息，绑定到 m6 阶段 + task_id
            await manager.broadcast_to_session(session_id, {
                "type": "agent_message",
                "source": "m6_execute",
                "timestamp": ts,
                "payload": {
                    "agent": agent_name,
                    "content": content[:6000],
                    "type": "message",
                    "model": (reasoning.get("model_routing", {}) or {}).get("selected_model"),
                    "latency": int(latency_s * 1000) if latency_s else 0,
                    "task_id": task.get("id", ""),
                },
            })
            # 2. reasoning_complete：附带思考过程 / 工具调用
            if reasoning:
                await manager.broadcast_to_session(session_id, {
                    "type": "reasoning_complete",
                    "source": "m6_execute",
                    "timestamp": ts,
                    "payload": {
                        "agent": agent_name,
                        "thinking_steps": reasoning.get("thinking_steps", ""),
                        "model_routing": reasoning.get("model_routing", {}),
                        "tool_calls": reasoning.get("tool_calls", []),
                        "decision_summary": f"完成任务: {task.get('title', task.get('id', ''))}",
                        "latency": int(latency_s * 1000) if latency_s else 0,
                    },
                })
            # 3. files_changed：worker 产物，立刻推送（不等 M6 整体完成）
            if files:
                await manager.broadcast_to_session(session_id, {
                    "type": "files_changed",
                    "source": "m6_execute",
                    "timestamp": ts,
                    "payload": {
                        "files": [
                            {
                                **f,
                                "producer_agent_name": agent_name,
                                "producer_task_id": task.get("id", ""),
                            } for f in files
                        ],
                    },
                })
        except Exception as e:
            logger.warning(f"M6 push_worker_message failed: {e}")

    # Topological sort into dependency levels
    levels = topological_sort(phases)

    # Resolve workspace path
    workspace_path = ""
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_workspace(session_id)
        if ws:
            workspace_path = ws.path
    except Exception:
        pass

    all_artifacts: dict[str, str] = {}
    all_files: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []

    for level_idx, level in enumerate(levels):
        # ── 介入检查：每个 level 开始前 poll 一次 ──
        if interrupt_coordinator.has_pending(session_id):
            req = interrupt_coordinator.consume(session_id)
            logger.info(f"M6 interrupted before level {level_idx}: mode={req.mode if req else '?'}")
            return {
                "status": "interrupted",
                "interrupt_message": req.message if req else "",
                "interrupt_mode": req.mode if req else "soft",
                "artifacts": all_artifacts,
                "files_changed": all_files,
                "_agent_name": "Worker",
                "_content": f"⏸ 已在 level {level_idx} 处暂停，等待重规划",
            }

        logger.info(f"M6 Level {level_idx}: {len(level)} tasks — executing in parallel")

        # Execute all tasks in this level in parallel
        tasks = []
        task_start_times: dict[str, float] = {}
        for task in level:
            # 推送 running 状态
            tid = task.get("id", "")
            task_start_times[tid] = asyncio.get_event_loop().time()
            await push_status(tid, "running")
            tasks.append(_execute_single_task(
                task=task,
                requirements_anchor=requirements_anchor,
                all_artifacts=all_artifacts,
                agent_assignments=agent_assignments,
                session_id=session_id,
                team_id=team_id,
                workspace_path=workspace_path,
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for task, result in zip(level, results):
            tid = task.get("id", "")
            elapsed_ms = int((asyncio.get_event_loop().time() - task_start_times.get(tid, 0)) * 1000)
            if isinstance(result, Exception):
                logger.error(f"M6 task {tid} failed: {result}")
                all_errors.append({"task_id": tid, "error": str(result)})
                await push_status(tid, "failed", duration=elapsed_ms, error=str(result))
            elif isinstance(result, dict):
                if result.get("output"):
                    all_artifacts[tid] = result["output"]
                if result.get("files"):
                    all_files.extend(result["files"])
                if result.get("error"):
                    all_errors.append({"task_id": tid, "error": result["error"]})
                    await push_status(tid, "failed", duration=elapsed_ms, error=result["error"])
                else:
                    # 推送 Worker 独立消息（含 reasoning + tool_calls + 实时 files_changed）
                    if result.get("llm_result"):
                        await push_worker_message(
                            task=task,
                            llm_result=result["llm_result"],
                            files=result.get("files", []),
                            agent_name=result.get("agent_name") or "Worker",
                            latency_s=result.get("latency_s", 0),
                        )
                    await push_status(tid, "done", duration=elapsed_ms)

    # Build summary
    total_tasks = sum(len(p.get("tasks", [])) for p in phases)
    success_count = total_tasks - len(all_errors)

    return {
        "status": "completed",
        "artifacts": all_artifacts,
        "files_changed": all_files,
        "hitl_type": "review",
        "hitl_message": f"✅ 执行完成: {success_count}/{total_tasks} 个任务成功"
                        + (f", {len(all_errors)} 个失败" if all_errors else ""),
        "hitl_options": [
            {"label": "✅ 确认完成", "value": "approve"},
            {"label": "✎ 需要修改", "value": "modify"},
        ],
        "_content": _format_execution_summary(all_artifacts, all_files, all_errors),
        "_agent_name": "Worker",
    }


async def _execute_single_task(
    task: dict[str, Any],
    requirements_anchor: str,
    all_artifacts: dict[str, str],
    agent_assignments: dict[str, dict],
    session_id: str,
    team_id: str,
    workspace_path: str,
) -> dict[str, Any]:
    """Execute a single task via agent_chat with M5 context trimming."""
    assigned_role = task.get("assigned_role", "")

    # Get peer messages for this worker (M8)
    peer_msgs = peer_mailbox.format_for_context(session_id, assigned_role)

    # Build trimmed context via M5
    ctx = context_pipeline.build_context(
        requirement_anchor=requirements_anchor,
        task=task,
        all_artifacts=all_artifacts,
        peer_messages=peer_msgs,
    )
    prompt = context_pipeline.format_context(ctx, workspace_path=workspace_path)

    # Find the right agent for this role
    from app.core.database import async_session
    from app.services.agent_chat import agent_chat
    from app.models.agent import Agent
    from sqlalchemy import select

    try:
        async with async_session() as db:
            agent = None
            agent_info = agent_assignments.get(assigned_role)
            if agent_info:
                agent_id = agent_info.get("agent_id")
                if agent_id:
                    stmt = select(Agent).where(Agent.id == agent_id)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return {"output": "", "files": [], "error": "No agent available"}

            import time
            t_start = time.monotonic()
            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=True, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
            latency_s = time.monotonic() - t_start

            output = llm_result.get("content", "")

            # Extract file changes from tool calls
            # 宽松匹配：包含 "file" 关键字（file-ops / file_ops / file-ops.write 等都算）
            files = []
            tool_calls = llm_result.get("reasoning", {}).get("tool_calls", [])
            for tc in tool_calls:
                tool_name = (tc.get("tool") or "").lower()
                if "file" in tool_name and tc.get("success"):
                    params = tc.get("params") or {}
                    path = (
                        params.get("path")
                        or params.get("file_path")
                        or params.get("filename")
                        or params.get("name")
                        or "unknown"
                    )
                    files.append({
                        "name": path,
                        "status": "created",
                        "meta": "",
                    })

            # Share useful findings with other workers (M8)
            if output and len(all_artifacts) > 0:
                peer_mailbox.send(
                    session_id=session_id,
                    from_agent=assigned_role,
                    to_agent="__all__",
                    msg_type="share",
                    content=f"完成了任务 '{task.get('title', '')}'，产出已就绪。",
                    references=[task.get("id", "")],
                )

            return {
                "output": output,
                "files": files,
                "llm_result": llm_result,
                "agent_name": agent.name,
                "latency_s": latency_s,
            }

    except Exception as e:
        logger.error(f"M6 task {task.get('id', '?')} execution failed: {e}")
        return {"output": "", "files": [], "error": str(e)}


def _format_execution_summary(
    artifacts: dict[str, str],
    files: list[dict],
    errors: list[dict],
) -> str:
    """Format execution summary for chat display."""
    lines = [f"✅ **执行完成**: {len(artifacts)} 个任务产出"]

    if files:
        lines.append(f"\n📁 **文件变更** ({len(files)} 个文件):")
        for f in files[:10]:  # Show max 10 files
            lines.append(f"  - `{f['name']}` {f.get('status', '')}")
        if len(files) > 10:
            lines.append(f"  - ... 还有 {len(files) - 10} 个文件")

    if errors:
        lines.append(f"\n❌ **失败任务** ({len(errors)} 个):")
        for e in errors:
            lines.append(f"  - {e['task_id']}: {e['error'][:100]}")

    # Append artifact content (truncated)
    for task_id, content in artifacts.items():
        if content:
            truncated = content[:2000]
            lines.append(f"\n### 产出: {task_id}\n{truncated}")

    return "\n".join(lines)


# ── Route function ──

def route_after_m6(state: CollabState) -> str:
    """After M6: rebalance (if interrupted) / verify / show review HITL."""
    status = state.get("status", "")
    if status == "interrupted":
        return "m1_rebalance"  # 介入触发，跳到增量重规划
    artifacts = state.get("artifacts", {})
    if artifacts:
        return "m7_verify"  # Has output → verify
    return "hitl"  # No output → show result to user
