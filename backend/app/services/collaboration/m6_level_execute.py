"""M6 Level Execute — execute one dependency level's tasks in parallel.

Extracted from the old monolithic m6_dag_executor.py's inner loop.
Each call executes ONE level (current_level from state). The LangGraph
loop (dispatch → execute → review) handles level iteration.

Key difference from old M6: only runs ONE level, not all levels.
Artifacts and files are accumulated into state for the next iteration.
"""

import asyncio
import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


async def m6_level_execute_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: execute one topological level's tasks in parallel.

    Reads current_level and execution_levels from state.
    Adds results to the accumulative level_results, artifacts, and files_changed.
    """
    execution_levels = state.get("execution_levels", [])
    current_level = state.get("current_level", 0)
    session_id = state.get("session_id", "")
    team_id = state.get("team_id", "")
    requirements_anchor = state.get("requirements_anchor", "")
    agent_assignments = state.get("agent_assignments", {})

    # Accumulated from previous levels
    all_artifacts: dict[str, str] = dict(state.get("artifacts", {}))
    all_files: list[dict[str, Any]] = list(state.get("files_changed", []))
    level_results: list[dict[str, Any]] = list(state.get("level_results", []))

    if current_level >= len(execution_levels):
        return {"status": "all_levels_done"}

    level = execution_levels[current_level]
    logger.info(f"M6 LevelExecute: level {current_level} — {len(level)} tasks executing in parallel")

    # Resolve workspace path
    workspace_path = ""
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_workspace(session_id)
        if ws:
            workspace_path = ws.path
    except Exception:
        pass

    # ── Execute all tasks in this level in parallel ──
    tasks = []
    task_start_times: dict[str, float] = {}
    for task in level:
        tid = task.get("id", "")
        task_start_times[tid] = asyncio.get_event_loop().time()
        await _push_status(session_id, tid, "running")
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

    # ── Process results ──
    level_task_results: dict[str, dict[str, Any]] = {}
    level_errors: list[dict[str, Any]] = []

    for task, result in zip(level, results):
        tid = task.get("id", "")
        elapsed_ms = int((asyncio.get_event_loop().time() - task_start_times.get(tid, 0)) * 1000)

        if isinstance(result, Exception):
            logger.error(f"M6 LevelExecute: task {tid} failed: {result}")
            level_errors.append({"task_id": tid, "error": str(result)})
            await _push_status(session_id, tid, "failed", duration=elapsed_ms, error=str(result))
            level_task_results[tid] = {"status": "failed", "error": str(result)}
        elif isinstance(result, dict):
            if result.get("output"):
                all_artifacts[tid] = result["output"]
                level_task_results[tid] = {"status": "done", "output": result["output"]}
            if result.get("files"):
                all_files.extend(result["files"])
                if tid not in level_task_results:
                    level_task_results[tid] = {}
                level_task_results[tid]["files"] = result["files"]
            if result.get("error"):
                level_errors.append({"task_id": tid, "error": result["error"]})
                await _push_status(session_id, tid, "failed", duration=elapsed_ms, error=result["error"])
                level_task_results[tid] = {"status": "failed", "error": result["error"]}
            else:
                # Push Worker message (reasoning + tool_calls + files)
                if result.get("llm_result"):
                    await _push_worker_message(
                        session_id=session_id,
                        task=task,
                        llm_result=result["llm_result"],
                        files=result.get("files", []),
                        agent_name=result.get("agent_name") or "Worker",
                        latency_s=result.get("latency_s", 0),
                    )
                await _push_status(session_id, tid, "done", duration=elapsed_ms)
                level_task_results.setdefault(tid, {})["status"] = "done"
        else:
            level_task_results[tid] = {"status": "unknown", "raw": str(result)}

    # ── Record level result ──
    level_results.append({
        "level_idx": current_level,
        "task_results": level_task_results,
        "error_count": len(level_errors),
        "total_count": len(level),
    })

    # Build summary for the chat bubble
    level_num = current_level + 1
    total_levels = len(execution_levels)
    success_count = len(level) - len(level_errors)

    summary_parts = []
    for task in level:
        tid = task.get("id", "")
        name = task.get("title") or task.get("name") or tid
        tr = level_task_results.get(tid, {})
        status_icon = "✅" if tr.get("status") == "done" else "❌"
        summary_parts.append(f"  {status_icon} {name}")

    content = (
        f"🔹 **Level {level_num}/{total_levels}** 执行完成: "
        f"{success_count}/{len(level)} 个任务成功"
        + (f", {len(level_errors)} 个失败" if level_errors else "")
        + "\n" + "\n".join(summary_parts)
    )

    return {
        "artifacts": all_artifacts,
        "files_changed": all_files,
        "level_results": level_results,
        "status": "executing",
        "_content": content,
        "_agent_name": "Worker",
    }


# ── Routing ──

def route_after_level_execute(state: CollabState) -> str:
    """Route after level execution.

    Has org_structure → m6_level_review (hierarchical review).
    No org_structure → m6_level_dispatch (flat team, skip review, next level).
    """
    org_structure = state.get("org_structure")
    if org_structure and org_structure.get("relations"):
        return "m6_level_review"
    return "m6_level_dispatch"


# ── Helpers (extracted from old m6_dag_executor.py, kept as private functions) ──

async def _push_status(
    session_id: str,
    task_id: str,
    status: str,
    duration: int | None = None,
    error: str | None = None,
) -> None:
    """Broadcast task_status event via WebSocket."""
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
            "source": "m6_level_execute",
            "timestamp": datetime.now().isoformat(),
            "payload": payload,
        })
    except Exception as e:
        logger.warning(f"M6 LevelExecute push_status failed: {e}")


async def _push_worker_message(
    session_id: str,
    task: dict[str, Any],
    llm_result: dict[str, Any],
    files: list[dict[str, Any]],
    agent_name: str,
    latency_s: float,
) -> None:
    """Push worker's reasoning + content + files to frontend and persist to Memory."""
    try:
        from app.services.ws_broadcaster import manager
        from datetime import datetime
        import time as _time

        ts = datetime.now().isoformat()
        reasoning = llm_result.get("reasoning", {}) or {}
        content = llm_result.get("content", "") or ""

        # Persist to Memory
        _persist_worker_result(session_id, task, content, reasoning, agent_name, latency_s)

        # 1. agent_message
        await manager.broadcast_to_session(session_id, {
            "type": "agent_message",
            "source": "m6_level_execute",
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

        # 2. reasoning_complete
        if reasoning:
            await manager.broadcast_to_session(session_id, {
                "type": "reasoning_complete",
                "source": "m6_level_execute",
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

        # 3. files_changed
        if files:
            await manager.broadcast_to_session(session_id, {
                "type": "files_changed",
                "source": "m6_level_execute",
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
        logger.warning(f"M6 LevelExecute push_worker_message failed: {e}")


def _persist_worker_result(
    session_id: str,
    task: dict[str, Any],
    content: str,
    reasoning: dict[str, Any],
    agent_name: str,
    latency_s: float,
) -> None:
    """Persist worker output to Memory so it survives page refresh."""
    try:
        from app.services.memory_manager import MemoryManager
        from app.schemas.memory import MemoryLevel, MemoryType
        from app.services.session_service import SessionService
        import uuid as _uuid
        import time as _time

        async def _do_persist():
            from app.core.database import async_session
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
                        "source": "m6_level_execute",
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

        # Run in background, don't block the level execution
        import asyncio
        asyncio.create_task(_do_persist())
    except Exception as e:
        logger.warning(f"M6 LevelExecute: worker persistence failed for {task.get('id')}: {e}")


async def _execute_single_task(
    task: dict[str, Any],
    requirements_anchor: str,
    all_artifacts: dict[str, str],
    agent_assignments: dict[str, Any],
    session_id: str,
    team_id: str,
    workspace_path: str,
) -> dict[str, Any]:
    """Execute a single task via agent_chat with M5 context trimming.

    Preserved from the original m6_dag_executor._execute_single_task.
    """
    from .m5_context_pipeline import context_pipeline
    from .m8_peer_mailbox import peer_mailbox

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

            # Share findings with peers (M8)
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
        logger.error(f"M6 LevelExecute: task {task.get('id', '?')} execution failed: {e}")
        return {"output": "", "files": [], "error": str(e)}
