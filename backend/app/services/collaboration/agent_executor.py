"""统一 Agent 执行器 — 按 Agent 配置路由到不同执行模式

支持三种执行模式：
  single_pass:   一次 LLM 调用（默认，向后兼容）
  plan_execute:  Plan → Review → Supplement 三阶段
  react:         Think → Act → Observe 循环

模式来源：**只来自 Agent 本身的 execution_mode 字段**（一处配置、处处生效）。
管道/编排层不再干预 Agent 怎么思考 —— node_key/node_config 仅作日志标签。
若 Agent 未配置或值非法，兜底 single_pass。
"""

import logging
from typing import Any

from app.services.agent_chat import agent_chat as _single_pass_chat
from app.services.collaboration.plan_execute_executor import PlanAndExecuteExecutor
from app.services.collaboration.react_executor import ReActExecutor
from app.services.collaboration.self_consistency_executor import SelfConsistencyExecutor
from app.services.collaboration.rewoo_executor import ReWOOExecutor
from app.services.collaboration.reflexion_executor import ReflexionExecutor
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

# 执行模式常量
EXEC_MODE_SINGLE = "single_pass"
EXEC_MODE_PLAN_EXECUTE = "plan_execute"
EXEC_MODE_REACT = "react"
EXEC_MODE_CHAIN_OF_THOUGHT = "chain_of_thought"
EXEC_MODE_REWOO = "rewoo"
EXEC_MODE_REFLEXION = "reflexion"
EXEC_MODE_SELF_CONSISTENCY = "self_consistency"

