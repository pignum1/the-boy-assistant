"""节点执行器：实现各种节点类型的执行逻辑

DDD 设计原则：
1. 每个执行器只负责自己的节点类型
2. 通过 ExecutionContext 获取外部数据
3. 返回标准化的执行结果
4. 不直接依赖其他领域的模型
"""

import logging
import uuid
import asyncio
from typing import Optional, Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workflow import WorkflowNode, WorkflowEdge
from app.models.workflow_instance import WorkflowInstance
from app.models.agent import Agent
from app.services.workflow_engine import NodeExecutor, ExecutionContext

logger = logging.getLogger(__name__)


# 执行结果标准格式
def execution_result(
    output: Optional[dict] = None,
    next_edge_type: str = "Forward",
    next_node_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> dict:
    """构造标准化的执行结果"""
    result = {
        "next_edge_type": next_edge_type,
    }
    if output:
        result["output"] = output
    if next_node_id:
        result["next_node_id"] = next_node_id
    if agent_id:
        result["agent_id"] = agent_id
    return result


class StartNodeExecutor(NodeExecutor):
    """开始节点执行器"""

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        """开始节点只做标记，直接流转"""
        logger.info(f"Starting workflow instance {instance.id}")

        return execution_result(
            output={"message": "Workflow started"},
        )


class EndNodeExecutor(NodeExecutor):
    """结束节点执行器"""

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        """结束节点，完成工作流"""
        logger.info(f"Ending workflow instance {instance.id}")

        return execution_result(
            output={"message": "Workflow completed"},
        )


class AgentNodeExecutor(NodeExecutor):
    """Agent 节点执行器

    职责：
    1. 根据节点配置获取 Agent
    2. 调用 Agent 执行任务
    3. 返回执行结果
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}

        # 获取 Agent ID
        agent_id_str = config.get("agent_id")
        if not agent_id_str:
            raise ValueError("Agent node requires agent_id in config")

        agent_id = uuid.UUID(agent_id_str)

        # 获取 Agent 信息
        agent_info = await context.get_agent(agent_id)
        if not agent_info:
            raise ValueError(f"Agent {agent_id} not found")

        logger.info(f"Executing Agent node '{node.label}' with agent {agent_info['name']}")

        # 构建 prompt
        prompt_template = config.get("prompt_template", "请处理用户输入：{user_input}")
        prompt = prompt_template.format(
            user_input=context.user_input or "",
            **state,
        )

        # 调用 Agent
        try:
            from app.services.agent_chat import agent_chat
            from app.models.agent import Agent

            # 获取完整的 Agent 对象
            agent = await context.db.get(Agent, agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            # 调用 Agent 对话
            response = await agent_chat(
                db=context.db,
                agent=agent,
                message=prompt,
                session_id=str(context.session_id) if context.session_id else None,
                return_reasoning=True,
            )

            # 提取结果
            output = {
                "response": response.get("content", ""),
                "agent_name": agent_info.get("name"),
            }

            # 如果有推理过程，也包含在输出中
            if response.get("reasoning"):
                output["reasoning"] = response["reasoning"]

            return execution_result(
                output=output,
                agent_id=str(agent_id),
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise


class RouterNodeExecutor(NodeExecutor):
    """路由节点执行器

    职责：
    1. 根据配置的策略选择下一个节点
    2. 支持多种路由策略：round_robin, priority, semantic, workload
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}
        strategy = config.get("strategy", "priority")
        candidates = config.get("candidates", [])
        fallback = config.get("fallback")

        logger.info(f"Router node '{node.label}' using strategy: {strategy}")

        # 根据策略选择目标
        target_agent_id = await self._select_target(
            strategy=strategy,
            candidates=candidates,
            context=context,
            state=state,
        )

        if not target_agent_id and fallback:
            target_agent_id = fallback

        if not target_agent_id:
            raise ValueError("Router failed to select target")

        # 查找目标 Agent 节点
        # 这里简化处理，实际应该查找 downstream 的 Agent 节点
        # 返回目标节点 ID（假设 candidates 是节点 ID）
        return execution_result(
            next_node_id=target_agent_id,
            output={"routed_to": target_agent_id},
        )

    async def _select_target(
        self,
        strategy: str,
        candidates: list,
        context: ExecutionContext,
        state: dict,
    ) -> Optional[str]:
        """根据策略选择目标"""
        if not candidates:
            return None

        if strategy == "round_robin":
            # 轮询：使用状态中的计数器
            count = state.get("_router_round_robin", 0)
            target = candidates[count % len(candidates)]
            state["_router_round_robin"] = count + 1
            return target

        elif strategy == "priority":
            # 优先级：选择第一个可用的
            for candidate in candidates:
                # 检查 Agent 是否可用
                agent_info = await context.get_agent(candidate)
                if agent_info:
                    return candidate
            return None

        elif strategy == "workload":
            # 工作负载：选择任务最少的（简化处理，返回随机）
            import random
            return random.choice(candidates)

        else:
            # 默认返回第一个
            return candidates[0] if candidates else None


