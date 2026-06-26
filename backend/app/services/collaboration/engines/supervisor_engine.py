"""主管式引擎（CrewAI 风格）— 包装现有 M0-M7 LangGraph 流程。

直接复用 streaming.py + graph.py。team.collaboration_mode == "supervisor" 时走这里。
"""

import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]

_collab_graphs: dict = {}


def _get_collab_graph():
    if "default" not in _collab_graphs:
        from app.services.collaboration.graph import compile_graph
        from langgraph.checkpoint.memory import MemorySaver
        _collab_graphs["default"] = compile_graph(checkpointer=MemorySaver())
    return _collab_graphs["default"]


def invalidate_graph_cache():
    """清除缓存的编译图。团队配置或 Agent 绑定变更后调用。"""
    _collab_graphs.clear()
    logger.info("Supervisor graph cache invalidated")


async def run(
    session_id: str,
    team,
    user_message: str,
    team_agents: list,
    available_roles: list,
    send_fn: SendFn,
    harness=None,
) -> None:
    """启动 supervisor 流程：M0 路由 → M1 分析 → ... → M7 验证。"""
    from app.services.collaboration.streaming import stream_to_websocket
    graph = _get_collab_graph()
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 100}
    await stream_to_websocket(
        graph=graph, config=config,
        user_message=user_message,
        websocket_send_fn=send_fn,
        team_agents=team_agents,
        available_roles=available_roles,
        team_id=str(team.id),
    )


def _extract_raw_action(user_response: dict) -> str:
    """Extract the user's raw action keyword from a structured HITL response.

    _classify_hitl_response() in graph.py does keyword matching ("approve",
    "reject", "modify", etc.) on user_response. We must pass the raw value
    (e.g. "approve") rather than the display-formatted string (e.g. "选择了: approve").
    """
    hitl_type = user_response.get("hitl_type", "select")
    values = user_response.get("values", [])

    if hitl_type == "answer":
        return user_response.get("feedback", "") or user_response.get("response", "")
    elif hitl_type == "review":
        return "approve" if user_response.get("approved") else "reject"
    elif hitl_type in ("select", "multi_select"):
        return values[0] if values else ""
    elif hitl_type == "escalation":
        return values[0] if values else "retry"
    else:
        return values[0] if values else ""


async def resume(session_id: str, user_response, send_fn: SendFn, harness=None) -> None:
    """HITL resume."""
    if isinstance(user_response, dict):
        # Extract raw action keyword BEFORE display formatting, so
        # _classify_hitl_response can match "approve" / "reject" / etc.
        raw_action = _extract_raw_action(user_response)
        from app.services.collaboration.engines.swarm_engine import _format_hitl_response_for_display
        _display_text = _format_hitl_response_for_display(user_response)
        logger.info(
            f"supervisor resume session={session_id[:8]} "
            f"raw_action={raw_action} display={_display_text[:60]}"
        )
        user_response = raw_action
    from app.services.collaboration.streaming import resume_after_hitl
    graph = _get_collab_graph()
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 100}
    await resume_after_hitl(
        graph=graph, config=config,
        user_response=user_response,
        websocket_send_fn=send_fn,
    )
