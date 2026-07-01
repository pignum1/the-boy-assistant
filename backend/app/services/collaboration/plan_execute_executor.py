"""Plan-and-Execute Agent 执行器

实现三阶段执行模式：
  Phase 1 (Plan):   LLM 深入分析，产出详细计划
  Phase 2 (Review): 自我审查，识别遗漏和薄弱点
  Phase 3 (Execute):补充完善，输出最终方案

设计原则：
- 不改变 Engine 层的调度逻辑
- 对外暴露统一的 execute(prompt, agent, db) 接口
- 可配置是否启用审查阶段
"""

import json
import logging
from typing import Any

from app.services.agent_chat import agent_chat
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

# ── Self-Review Prompt ──

REVIEW_PROMPT = """你是一位严格的架构审查员。请审查以下需求分析报告，找出不足之处。

## 审查维度
1. **完整性**: 是否覆盖了需求理解、技术方案、任务分解、API契约？
2. **深度**: 每个部分是否足够具体？是否有"一句话带过"的敷衍？
3. **可执行性**: 后续 Agent 能否仅凭这份报告就开始工作？是否需要反复追问？

## 审查规则
- 只指出真正缺失或不足的部分，不要为了挑刺而挑刺
- 对每个问题，给出具体的补充建议
- 如果报告已经足够完善，明确说"报告完善，无需补充"

## 待审查报告
{report}

## 输出格式（严格JSON）
{{
  "score": 0-100,
  "verdict": "good|acceptable|needs_improvement",
  "gaps": [
    {{"section": "问题所在章节", "issue": "具体什么问题", "suggestion": "建议如何补充"}}
  ]
}}

如果报告完善，gaps 为空数组，verdict 为 "good"。
"""

SUPPLEMENT_PROMPT = """以下是一份需求分析报告和审查意见。请补充报告中不足的部分。

## 原始报告
{report}

## 审查意见
{gaps}

## 要求
1. 针对每个 gap 给出具体补充内容
2. 补充内容应该可以无缝插入原始报告
3. 不要重复原始报告中已有的内容
4. 输出补充后的完整内容（Markdown格式），不要输出 JSON

## 补充内容
"""


class PlanAndExecuteExecutor:
    """Plan-and-Execute 执行器。

    用法:
        executor = PlanAndExecuteExecutor()
        result = await executor.execute(
            prompt=full_prompt, agent=agent, db=db,
            config={"enable_review": True, "min_score": 70},
        )
    """

    def __init__(self):
        pass

    async def execute(
        self,
        prompt: str,
        agent,
        db,
        session_id: str = "",
        team_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        # 从 config 读取参数，兜底默认值
        enable_review = (config or {}).get("enable_review", True)
        min_score = (config or {}).get("min_score", 70)
        """执行 Plan-and-Execute 流程。

        Returns:
            {
                "content": str,           # 最终报告内容
                "reasoning": dict,        # 推理过程
                "review_score": int | None,  # 审查评分（如果启用了审查）
                "iterations": int,        # 总 LLM 调用次数
            }
        """
        iterations = 0

        # ── Phase 1: Plan（初始分析）──
        logger.info("[Plan&Execute] Phase 1: Plan")
        with TraceContext.span(name=trace_metadata.phase_span_name("plan_execute", "Plan", 1), metadata=trace_metadata.phase_span_meta(mode="plan_execute", phase_name="Plan", phase_index=1, total_phases=3)):
            plan_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=True, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
        iterations += 1
        content = plan_result.get("content", "")
        reasoning = plan_result.get("reasoning", {}) or {}

        if not enable_review:
            return {
                "content": content,
                "reasoning": reasoning,
                "review_score": None,
                "iterations": iterations,
            }

        # ── Phase 2: Review（自我审查）──
        logger.info("[Plan&Execute] Phase 2: Review")
        with TraceContext.span(name=trace_metadata.phase_span_name("plan_execute", "Review", 2), metadata=trace_metadata.phase_span_meta(mode="plan_execute", phase_name="Review", phase_index=2, total_phases=3)):
            review_prompt = REVIEW_PROMPT.format(report=content[:8000])
            review_result = await agent_chat(
                db=db, agent=agent, message=review_prompt,
                return_reasoning=False, save_memory=False,
                session_id=session_id, team_id=team_id,
            )
        iterations += 1

        # 解析审查结果
        review_content = review_result.get("content", "").strip()
        try:
            review_json = self._parse_json(review_content)
            score = review_json.get("score", 0)
            verdict = review_json.get("verdict", "needs_improvement")
            gaps = review_json.get("gaps", [])
        except (json.JSONDecodeError, KeyError):
            # 解析失败 → 直接返回原始报告
            logger.warning("[Plan&Execute] Review parse failed, returning plan as-is")
            return {
                "content": content,
                "reasoning": reasoning,
                "review_score": None,
                "iterations": iterations,
            }

        logger.info(f"[Plan&Execute] Review: score={score}, verdict={verdict}, gaps={len(gaps)}")

        # 如果报告足够好 → 直接返回
        if score >= min_score and verdict == "good":
            return {
                "content": content,
                "reasoning": reasoning,
                "review_score": score,
                "iterations": iterations,
            }

        # ── Phase 3: Supplement（补充完善）──
        if gaps:
            logger.info(f"[Plan&Execute] Phase 3: Supplement ({len(gaps)} gaps)")
            with TraceContext.span(name=trace_metadata.phase_span_name("plan_execute", "Supplement", 3), metadata=trace_metadata.phase_span_meta(mode="plan_execute", phase_name="Supplement", phase_index=3, total_phases=3)):
                gaps_text = "\n".join(
                    f"{i+1}. [{g['section']}] {g['issue']}\n   建议: {g['suggestion']}"
                    for i, g in enumerate(gaps)
                )
                supplement_prompt = SUPPLEMENT_PROMPT.format(
                    report=content[:6000],
                    gaps=gaps_text,
                )
                supplement_result = await agent_chat(
                    db=db, agent=agent, message=supplement_prompt,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=team_id,
                )
            iterations += 1
            supplement_text = supplement_result.get("content", "")

            # 保留原始 JSON 结构用于路由解析，仅增强 analysis_report 字段
            try:
                original_json = self._parse_json(content)
                if original_json and "analysis_report" in original_json:
                    original_json["analysis_report"] = (
                        original_json["analysis_report"] + "\n\n## 补充完善\n" + supplement_text
                    )
                    content = json.dumps(original_json, ensure_ascii=False)
                else:
                    content = supplement_text or content
            except (json.JSONDecodeError, KeyError):
                content = supplement_text or content

        return {
            "content": content,
            "reasoning": reasoning,
            "review_score": score,
            "iterations": iterations,
        }

    def _parse_json(self, raw: str) -> dict:
        """从 LLM 输出中提取 JSON 对象。"""
        raw = raw.strip()
        # 移除 markdown 代码块标记
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
            if raw.endswith("```"):
                raw = raw[:-3]
        # 找到 JSON 对象的起止位置
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        return json.loads(raw)