class ConditionNodeExecutor(NodeExecutor):
    """条件节点执行器

    职责：
    1. 根据表达式评估条件
    2. 返回对应的下一个节点
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}
        expression = config.get("expression", "")
        branches = config.get("branches", {})

        logger.info(f"Condition node '{node.label}' evaluating: {expression}")

        # 评估条件（简化处理）
        # 实际应该使用更安全的表达式评估器
        try:
            # 从状态中获取值
            condition_value = state.get(expression)

            # 查找匹配的分支
            target = branches.get(str(condition_value)) or branches.get(condition_value)

            if not target:
                # 默认分支
                target = branches.get("default")

            if not target:
                raise ValueError(f"No matching branch for condition value: {condition_value}")

            return execution_result(
                next_node_id=target,
                output={"condition_result": condition_value},
            )

        except Exception as e:
            logger.error(f"Condition evaluation failed: {e}")
            raise


class ValidationNodeExecutor(NodeExecutor):
    """验证节点执行器

    职责：
    1. 验证上一个节点的输出
    2. 根据验证结果决定流转
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}
        validator = config.get("validator", "LLM")
        criteria = config.get("criteria", [])
        on_fail = config.get("on_fail", "reject")

        logger.info(f"Validation node '{node.label}' with criteria: {criteria}")

        # 获取待验证的内容
        content_to_validate = state.get("last_output") or str(state)

        # 根据验证器类型执行验证
        if validator == "LLM":
            # 使用 LLM 验证
            passed = await self._llm_validate(
                content=content_to_validate,
                criteria=criteria,
                context=context,
            )
        elif validator == "Rule":
            # 使用规则验证
            passed = self._rule_validate(
                content=content_to_validate,
                criteria=criteria,
            )
        else:
            # Agent 验证
            agent_id = config.get("validator_agent_id")
            if agent_id:
                passed = await self._agent_validate(
                    agent_id=agent_id,
                    content=content_to_validate,
                    criteria=criteria,
                    context=context,
                )
            else:
                passed = False

        if passed:
            return execution_result(
                output={"validation": "passed"},
            )
        else:
            # 验证失败，根据配置决定处理方式
            if on_fail == "reject":
                return execution_result(
                    next_edge_type="Reject",
                    output={"validation": "failed"},
                )
            elif on_fail == "retry":
                # 重试上一个节点（需要特殊处理）
                return execution_result(
                    next_node_id=state.get("_last_node_id"),
                    output={"validation": "failed, retrying"},
                )
            else:  # escalate
                return execution_result(
                    next_edge_type="Escalate",
                    output={"validation": "failed, escalating"},
                )

    async def _llm_validate(
        self, content: str, criteria: list, context: ExecutionContext
    ) -> bool:
        """使用 LLM 验证"""
        from app.adapters.llm.litellm_adapter import LiteLLMAdapter

        llm = LiteLLMAdapter()

        prompt = f"""请验证以下内容是否满足以下标准：

标准：{', '.join(criteria)}

内容：{content}

返回 JSON 格式：{{"passed": true/false, "reason": "原因"}}"""

        try:
            response = await llm.acomplete(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            result = response.get("content", "{}")
            import json
            data = json.loads(result)
            return data.get("passed", False)
        except Exception as e:
            logger.error(f"LLM validation failed: {e}")
            return False

    def _rule_validate(self, content: str, criteria: list) -> bool:
        """使用规则验证"""
        # 简化处理：检查内容是否包含所有关键词
        for criterion in criteria:
            if criterion.lower() not in content.lower():
                return False
        return True

    async def _agent_validate(
        self, agent_id: str, content: str, criteria: list, context: ExecutionContext
    ) -> bool:
        """使用 Agent 验证"""
        # 调用 Agent 进行验证
        agent_info = await context.get_agent(uuid.UUID(agent_id))
        if not agent_info:
            return False

        # 实现类似 LLM 验证的逻辑
        return await self._llm_validate(content, criteria, context)


class HITLNodeExecutor(NodeExecutor):
    """人工介入节点执行器

    职责：
    1. 暂停执行，等待人工输入
    2. 支持超时处理
    3. 支持超时后升级
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}
        action_type = config.get("action_type", "approve")
        timeout = config.get("timeout", 3600)
        escalation_target = config.get("escalation_target")

        logger.info(f"HITL node '{node.label}' action: {action_type}")

        # 设置 HITL 状态
        instance.hitl_pending = True
        instance.hitl_node_id = node.id
        instance.hitl_action_type = action_type
        instance.hitl_timeout_at = datetime.now(timezone.utc).timestamp() + timeout
        await self.db.commit()

        # 发送 HITL 请求事件（如果有事件回调）
        # 注意：这里我们通过 context 发送事件，而不是依赖全局 engine
        # 实际使用时应该通过 WorkflowEngine 的事件回调来处理
        try:
            # 尝试通过 metadata 发送事件（如果设置了）
            if hasattr(context, 'event_callback') and context.event_callback:
                await context.event_callback("hitl.required", {
                    "instance_id": str(instance.id),
                    "node_id": str(node.id),
                    "action_type": action_type,
                    "timeout": timeout,
                    "data": state,
                })
        except Exception as e:
            logger.debug(f"Failed to emit HITL event: {e}")

        # 等待人工响应（这里简化处理，实际应该使用消息队列）
        # 返回等待状态，调用方需要处理
        return execution_result(
            output={"hitl": "pending", "action_type": action_type},
        )


class ParallelNodeExecutor(NodeExecutor):
    """并行节点执行器

    职责：
    1. 并行执行多个分支
    2. 合并分支结果
    3. 支持多种合并策略
    """

    async def execute(
        self,
        node: WorkflowNode,
        instance: WorkflowInstance,
        state: dict,
        context: ExecutionContext,
    ) -> dict:
        config = node.config or {}
        branches = config.get("branches", [])
        merge_strategy = config.get("merge_strategy", "all")
        timeout = config.get("timeout", 300)

        logger.info(f"Parallel node '{node.label}' with {len(branches)} branches")

        # 执行所有分支
        branch_results = []

        for branch in branches:
            # 每个分支是一个节点序列
            branch_result = await self._execute_branch(
                branch=branch,
                instance=instance,
                state=state,
                context=context,
            )
            branch_results.append(branch_result)

        # 合并结果
        merged_result = self._merge_results(
            results=branch_results,
            strategy=merge_strategy,
        )

        return execution_result(
            output={"parallel_result": merged_result},
        )

    async def _execute_branch(
        self, branch: list, instance: WorkflowInstance, state: dict, context: ExecutionContext
    ) -> dict:
        """执行单个分支"""
        # 简化处理：只执行分支的第一个节点
        # 实际应该执行整个节点序列
        branch_state = state.copy()

        for step in branch:
            step_type = step.get("type")
            step_config = step.get("config", {})

            if step_type == "Agent":
                # 创建临时 Agent 节点
                from app.models.workflow import WorkflowNode
                temp_node = WorkflowNode(
                    type="Agent",
                    label=step.get("label", "Branch Agent"),
                    config=step_config,
                )
                executor = AgentNodeExecutor()
                result = await executor.execute(
                    node=temp_node,
                    instance=instance,
                    state=branch_state,
                    context=context,
                )
                branch_state.update(result.get("output", {}))

        return branch_state

    def _merge_results(self, results: list, strategy: str) -> dict:
        """合并分支结果"""
        if strategy == "all":
            # 等待所有分支完成，返回所有结果
            return {"results": results, "merged": "all"}
        elif strategy == "first":
            # 返回第一个完成的结果
            return results[0] if results else {}
        elif strategy == "majority":
            # 返回大多数的结果（简化处理）
            return results[len(results) // 2] if results else {}
        else:
            return {"results": results}