# 合法模式集合
_VALID_MODES = (
    EXEC_MODE_SINGLE,
    EXEC_MODE_PLAN_EXECUTE,
    EXEC_MODE_REACT,
    EXEC_MODE_CHAIN_OF_THOUGHT,
    EXEC_MODE_REWOO,
    EXEC_MODE_REFLEXION,
    EXEC_MODE_SELF_CONSISTENCY,
)


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
        self._plan_executor = PlanAndExecuteExecutor()
        self._react_executor = ReActExecutor()
        self._self_consistency_executor = SelfConsistencyExecutor()
        self._rewoo_executor = ReWOOExecutor()
        self._reflexion_executor = ReflexionExecutor()

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
        # 1. 确定执行模式 —— 只读 Agent 自身配置
        exec_mode = self.agent_execution_mode(agent)
        exec_config = self._get_execution_config(agent)
        agent_name = getattr(agent, "name", "?")
        logger.info(f"[AgentExecutor] node={node_key} agent={agent_name} mode={exec_mode}")

        # ── LangFuse: structured span with input/output ──
        agent_role = getattr(agent, "role", "")
        with TraceContext.span(
            name=trace_metadata.span_name(exec_mode, agent_name, agent_role),
            input_data={"prompt": prompt[:1000]} if prompt else None,
            metadata=trace_metadata.span_meta(
                exec_mode=exec_mode,
                agent_name=agent_name,
                agent_role=agent_role,
                node_key=node_key,
                session_id=session_id,
                team_id=team_id,
            ),
        ) as span:
            try:
                if exec_mode == EXEC_MODE_SINGLE:
                    result = await self._execute_single(prompt, agent, db, session_id, team_id, exec_mode)
                elif exec_mode == EXEC_MODE_CHAIN_OF_THOUGHT:
                    result = await self._execute_single(prompt, agent, db, session_id, team_id, exec_mode)
                elif exec_mode == EXEC_MODE_PLAN_EXECUTE:
                    result = await self._plan_executor.execute(
                        prompt=prompt, agent=agent, db=db,
                        session_id=session_id, team_id=team_id,
                        config=exec_config,
                    )
                    result["exec_mode"] = EXEC_MODE_PLAN_EXECUTE
                    result.setdefault("reasoning", {})["exec_mode"] = EXEC_MODE_PLAN_EXECUTE
                    if result.get("review_score") is not None:
                        result["reasoning"]["review_score"] = result["review_score"]
                    result["reasoning"]["iterations"] = result.get("iterations", 1)
                elif exec_mode == EXEC_MODE_REACT:
                    result = await self._react_executor.execute(
                        prompt=prompt, agent=agent, db=db,
                        session_id=session_id, team_id=team_id,
                        config=exec_config,
                    )
                    result.setdefault("reasoning", {})
                    result["exec_mode"] = EXEC_MODE_REACT
                    result["reasoning"]["exec_mode"] = EXEC_MODE_REACT
                    result["reasoning"]["history"] = result.get("history", [])
                    result["reasoning"]["iterations"] = result.get("iterations", 1)
                elif exec_mode == EXEC_MODE_SELF_CONSISTENCY:
                    result = await self._self_consistency_executor.execute(
                        prompt=prompt, agent=agent, db=db,
                        session_id=session_id, team_id=team_id,
                        config=exec_config,
                    )
                    result["exec_mode"] = EXEC_MODE_SELF_CONSISTENCY
                    result.setdefault("reasoning", {})["exec_mode"] = EXEC_MODE_SELF_CONSISTENCY
                elif exec_mode == EXEC_MODE_REWOO:
                    result = await self._rewoo_executor.execute(
                        prompt=prompt, agent=agent, db=db,
                        session_id=session_id, team_id=team_id,
                        config=exec_config,
                    )
                    result["exec_mode"] = EXEC_MODE_REWOO
                    result.setdefault("reasoning", {})["exec_mode"] = EXEC_MODE_REWOO
                elif exec_mode == EXEC_MODE_REFLEXION:
                    result = await self._reflexion_executor.execute(
                        prompt=prompt, agent=agent, db=db,
                        session_id=session_id, team_id=team_id,
                        config=exec_config,
                    )
                    result["exec_mode"] = EXEC_MODE_REFLEXION
                    result.setdefault("reasoning", {})["exec_mode"] = EXEC_MODE_REFLEXION
                else:
                    logger.warning(f"Unknown exec_mode '{exec_mode}', falling back to single_pass")
                    result = await self._execute_single(prompt, agent, db, session_id, team_id, exec_mode)

                # Record span output with actual content
                if span:
                    content = result.get("content", "")
                    reasoning = result.get("reasoning", {})
                    span.update(output={
                        "content": content[:2000] if content else "(no output)",
                        "iterations": result.get("iterations", 1),
                        "exec_mode": exec_mode,
                        "model": reasoning.get("model_routing", {}).get("selected_model", ""),
                        "latency_s": reasoning.get("latency", 0),
                        "status": "success",
                    })
                return result
            except Exception:
                if span:
                    span.update(output={"status": "failed"})
                raise

    def _get_execution_config(self, agent) -> dict | None:
        """从 Agent 读取 execution_config，兼容 ORM 对象与 dict。"""
        if isinstance(agent, dict):
            return agent.get("execution_config")
        return getattr(agent, "execution_config", None) or None

    def agent_execution_mode(self, agent) -> str:
        """从 Agent 解析执行模式（唯一来源）。

        兼容 ORM 对象与 dict；非法/缺失值兜底 single_pass。
        """
        mode = None
        if isinstance(agent, dict):
            mode = agent.get("execution_mode")
        else:
            mode = getattr(agent, "execution_mode", None)
        if mode in _VALID_MODES:
            return mode
        return EXEC_MODE_SINGLE

    # ── Chain of Thought 前缀 ──
    COT_PREFIX = "让我们一步一步思考。\n\n"

    async def _execute_single(
        self, prompt: str, agent, db, session_id: str, team_id: str,
        exec_mode: str = EXEC_MODE_SINGLE,
    ) -> dict[str, Any]:
        """Single-pass / Chain-of-Thought 模式。"""
        if exec_mode == EXEC_MODE_CHAIN_OF_THOUGHT:
            prompt = self.COT_PREFIX + prompt

        result = await _single_pass_chat(
            db=db, agent=agent, message=prompt,
            return_reasoning=True, save_memory=False,
            session_id=session_id, team_id=team_id,
        )
        return {
            "content": result.get("content", ""),
            "reasoning": {**(result.get("reasoning", {}) or {}), "exec_mode": exec_mode},
            "exec_mode": exec_mode,
            "iterations": 1,
        }


# 全局单例
agent_executor = AgentExecutor()
