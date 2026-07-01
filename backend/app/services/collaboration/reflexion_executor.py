"""Reflexion 执行器 — 执行→自我批判→重做

循环：执行任务 → 自我批判产出 → 拿批评指导重做 → 直到达标或超限。
与 Plan&Execute 的关键区别：批评的是**产出结果**，不是计划。

参数:
  max_reflections: int = 3  最大反思次数
"""
import logging
from typing import Any

from app.services.agent_chat import agent_chat
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

DEFAULT_MAX_REFLECTIONS = 3

CRITIQUE_PROMPT = """你是一位严格的审查员。请审查以下产出，找出问题和不足。

## 原始任务
{task}

## 当前产出
{output}

## 审查维度
1. **正确性**: 是否满足任务要求？有没有错误？
2. **完整性**: 有没有遗漏的内容？
3. **质量**: 代码/方案是否足够好？有没有改进空间？

## 输出格式（严格 JSON）
{{
  "score": 0-100,
  "verdict": "pass|needs_improvement",
  "issues": [
    {{"problem": "具体问题", "severity": "high|medium|low", "suggestion": "改进建议"}}
  ]
}}

如果产出足够好，verdict 为 "pass"，issues 为空数组。
"""

REDO_PROMPT = """请根据以下批评意见，重新完成任务。

## 原始任务
{task}

## 之前的产出
{previous_output}

## 审查意见
{critique}

## 要求
1. 逐条处理审查意见中的每个问题
2. 保留之前产出中正确的部分
3. 输出改进后的完整内容，不要只输出修改部分
4. 不要重复审查意见

## 改进后的产出
"""


class ReflexionExecutor:
    """Reflexion 执行器。

    用法:
        executor = ReflexionExecutor()
        result = await executor.execute(
            prompt=prompt, agent=agent, db=db,
            config={"max_reflections": 3},
        )
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
        """执行 Reflexion 循环。

        Returns:
            {content, iterations, reasoning}
        """
        max_reflections = (config or {}).get("max_reflections", DEFAULT_MAX_REFLECTIONS)
        max_reflections = max(1, min(max_reflections, 5))  # 限制 1-5

        iterations = 0
        reflections: list[dict] = []

        # Round 1: 首次执行
        logger.info("[Reflexion] Round 1: initial execution")
        with TraceContext.span(name=trace_metadata.phase_span_name("reflexion", "Round1 Execute", 1), metadata=trace_metadata.phase_span_meta(mode="reflexion", phase_name="Round1 Execute", phase_index=1)):
            result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=True, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
        iterations += 1
        content = (result.get("content") or "").strip()
        reasoning = result.get("reasoning", {}) or {}

        for r in range(max_reflections):
            # Self-critique
            logger.info(f"[Reflexion] Critique round {r+1}")
            with TraceContext.span(name=trace_metadata.phase_span_name("reflexion", f"Critique Round {r+1}"), metadata=trace_metadata.phase_span_meta(mode="reflexion", phase_name="Critique", phase_index=r+1)):
                critique_message = CRITIQUE_PROMPT.format(task=prompt, output=content[:6000])
                critique_result = await agent_chat(
                    db=db, agent=agent, message=critique_message,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=team_id,
                )
            iterations += 1

            critique = self._parse_critique(
                (critique_result.get("content") or "").strip(),
            )
            reflections.append(critique)

            score = critique.get("score", 0)
            verdict = critique.get("verdict", "needs_improvement")
            issues = critique.get("issues", [])
            logger.info(
                f"[Reflexion] round {r+1}: score={score} verdict={verdict} issues={len(issues)}"
            )

            # 达标则结束
            if verdict == "pass" or score >= 85 or not issues:
                logger.info(f"[Reflexion] passed at round {r+1}")
                break

            # Redo with critique
            logger.info(f"[Reflexion] Redo round {r+2}")
            with TraceContext.span(name=trace_metadata.phase_span_name("reflexion", f"Redo Round {r+2}"), metadata=trace_metadata.phase_span_meta(mode="reflexion", phase_name="Redo", phase_index=r+2)):
                issues_text = "\n".join(
                    f"- [{i.get('severity', 'medium')}] {i.get('problem', '')}\n  建议: {i.get('suggestion', '')}"
                    for i in issues
                )
                redo_message = REDO_PROMPT.format(
                    task=prompt, previous_output=content[:4000], critique=issues_text,
                )
                redo_result = await agent_chat(
                    db=db, agent=agent, message=redo_message,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=team_id,
                )
            iterations += 1
            content = (redo_result.get("content") or content).strip()

        return {
            "content": content,
            "iterations": iterations,
            "reasoning": {
                **reasoning,
                "reflections": reflections,
            },
        }

    def _parse_critique(self, raw: str) -> dict:
        """从 LLM 输出中解析审查 JSON。"""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
            if raw.endswith("```"):
                raw = raw[:-3]
        try:
            import json
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start:end + 1])
        except Exception:
            logger.warning("[Reflexion] Failed to parse critique JSON")
        return {"score": 0, "verdict": "needs_improvement", "issues": []}
