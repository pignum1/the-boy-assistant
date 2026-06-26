"""协作引擎总路由

按 team.collaboration_mode 分流到对应引擎。

分发策略：
- "swarm"      → swarm_engine
- "langgraph"  → langgraph_engine
- 其他（包括 "supervisor"、"round_robin"、"custom_sop"、None）
              → supervisor_engine（默认）
"""

import logging
from typing import Callable, Awaitable

from app.services.collaboration.engines import ENGINES, DEFAULT_ENGINE

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]

# 模式 → 引擎模块映射（延迟导入）
_MODE_ENGINE_MAP: dict[str, str] = {
    "swarm":      "swarm_engine",
    "langgraph":  "langgraph_engine",
    # supervisor 是默认兜底，不在映射中
}


def _resolve_engine(mode: str):
    """解析模式到引擎模块（延迟导入）。"""
    mode = (mode or DEFAULT_ENGINE).lower()
    module_name = _MODE_ENGINE_MAP.get(mode, "supervisor_engine")
    import_path = f"app.services.collaboration.engines.{module_name}"

    # 动态导入
    import importlib
    return importlib.import_module(import_path)


async def dispatch(
    session_id: str,
    team,
    user_message: str,
    team_agents: list,
    available_roles: list,
    send_fn: SendFn,
    harness=None,
) -> None:
    """启动协作。根据 team.collaboration_mode 选择引擎。（可选注入 Harness）"""
    mode = (team.collaboration_mode or DEFAULT_ENGINE).lower()
    logger.info("[router] dispatch session=%s mode=%s", session_id[:8], mode)

    engine = _resolve_engine(mode)
    await engine.run(
        session_id=session_id,
        team=team,
        user_message=user_message,
        team_agents=team_agents,
        available_roles=available_roles,
        send_fn=send_fn,
        harness=harness,
    )


async def dispatch_resume(
    session_id: str,
    team,
    user_response,  # str (legacy) or dict (structured HITL)
    send_fn: SendFn,
    harness=None,
) -> None:
    """HITL resume，按 mode 分流。（可选注入 Harness）"""
    mode = (team.collaboration_mode or DEFAULT_ENGINE).lower()
    logger.info("[router] resume session=%s mode=%s", session_id[:8], mode)

    # 标准化响应格式
    if isinstance(user_response, str):
        user_response = {
            "hitl_type": "select",
            "values": [user_response],
        }

    engine = _resolve_engine(mode)
    await engine.resume(session_id, user_response, send_fn, harness=harness)


def get_engine_info(team_or_mode) -> dict:
    """获取引擎元数据。
    接受 Team 对象（含 collaboration_mode）或直接传 mode 字符串。
    """
    from app.services.collaboration.engines import get_engine_info as _info
    mode = team_or_mode if isinstance(team_or_mode, str) else getattr(team_or_mode, "collaboration_mode", DEFAULT_ENGINE)
    return _info(mode)
