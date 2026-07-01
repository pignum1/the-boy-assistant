"""ReWOO 执行器 — Reasoning WithOut Observation

一次性列出所有步骤 + 所需工具调用，批量执行，最后汇总。
比 ReAct 快（省去 N-1 次观察反馈的 LLM 调用），适合工具调用明确的场景。

无额外参数。
"""
import json
import logging
from typing import Any

from app.services.agent_chat import agent_chat
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

REWOO_SYSTEM_PROMPT = """你是一个具备批量规划执行能力的 AI Agent。

## 执行模式
你采用 ReWOO (Reasoning WithOut Observation) 模式工作：
1. 一次性分析任务，列出所有需要执行的具体步骤
2. 对每个步骤，说明需要调用什么工具、传入什么参数
3. 系统会批量执行所有工具调用，然后你需要汇总结果

## 输出格式
你必须输出以下 JSON 格式：

```json
{
  "analysis": "对任务的整体分析",
  "steps": [
    {
      "step": 1,
      "description": "这一步做什么",
      "tool": "工具名称（如 file-ops）",
      "params": {"key": "value"}
    }
  ]
}
```

如果没有需要调用的工具，steps 为空数组。

## 规则
- 步骤之间可以有依赖（后面的步骤使用前面步骤的输出）
- 明确写出每个工具调用的完整参数
- 如果不需要工具，直接输出最终答案
"""

MERGE_PROMPT = """以下是对任务的分析和工具执行结果。请根据这些结果，输出最终答案。

## 原始任务
{task}

## 执行计划
{plan}

## 工具执行结果
{results}

## 最终答案
"""


class ReWOOExecutor:
    """ReWOO 执行器。

    用法:
        executor = ReWOOExecutor()
        result = await executor.execute(prompt=prompt, agent=agent, db=db)
    """

    async def execute(
        self,
        prompt: str,
        agent,
        db,
        session_id: str = "",
        team_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        """执行 ReWOO 流程。

        Returns:
            {content, iterations, reasoning}
        """
        iterations = 0

        # Phase 1: 规划 —— 一次性列出所有步骤和工具
        logger.info("[ReWOO] Phase 1: Plan all steps")
        with TraceContext.span(name=trace_metadata.phase_span_name("rewoo", "Plan", 1), metadata=trace_metadata.phase_span_meta(mode="rewoo", phase_name="Plan", phase_index=1, total_phases=3)):
            plan_message = f"{REWOO_SYSTEM_PROMPT}\n\n## 任务\n{prompt}"
            plan_result = await agent_chat(
                db=db, agent=agent, message=plan_message,
                return_reasoning=False, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
        iterations += 1

        plan_text = (plan_result.get("content") or "").strip()
        plan = self._parse_plan(plan_text)
        steps = plan.get("steps", [])

        if not steps:
            # 无工具调用 → 直接返回分析结果
            return {
                "content": plan.get("analysis", plan_text),
                "iterations": iterations,
                "reasoning": {"plan": plan, "tool_results": []},
            }

        logger.info(f"[ReWOO] Phase 2: Execute {len(steps)} steps in batch")

        # Phase 2: 批量执行工具调用
        with TraceContext.span(name=trace_metadata.phase_span_name("rewoo", "Execute", 2), metadata=trace_metadata.phase_span_meta(mode="rewoo", phase_name="Execute", phase_index=2, total_phases=3)):
            tool_results: list[dict] = []
            for step in steps:
                tool_name = step.get("tool", "")
                params = step.get("params", {})
                logger.info(f"[ReWOO] Step {step.get('step')}: {tool_name} {params}")

                # 执行工具调用（复用 agent_chat 的工具执行能力）
                tool_message = (
                    f"请调用工具 `{tool_name}`，参数如下：\n```json\n"
                    f"{json.dumps(params, ensure_ascii=False)}\n```\n"
                    f"只返回工具执行结果，不要添加额外内容。"
                )
                try:
                    tool_result = await agent_chat(
                        db=db, agent=agent, message=tool_message,
                        return_reasoning=False, save_memory=False,
                        session_id=session_id, team_id=team_id,
                    )
                    iterations += 1
                    tool_results.append({
                        "step": step.get("step"),
                        "tool": tool_name,
                        "params": params,
                        "result": (tool_result.get("content") or "").strip(),
                    })
                except Exception as e:
                    tool_results.append({
                        "step": step.get("step"),
                        "tool": tool_name,
                        "params": params,
                        "error": str(e),
                    })

        # Phase 3: 汇总
        logger.info("[ReWOO] Phase 3: Merge results")
        with TraceContext.span(name=trace_metadata.phase_span_name("rewoo", "Merge", 3), metadata=trace_metadata.phase_span_meta(mode="rewoo", phase_name="Merge", phase_index=3, total_phases=3)):
            results_text = "\n".join(
                f"### 步骤 {tr['step']}: {tr.get('tool', '')}\n"
                f"参数: {json.dumps(tr.get('params', {}), ensure_ascii=False)}\n"
                f"结果: {tr.get('result', tr.get('error', ''))}"
                for tr in tool_results
            )
            merge_message = MERGE_PROMPT.format(
                task=prompt, plan=plan_text[:3000], results=results_text,
            )
            merge_result = await agent_chat(
                db=db, agent=agent, message=merge_message,
                return_reasoning=False, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
        iterations += 1

        return {
            "content": (merge_result.get("content") or "").strip(),
            "iterations": iterations,
            "reasoning": {"plan": plan, "tool_results": tool_results},
        }

    def _parse_plan(self, raw: str) -> dict:
        """从 LLM 输出中提取 JSON 计划。"""
        raw = raw.strip()
        # 移除 markdown 代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
            if raw.endswith("```"):
                raw = raw[:-3]
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
        except (json.JSONDecodeError, KeyError):
            logger.warning("[ReWOO] Failed to parse plan JSON")
        return {"analysis": raw, "steps": []}
