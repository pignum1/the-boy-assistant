"""三协作引擎：swarm / supervisor / langgraph

统一接口契约（每个引擎必须实现）：

    async def run(session_id, team, user_message, team_agents, available_roles, send_fn) -> None
    async def resume(session_id, user_response, send_fn) -> None
    def has_paused(session_id) -> bool
    def cancel_paused(session_id) -> bool

顶层 router.dispatch() 根据 team.collaboration_mode 选择引擎。

模块结构：
- swarm_engine.py      — 群聊辩论式（AutoGen 风格）
- supervisor_engine.py  — 主管管道式（M0-M7 LangGraph）
- langgraph_engine.py   — 图编排式（预定义 DAG）
- langgraph_pause.py    — HITL 暂停/恢复持久化（langgraph 专用）
"""

# 引擎元数据
ENGINES = {
    "swarm": {
        "name": "群聊模式",
        "emoji": "💬",
        "description": "多 Agent 自由讨论协作，适合头脑风暴和开放设计",
        "has_hitl": True,
    },
    "supervisor": {
        "name": "主管模式",
        "emoji": "👑",
        "description": "Leader 分析任务 → 委派成员执行，适合多角色项目开发",
        "has_hitl": True,
    },
    "langgraph": {
        "name": "工作流模式",
        "emoji": "🔀",
        "description": "预定义 DAG 编排执行，适合已知 SOP 和合规流程",
        "has_hitl": True,
    },
}

# 默认引擎（未知模式时的兜底）
DEFAULT_ENGINE = "supervisor"


def get_engine_info(mode: str) -> dict:
    """获取引擎元数据（供前端展示）。"""
    return ENGINES.get(mode, ENGINES[DEFAULT_ENGINE])
