"""WebSocket 端点：实时任务事件推送 + 会话事件推送

端点：
- ws://.../ws/tasks/{task_id}    任务执行事件（SOP 模式）
- ws://.../ws/sessions/{session_id} 会话讨论事件（Discussion 模式）
消息类型：node_update / agent_message / hitl_notification / task_complete
         thinking_update / reasoning_complete / message_complete
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_broadcaster import manager
from app.core.auth import verify_ws_auth

router = APIRouter()
logger = logging.getLogger(__name__)

# WebSocket 消息最大大小：1 MB
_MAX_WS_MESSAGE_BYTES = 1 * 1024 * 1024


@router.websocket("/ws/tasks/{task_id}")
async def websocket_task_events(websocket: WebSocket, task_id: str):
    """WebSocket 端点：订阅任务实时事件"""
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.close(code=4001, reason="Invalid or missing API key")
        return
    logger.info(f"WebSocket client connected for task: {task_id}")

    team_id = websocket.query_params.get("team_id", "")
    await manager.connect(task_id, team_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if len(data.encode("utf-8")) > _MAX_WS_MESSAGE_BYTES:
                logger.warning("Oversized WS message from task %s: %d bytes", task_id, len(data.encode("utf-8")))
                continue
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for task: {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {e}")
    finally:
        await manager.disconnect(task_id, websocket)


@router.websocket("/ws/sessions/{session_id}")
async def websocket_session_events(websocket: WebSocket, session_id: str):
    """WebSocket 端点：订阅会话讨论事件

    接收客户端消息：
    - "ping" → 回复 pong
    - {"type": "chat", "message": "..."}  → 触发 DiscussionEngine
    - {"type": "chat", "message": "...", "mode": "collab"} → 触发 LangGraph 协作引擎
    - {"type": "hitl_resume", "response": "..."} → 恢复 HITL 暂停
    """
    await websocket.accept()
    if not await verify_ws_auth(websocket):
        await websocket.close(code=4001, reason="Invalid or missing API key")
        return
    logger.info(f"WebSocket client connected for session: {session_id}")

    await manager.connect_session(session_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if len(data.encode("utf-8")) > _MAX_WS_MESSAGE_BYTES:
                logger.warning("Oversized WS message from session %s: %d bytes", session_id, len(data.encode("utf-8")))
                continue
            if data == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                # ── HITL resume ──
                if msg_type == "hitl_resume":
                    # Build structured response dict from client message
                    hitl_type = msg.get("hitl_type", "select")
                    response_data = {
                        "hitl_id": msg.get("hitl_id", ""),
                        "hitl_type": hitl_type,
                    }
                    if hitl_type in ("select", "multi_select", "confirmation", "escalation", "clarification"):
                        response_data["values"] = msg.get("values", [msg.get("response", "")])
                    elif hitl_type == "answer":
                        response_data["feedback"] = msg.get("response", "")
                    elif hitl_type == "review":
                        response_data["approved"] = msg.get("approved", False)
                        response_data["feedback"] = msg.get("feedback", "")
                    await _handle_hitl_resume(
                        websocket=websocket,
                        session_id=session_id,
                        user_response=response_data,
                    )
                    continue

                # ── 介入（PR5 软介入 / 硬中断） ──
                if msg_type == "interrupt":
                    mode = msg.get("mode", "soft")
                    message = msg.get("message", "")
                    from app.services.collaboration.interrupt_coordinator import interrupt_coordinator
                    interrupt_coordinator.request_interrupt(session_id, mode, message)
                    await websocket.send_json({
                        "type": "execution_state",
                        "payload": {
                            "state": "interrupting" if mode == "soft" else "paused",
                            "reason": f"user_interrupt_{mode}",
                        },
                    })
                    continue

                # ── 介入恢复（PR5 硬中断后用户主动恢复） ──
                if msg_type == "resume":
                    message = msg.get("message", "")
                    from app.services.collaboration.interrupt_coordinator import interrupt_coordinator
                    interrupt_coordinator.resume(session_id)
                    # 如果用户带了消息，作为新一轮 chat 发起
                    if message:
                        await _handle_collab_chat(
                            websocket=websocket,
                            session_id=session_id,
                            user_message=message,
                            mentioned_agents=[],
                        )
                    else:
                        await websocket.send_json({
                            "type": "execution_state",
                            "payload": {"state": "executing", "reason": "resumed"},
                        })
                    continue

                # ── 批准/拒绝 delta_plan（PR5） ──
                if msg_type == "approve_delta_plan":
                    approve = bool(msg.get("approve", False))
                    await _handle_hitl_resume(
                        websocket=websocket,
                        session_id=session_id,
                        user_response={
                            "hitl_type": "review",
                            "approved": approve,
                            "feedback": "确认" if approve else "撤回",
                        },
                    )
                    continue

                # ── Chat message ──
                if msg_type == "chat":
                    user_message = msg.get("message", "")
                    mentioned_agents = msg.get("mentioned_agents", [])

                    # 安全检查：Prompt Injection 检测
                    from app.services.safety_filter import detect_injection
                    is_injection, reason = detect_injection(user_message)
                    if is_injection:
                        logger.warning(f"Blocked prompt injection: {reason}")
                        await websocket.send_json({
                            "type": "error",
                            "source": "security",
                            "timestamp": datetime.now().isoformat(),
                            "payload": {
                                "message": f"输入被安全策略拦截：{reason}",
                                "code": "prompt_injection_detected",
                            },
                        })
                        continue

                    print(f"[WS] Received chat message: {user_message[:50]}...")
                    logger.info(f"Session chat message: {user_message[:50]}")

                    if "@all" in user_message or "@ALL" in user_message:
                        mentioned_agents = ["__all__"]

                    if user_message:
                        await _handle_collab_chat(
                            websocket=websocket,
                            session_id=session_id,
                            user_message=user_message,
                            mentioned_agents=mentioned_agents,
                        )
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Session chat error: {e}")
                # Guard: never send on a socket that already closed, else this
                # raises "Cannot call send once a close message has been sent".
                try:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": str(e)},
                    })
                except Exception:
                    pass
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        await manager.disconnect_session(session_id, websocket)


async def _handle_session_chat(
    websocket: WebSocket,
    session_id: str,
    user_message: str,
    mentioned_agents: list[str] = None,
):
    """处理会话聊天消息：通过 DiscussionEngine 执行并推送事件"""
    from app.core.database import async_session
    from app.services.discussion_engine import DiscussionEngine

    async with async_session() as db:
        from app.models.session import Session
        import uuid

        session = await db.get(Session, uuid.UUID(session_id))
        if not session:
            await websocket.send_json({
                "type": "error",
                "payload": {"message": "会话不存在"},
            })
            return

        # 立即保存用户消息（防止刷新丢失）
        from app.services.memory_manager import MemoryManager
        from app.schemas.memory import MemoryLevel, MemoryType
        try:
            mm = MemoryManager(db)
            await mm.save_memory(
                level=MemoryLevel.context,
                content=user_message,
                type=MemoryType.context,
                team_id=session.team_id,
                session_id=session_id,
                importance=0.4,
                created_by="user",
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save user message: {e}")

        engine = DiscussionEngine(db)
        async for event in engine.process_message(
            session_id=uuid.UUID(session_id),
            user_message=user_message,
            team_id=session.team_id,
            mentioned_agents=mentioned_agents or [],
        ):
            await websocket.send_json({
                "type": event.type.value,
                "source": event.source,
                "timestamp": event.timestamp,
                "payload": event.payload,
            })


# ── Collaboration mode (multi-engine via router) ──


async def _handle_collab_chat(
    websocket,
    session_id: str,
    user_message: str,
    mentioned_agents: list[str] = None,
):
    """Handle chat via collaboration router (swarm / supervisor / langgraph)."""
    from app.core.database import async_session
    from app.services.collaboration.router import dispatch as router_dispatch
    import uuid

    async with async_session() as db:
        from app.models.session import Session as SessionModel
        session = await db.get(SessionModel, uuid.UUID(session_id))
        if not session:
            await websocket.send_json({
                "type": "error", "payload": {"message": "会话不存在"},
            })
            return

        from app.models.team import Team
        from app.models.team_member import TeamMember
        from app.models.agent import Agent as AgentModel
        from sqlalchemy import select

        team = await db.get(Team, session.team_id)
        if not team:
            await websocket.send_json({
                "type": "error", "payload": {"message": "团队不存在"},
            })
            return

        team_agents = []
        members = await db.execute(
            select(TeamMember, AgentModel)
            .join(AgentModel, TeamMember.agent_id == AgentModel.id)
            .where(TeamMember.team_id == team.id)
        )
        for tm, agent in members:
            team_agents.append({
                "agent_id": str(agent.id),
                "name": agent.name,
                "role": tm.role_name or "",
                "capabilities": tm.capabilities or [],
                "status": "idle",
            })

        available_roles = team.capabilities if team.capabilities else [
            "pm", "architect", "backend_dev", "frontend_dev", "tester",
            "ui_designer", "devops"
        ]

        # Track agent responses to save as dialog memory: [{content, agent}]
        agent_responses: list[dict] = []
        # Also track reasoning data keyed by agent name for rich context persistence
        reasoning_by_agent: dict[str, dict] = {}

        # 用于实时持久化的 MemoryManager（在 async_session 上下文中）
        from app.services.memory_manager import MemoryManager
        from app.schemas.memory import MemoryLevel, MemoryType
        import time as _time

        mm = MemoryManager(db)
        # 立即保存用户消息（带唯一时间戳避免去重）
        user_msg_tag = f"[{_time.time_ns()}]"
        try:
            await mm.save_memory(
                level=MemoryLevel.context,
                content=f"{user_message}{user_msg_tag}",
                type=MemoryType.context,
                team_id=session.team_id,
                session_id=session_id,
                importance=0.5,
                created_by="user",
                metadata_={"role": "user"},
            )
        except Exception as e:
            logger.warning(f"Failed to save user message immediately: {e}")

        async def save_and_send(data: dict) -> None:
            nonlocal agent_responses, reasoning_by_agent
            data_type = data.get("type", "")

            # 先发送 WebSocket 消息（保证实时性）。若客户端中途断开（切换会话/
            # 关闭页面），send 会抛 RuntimeError — 吞掉它以免整个 graph 中断，
            # 后续持久化仍会继续，刷新页面即可恢复消息。
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.debug(f"WS send skipped (client gone?): {e}")

            # 然后根据类型处理持久化
            if data_type == "agent_message":
                payload = data.get("payload", {})
                content = payload.get("content", "")
                agent_name = payload.get("agent", "")
                if content:
                    # 立即保存到数据库
                    try:
                        # 构建带时间戳的组合消息格式（与用户消息配对）
                        tag = user_msg_tag  # 使用相同的 tag，确保与用户消息配对
                        combined = f"用户: {user_message}{tag}\n助手: {content}"
                        agent_meta = {
                            "agent": agent_name,
                            "source": data.get("source", ""),
                            "task_id": payload.get("task_id", ""),
                            "node_key": payload.get("node_key", ""),
                        }

                        # 如果已有 reasoning 数据，合并到 metadata
                        if agent_name and agent_name in reasoning_by_agent:
                            agent_meta.update(reasoning_by_agent[agent_name])

                        await mm.save_memory(
                            level=MemoryLevel.context,
                            content=combined,
                            type=MemoryType.context,
                            team_id=session.team_id,
                            session_id=session_id,
                            importance=0.5,
                            created_by="system",
                            metadata_=agent_meta,
                        )
                        # 立即提交这个保存（不等到整个事务结束）
                        await db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to save agent message immediately: {e}")

                    # 同时收集到列表（用于后续统计和兼容）
                    agent_responses.append({"content": content, "agent": agent_name})

            elif data_type == "reasoning_complete":
                payload = data.get("payload", {})
                agent_name = payload.get("agent", "")
                if agent_name:
                    reasoning_by_agent[agent_name] = {
                        "thinking_steps": payload.get("thinking_steps", ""),
                        "tool_calls": payload.get("tool_calls", []),
                        "model_routing": payload.get("model_routing", {}),
                        "decision_summary": payload.get("decision_summary", ""),
                        "latency": payload.get("latency", 0),
                    }

            elif data_type == "hitl_notification" or data_type == "hitl_request":
                # 持久化 HITL 卡片数据到消息历史
                payload = data.get("payload", {})
                try:
                    hitl_msg = payload.get("message", "")
                    combined = f"⚠️ **需要您的决策**\n\n{hitl_msg}"
                    meta = {
                        "role": "system",
                        "hitl_notification": True,
                        "hitl_type": payload.get("type", "confirmation"),
                        "hitl_message": hitl_msg,
                        "hitl_options": payload.get("options", []),
                    }
                    await mm.save_memory(
                        level=MemoryLevel.context,
                        content=combined,
                        type=MemoryType.context,
                        team_id=session.team_id if session else None,
                        session_id=session_id,
                        importance=0.5,
                        created_by="system",
                        metadata_=meta,
                    )
                    await db.commit()
                except Exception as e:
                    logger.warning(f"Failed to persist HITL notification: {e}")

        # 通过 router 分流到对应引擎（swarm / supervisor / langgraph）
        try:
            # 创建 Loop Engine + Harness 横切拦截器
            from app.services.loop_engine import LoopEngine
            from app.services.harness import Harness, HarnessConfig
            loop_engine = LoopEngine()
            harness = Harness(db, save_and_send, config=HarnessConfig(), loop_engine=loop_engine)

            await router_dispatch(
                session_id=session_id,
                team=team,
                user_message=user_message,
                team_agents=team_agents,
                available_roles=available_roles,
                send_fn=save_and_send,
                harness=harness,
            )
        except Exception as e:
            import traceback
            logger.error(f"[collab_chat] Engine error: {e}\n{traceback.format_exc()}")
            await save_and_send({
                "type": "error",
                "source": "system",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": f"引擎执行错误: {str(e)}"},
            })

        # 更新会话统计（消息已在 save_and_send 中实时保存）
        if agent_responses:
            try:
                # Update message count
                prev_count = session.message_count or 0
                session.message_count = prev_count + len(agent_responses)
                # Auto-title: use first user message (exclude confirmations)
                if prev_count == 0 and session.title in ("新对话", "New Chat"):
                    title_text = user_message.strip()
                    # Only use meaningful messages as title (not confirmations)
                    if title_text and title_text not in ("确认", "ok", "好的", "/approve", "可以", "yes", "sure"):
                        session.title = title_text[:40] + ("..." if len(title_text) > 40 else "")
                await db.commit()
            except Exception:
                pass


async def _handle_hitl_resume(
    websocket,
    session_id: str,
    user_response: dict,
):
    """Resume collaboration graph after HITL interrupt.

    PR4 修复：恢复期间产生的所有 agent_message 也要持久化到 Memory，
    否则刷新后只能看到 M1 的回复（M3/M4/M6/M7 全丢失）。

    修改：使用单一 db session，实时保存每条消息。
    """
    from app.core.database import async_session
    from app.services.session_service import SessionService
    from app.services.memory_manager import MemoryManager
    from app.services.collaboration.router import dispatch_resume as router_resume
    from app.services.collaboration.engines.swarm_engine import _format_hitl_response_for_display
    from app.schemas.memory import MemoryLevel, MemoryType
    import time as _time
    import uuid as _uuid

    # 使用单一 db session 贯穿整个 resume 流程，实现实时持久化
    async with async_session() as db:
        svc = SessionService(db)
        session = await svc.get_session(_uuid.UUID(session_id))
        if not session:
            return
        from app.models.team import Team
        team = await db.get(Team, session.team_id)
        if not team:
            return

        mm = MemoryManager(db)

        # 先保存用户的 HITL 决策
        display_text = _format_hitl_response_for_display(user_response)
        try:
            await mm.save_memory(
                level=MemoryLevel.context,
                content=display_text,
                type=MemoryType.context,
                team_id=session.team_id,
                session_id=session_id,
                importance=0.5,
                created_by="user",
                metadata_={
                    "role": "user",
                    "hitl_response": True,
                    "hitl_type": user_response.get("hitl_type", "select"),
                    "hitl_id": user_response.get("hitl_id", ""),
                },
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save HITL user decision: {e}")

        # 收集 resume 过程中产生的 agent_message + reasoning
        agent_responses: list[dict] = []
        reasoning_by_agent: dict[str, dict] = {}
        # 用于与用户决策配对的时间戳
        user_msg_tag = f"[{_time.time_ns()}]"

        async def save_and_send(data: dict) -> None:
            nonlocal agent_responses, reasoning_by_agent
            dtype = data.get("type", "")

            # 先发送 WebSocket 消息
            await websocket.send_json(data)

            if dtype == "agent_message":
                p = data.get("payload", {})
                if p.get("content"):
                    agent_responses.append({
                        "content": p.get("content", ""),
                        "agent": p.get("agent", ""),
                        "task_id": p.get("task_id"),
                        "model": p.get("model"),
                        "latency": p.get("latency"),
                        "source": data.get("source", ""),
                    })

                    # 立即保存到数据库
                    try:
                        r = agent_responses[-1]
                        combined = f"用户{user_msg_tag}: [Internal:hitl_resume]\n助手: {r['content']}"
                        meta = {
                            "agent": r.get("agent", ""),
                            "source": r.get("source", ""),
                            "task_id": r.get("task_id"),
                            "model": r.get("model"),
                            "latency": r.get("latency"),
                        }
                        name = r.get("agent", "")
                        if name and name in reasoning_by_agent:
                            meta.update(reasoning_by_agent[name])
                        meta = {k: v for k, v in meta.items() if v is not None}

                        await mm.save_memory(
                            level=MemoryLevel.context,
                            content=combined,
                            type=MemoryType.context,
                            team_id=session.team_id,
                            session_id=session_id,
                            importance=0.5,
                            created_by="system",
                            metadata_=meta,
                        )
                        await db.commit()
                    except Exception as e:
                        logger.warning(f"Failed to save agent message during resume: {e}")

            elif dtype in ("hitl_request", "hitl_notification"):
                # 持久化 HITL 卡片数据，确保页面刷新后能重建 HITL 卡片
                p = data.get("payload", {})
                try:
                    hitl_msg = p.get("message", "")
                    combined = f"⚠️ **需要您的决策**\n\n{hitl_msg}"
                    meta = {
                        "role": "system",
                        "hitl_notification": True,
                        "hitl_type": p.get("type", "confirmation"),
                        "hitl_message": hitl_msg,
                        "hitl_options": p.get("options", []),
                    }
                    await mm.save_memory(
                        level=MemoryLevel.context,
                        content=combined,
                        type=MemoryType.context,
                        team_id=session.team_id,
                        session_id=session_id,
                        importance=0.5,
                        created_by="system",
                        metadata_=meta,
                    )
                    await db.commit()
                except Exception as e:
                    logger.warning(f"Failed to save HITL notification: {e}")

            elif dtype == "reasoning_complete":
                p = data.get("payload", {})
                name = p.get("agent", "")
                if name:
                    reasoning_by_agent[name] = {
                        "thinking_steps": p.get("thinking_steps", ""),
                        "tool_calls": p.get("tool_calls", []),
                        "model_routing": p.get("model_routing", {}),
                        "decision_summary": p.get("decision_summary", ""),
                        "latency": p.get("latency", 0),
                    }

        # 创建 Harness + Loop Engine for resume
        from app.services.loop_engine import LoopEngine as _LoopEngine2
        from app.services.harness import Harness as _Harness2, HarnessConfig as _HC2
        _loop_engine2 = _LoopEngine2()
        _harness2 = _Harness2(db, save_and_send, config=_HC2(), loop_engine=_loop_engine2)

        await router_resume(
            session_id=session_id,
            team=team,
            user_response=user_response,
            send_fn=save_and_send,
            harness=_harness2,
        )

        # 更新消息计数（消息已在 save_and_send 中实时保存）
        if agent_responses:
            try:
                session.message_count = (session.message_count or 0) + len(agent_responses) + 1
                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update session message count: {e}")
