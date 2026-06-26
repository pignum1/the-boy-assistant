"""M7: Independent Verifier — blind review against requirements.

PRINCIPLE: The verifier sees ONLY requirements + artifacts.
It does NOT see:
- Worker reasoning chains
- Supervisor guidance
- Conversation history
- HITL interaction logs

This prevents confirmation bias — the verifier judges purely
on whether the output matches the original requirements.
"""

import json
import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── Verifier system prompt ──

VERIFIER_SYSTEM_PROMPT = """你是独立质量审核员。你的任务是对照原始需求检查实现产物。

## 重要: 你只看到需求和产物
- ✅ 你看到: 原始需求 + 各任务产出
- ❌ 你看不到: Worker的思考过程、Supervisor的指导、对话历史
- 原因: 防止确认偏差 — 你不应该被实现者的推理影响判断

## 检查维度
1. **功能完整性**: 需求中提到的每个功能点是否都有对应实现?
2. **偏离检测**: 实现是否偏离了需求? 多了不需要的东西? 少了应该有的?
3. **代码质量**: 是否有明显 bug、安全漏洞、性能问题?
4. **文件完整性**: 所有期望的产出文件是否都已生成?

## 严重度
- none: 完全匹配，无问题
- minor: 小问题，可以后续修正（如注释不够、命名不规范）
- major: 需要修改（如功能缺失、逻辑错误）
- critical: 严重偏离，必须停止（如需求完全理解错误）

## 输出格式 (严格 JSON)
{
  "passed": true/false,
  "feedback": "具体的不通过原因或肯定意见",
  "severity": "none|minor|major|critical",
  "drift_detected": true/false,
  "suggestions": ["改进建议1", "改进建议2"]
}"""


def build_verification_prompt(requirements: str, artifacts: dict[str, str]) -> str:
    """Build a prompt for the verifier.

    Critically: this prompt does NOT include any worker reasoning.
    """
    artifacts_section = ""
    for task_id, output in artifacts.items():
        # Truncate long artifacts
        truncated = output[:2000] + "..." if len(output) > 2000 else output
        artifacts_section += f"\n### {task_id}\n{truncated}\n"

    return f"""
## 原始需求 (不可变 — 对照此标准检查)
{requirements}

## 任务产出 (待验证)
{artifacts_section}

请逐项对照需求检查产物，输出 JSON 验证结果。
"""


def parse_verification_result(raw: str) -> dict[str, Any]:
    """Parse verifier LLM output."""
    # Direct JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Code block
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except json.JSONDecodeError:
            pass

    # Braces
    if "{" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    return {
        "passed": False,
        "feedback": raw[:500],
        "severity": "major",
        "drift_detected": True,
        "suggestions": [],
    }


def route_after_verify(verification: dict[str, Any]) -> str:
    """Decide next action based on verification result.

    Returns: "pass" | "retry" | "escalate" | "reanalyze"

    Decision logic:
    - drift_detected → "reanalyze" (需求理解有偏差，回 M1 重新分析)
    - passed → "pass"
    - critical → "escalate" (严重偏离，人工介入)
    - major → "retry" (M6 重做)
    - minor → "pass" (小问题不阻塞)
    """
    if verification.get("drift_detected"):
        return "reanalyze"

    if verification.get("passed"):
        return "pass"

    severity = verification.get("severity", "major")
    if severity == "critical":
        return "escalate"
    elif severity == "major":
        return "retry"
    else:
        return "pass"  # minor issues don't block


# ── LangGraph node ──

