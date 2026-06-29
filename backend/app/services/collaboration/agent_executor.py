"""统一 Agent 执行器 — 按配置路由到不同执行模式

支持三种执行模式：
  single_pass:   一次 LLM 调用（默认，向后兼容）
  plan_execute:  Plan → Review → Supplement 三阶段
  react:         Think → Act → Observe 循环

配置来源（优先级从高到低）：
  1. node.config.execution_mode（workflow_node 级别）
  2. agent 配置（未来扩展）
  3. 默认 single_pass
"""

import logging
from typing import Any

from app.services.agent_chat import agent_chat as _single_pass_chat
from app.services.collaboration.plan_execute_executor import PlanAndExecuteExecutor
from app.services.collaboration.react_executor import ReActExecutor

logger = logging.getLogger(__name__)

# 执行模式常量
EXEC_MODE_SINGLE = "single_pass"
EXEC_MODE_PLAN_EXECUTE = "plan_execute"
EXEC_MODE_REACT = "react"

# 模式选择规则：哪些节点/场景默认用什么模式
DEFAULT_MODES = {
    # Supervisor 管道节点
    "m1_analyze": EXEC_MODE_PLAN_EXECUTE,      # 需求分析 → Plan-and-Execute
    "m6_execute_worker": EXEC_MODE_REACT,       # Worker 执行 → ReAct
    "m6_execute": EXEC_MODE_REACT,              # M6 执行 → ReAct
    "m7_verify": EXEC_MODE_SINGLE,              # 盲审 → Single-pass
    # LangGraph 节点类型
    "agent": EXEC_MODE_SINGLE,                  # 默认
    "validation": EXEC_MODE_SINGLE,             # 校验 → Single-pass
    # Swarm
    "swarm_agent": EXEC_MODE_REACT,             # 群聊 Agent → ReAct
}


class AgentExecutor:
    """统一 Agent 执行器调度器。

    用法:
        executor = AgentExecutor()
        result = await executor.execute(
            prompt=prompt, agent=agent, db=db,
            node_key="m1_analyze",       # 用于匹配默认模式
            node_config=node_config,     # 可覆盖默认模式
        )
    """

    def __init__(self):
        self._plan_executor = PlanAndExecuteExecutor(enable_review=True, min_score=70)
        self._react_executor = ReActExecutor(max_iterations=5, enable_self_review=True)

    async def execute(
        self,
        prompt: str,
        agent,
        db,
        session_id: str = "",
        team_id: str = "",
        node_key: str = "",
        node_config: dict | None = None,
    ) -> dict[str, Any]:
        """根据配置选择执行模式。

        Args:
            prompt: LLM prompt
            agent: Agent ORM 对象
            db: 数据库会话
            node_key: 节点标识（如 "m1_analyze", "m6_execute_worker"）
            node_config: 节点配置 dict（可能包含 execution_mode 字段）

        Returns:
            {
                "content": str,       # 最终输出
                "reasoning": dict,    # 推理过程
                "exec_mode": str,     # 实际使用的模式
                "iterations": int,    # LLM 调用次数
            }
        """
        # 1. 确定执行模式
        exec_mode = self._resolve_mode(node_key, node_config)
        logger.info(f"[AgentExecutor] node={node_key} mode={exec_mode}")

        if exec_mode == EXEC_MODE_SINGLE:
            return await self._execute_single(prompt, agent, db, session_id, team_id)

        elif exec_mode == EXEC_MODE_PLAN_EXECUTE:
            result = await self._plan_executor.execute(
                prompt=prompt, agent=agent, db=db,
                session_id=session_id, team_id=team_id,
            )
            result["exec_mode"] = EXEC_MODE_PLAN_EXECUTE
            return result

        elif exec_mode == EXEC_MODE_REACT:
            result = await self._react_executor.execute(
                prompt=prompt, agent=agent, db=db,
                session_id=session_id, team_id=team_id,
            )
            # 保留 react 写入文件的 tool_calls（供 M6 _extract_file_changes 提取）
            result.setdefault("reasoning", {})
            result["exec_mode"] = EXEC_MODE_REACT
            return result

        else:
            logger.warning(f"Unknown exec_mode '{exec_mode}', falling back to single_pass")
            return await self._execute_single(prompt, agent, db, session_id, team_id)

    def _resolve_mode(self, node_key: str, node_config: dict | None) -> str:
        """解析执行模式。优先级：node_config > DEFAULT_MODES > single_pass"""
        # 1. node_config 显式指定
        if node_config and isinstance(node_config, dict):
            mode = node_config.get("execution_mode")
            if mode in (EXEC_MODE_SINGLE, EXEC_MODE_PLAN_EXECUTE, EXEC_MODE_REACT):
                return mode

        # 2. 节点类型默认模式
        if node_key:
            for pattern, mode in DEFAULT_MODES.items():
                if pattern in node_key:
                    return mode

        # 3. 兜底
        return EXEC_MODE_SINGLE

    async def _execute_single(
        self, prompt: str, agent, db, session_id: str, team_id: str
    ) -> dict[str, Any]:
        """Single-pass 模式（原有行为）。"""
        result = await _single_pass_chat(
            db=db, agent=agent, message=prompt,
            return_reasoning=True, save_memory=False,
            session_id=session_id, team_id=team_id,
        )
        return {
            "content": result.get("content", ""),
            "reasoning": result.get("reasoning", {}) or {},
            "exec_mode": EXEC_MODE_SINGLE,
            "iterations": 1,
        }


# 全局单例
agent_executor = AgentExecutor()