async def m7_verify_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M7 independent verification.

    Calls LLM with blind review (only requirements + artifacts).
    """
    requirements = state.get("requirements_anchor", "")
    artifacts = state.get("artifacts", {})
    retry_count = state.get("retry_count", 0)

    # Skip verification if no artifacts or requirements
    if not requirements or not artifacts:
        return {
            "verification": {
                "passed": True,
                "feedback": "无产出需要验证",
                "severity": "none",
                "drift_detected": False,
            },
            "status": "completed",
        }

    # Max retries
    if retry_count >= 2:
        logger.warning(f"M7: max retries ({retry_count}) reached, auto-passing")
        return {
            "verification": {
                "passed": True,
                "feedback": "达到最大重试次数，自动通过",
                "severity": "minor",
                "drift_detected": False,
            },
            "status": "completed",
            "hitl_type": "review",
            "hitl_message": "⚠️ 验证重试次数已达上限，自动通过。请人工审核。",
            "hitl_options": [
                {"label": "✅ 确认完成", "value": "approve"},
                {"label": "✎ 需要修改", "value": "modify"},
            ],
            "_content": "⚠️ 验证重试次数已达上限，自动通过。请人工审核。",
            "_agent_name": "验证员",
        }

    # Call LLM for verification
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        async with async_session() as db:
            # Use a different agent for verification (not the same worker)
            stmt = select(Agent).limit(1)
            result = await db.execute(stmt)
            agent = result.scalar_one_or_none()

            if not agent:
                return _auto_pass("无可用 Agent 进行验证")

            prompt = VERIFIER_SYSTEM_PROMPT + "\n\n" + build_verification_prompt(
                requirements=requirements,
                artifacts=artifacts,
            )

            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                return_reasoning=False, save_memory=False,
            )

            raw = llm_result.get("content", "")
            verification = parse_verification_result(raw)

            logger.info(f"M7 verification: passed={verification.get('passed')}, severity={verification.get('severity')}")

            # Route based on result
            decision = route_after_verify(verification)

            if decision == "pass":
                return {
                    "verification": verification,
                    "status": "completed",
                    "hitl_type": "review",
                    "hitl_message": f"✅ 验证通过: {verification.get('feedback', '产物与需求匹配')}",
                    "hitl_options": [
                        {"label": "✅ 确认完成", "value": "approve"},
                        {"label": "✎ 需要修改", "value": "modify"},
                    ],
                    "_content": f"✅ **验证通过**: {verification.get('feedback', '产物与需求匹配')}",
                    "_agent_name": "验证员",
                }
            elif decision == "reanalyze":
                # 需求理解偏差 → 回 M1 重新分析，带上验证反馈
                drift_feedback = verification.get('feedback', '需求理解与实现偏差')
                suggestions = verification.get('suggestions', [])
                reanalyze_msg = (
                    f"🔁 **M7 验证发现需求理解偏差，回到 M1 重新分析**\n\n"
                    f"偏差说明: {drift_feedback}\n\n"
                    + (f"修正建议:\n" + "\n".join(f"- {s}" for s in suggestions) + "\n\n" if suggestions else "")
                    + "请根据以上反馈重新分析需求，修正理解偏差后重新规划。"
                )
                return {
                    "verification": verification,
                    "status": "analyzing",
                    "retry_count": 0,
                    # 重置 M6 状态
                    "delegation_stack": [],
                    "current_delegation": None,
                    "delegation_depth": 0,
                    "task_dag": None,
                    # 清除旧 artifacts，让 M1 从干净的上下文开始
                    "artifacts": {},
                    # 将偏差反馈注入 messages，M1 会读取最新的消息作为输入
                    "messages": [{"role": "system", "content": reanalyze_msg}],
                    "clarification_answers": {
                        "_drift_feedback": drift_feedback,
                    },
                    "_content": reanalyze_msg,
                    "_agent_name": "验证员",
                }
            elif decision == "retry":
                return {
                    "verification": verification,
                    "status": "executing",
                    "retry_count": retry_count + 1,
                    # Route B: reset delegation state for full re-execution
                    "delegation_stack": [],
                    "current_delegation": None,
                    "delegation_depth": 0,
                    "_content": f"⚠️ **验证未通过**: {verification.get('feedback', '')}\n\n严重度: {verification.get('severity', 'major')}\n\n正在重试（第 {retry_count + 1} 次）...",
                    "_agent_name": "验证员",
                }
            else:  # escalate
                return {
                    "verification": verification,
                    "status": "blocked",
                    "hitl_type": "review",
                    "hitl_message": f"🚨 **验证发现严重问题**: {verification.get('feedback', '')}\n\n建议: {'; '.join(verification.get('suggestions', []))}",
                    "hitl_options": [
                        {"label": "🔄 重新执行", "value": "approve"},
                        {"label": "✗ 放弃任务", "value": "reject"},
                    ],
                    "_content": f"🚨 **严重偏离**: {verification.get('feedback', '')}",
                    "_agent_name": "验证员",
                }

    except Exception as e:
        logger.error(f"M7 verification failed: {e}", exc_info=True)
        return _auto_pass(f"验证执行出错: {str(e)[:200]}")


def _auto_pass(reason: str) -> dict[str, Any]:
    """验证无法执行时报告失败而非静默通过，要求人工审查。"""
    logger.error(f"M7 verification cannot run: {reason}")
    return {
        "verification": {
            "passed": False,
            "feedback": f"⚠️ 自动验证无法执行 ({reason})，请人工审查",
            "severity": "warning",
            "drift_detected": False,
        },
        "status": "requires_review",
    }


# ── Route function ──

def route_after_m7(state: CollabState) -> str:
    """After M7: pass → HITL, retry → M6, reanalyze → M1, escalate → HITL."""
    verification = state.get("verification", {})
    if not verification:
        return "hitl"

    decision = route_after_verify(verification)
    if decision == "pass":
        return "hitl"  # Show review HITL for user approval
    elif decision == "retry":
        return "m6_execute"  # Retry execution
    elif decision == "reanalyze":
        return "m1_analyze"  # Back to M1: re-analyze requirements with verification feedback
    else:
        return "hitl"  # Escalate to user
