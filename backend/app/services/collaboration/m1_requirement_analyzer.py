"""M1: Requirement Analyzer — LLM brain with workflow template injection.

Analyzes user messages, consults team workflow templates,
and outputs a structured decision for LangGraph routing.

Preserves: parse_supervisor_output(), validate_supervisor_output()
           from the original supervisor_analyzer.py.
"""

import json
import logging
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── System prompt for Supervisor LLM ──

SUPERVISOR_SYSTEM_PROMPT = """你是团队主管(Supervisor)。你的职责是:
1. 理解用户意图，总结需求
2. 提出整体方案和阶段计划
3. 只在关键信息确实缺失、影响方案可行性时才提问澄清
4. 匹配需要的角色
5. 输出结构化 JSON 决策

## 核心原则
- **先理解，提方案**: 先总结用户要做什么，给出大体的方案思路和执行计划
- **尽量确认而非澄清**: 技术细节(端口号、字段名、颜色等)可用合理默认值，不需要提问
- **只在阻塞时才问**: 只有当某个决策直接影响方案可行性时才需要澄清（如：用REST还是GraphQL？单租户还是多租户？）
- **clarity_score > 0.7 通常直接确认**: 大多数有经验的开发者需求都应高于此阈值
- **每次只输出一个决策**: 不要一次输出多个 action

## 决策类型
{
  "action": "need_clarify" | "need_confirm" | "execute_task" | "done" | "invite_agent"
}

## 输出格式 (严格JSON)

### need_clarify (仅在关键信息缺失时使用，最多3个问题)
{
  "action": "need_clarify",
  "summary": "已理解的需求概述",
  "plan_outline": "当前设想的方案思路",
  "questions": ["关键阻塞问题1", "关键阻塞问题2"],
  "clarity_score": 0.5,
  "reasoning": "为什么这些是关键问题"
}

### need_confirm (正常流程，给出完整方案)
{
  "action": "need_confirm",
  "problem_type": "feature_request|bug_fix|refactor|question",
  "complexity": "simple|medium|complex",
  "summary": "需求摘要",
  "plan_outline": "整体方案概述",
  "required_roles": ["architect", "backend_dev"],
  "phases": [
    {"name": "架构设计", "role": "architect", "goal": "DB+API设计"}
  ],
  "clarity_score": 0.85,
  "hitl_message": "展示给用户的确认消息"
}

### execute_task
{
  "action": "execute_task",
  "tasks": [
    {
      "id": "task_1",
      "title": "任务标题",
      "description": "精确的任务描述",
      "assigned_role": "architect",
      "depends_on": [],
      "expected_output": "产出文件"
    }
  ],
  "guidance": "给Worker的执行指导"
}

### invite_agent
{
  "action": "invite_agent",
  "missing_roles": ["frontend_dev"],
  "hitl_message": "缺少前端工程师，是否邀请？"
}

### done
{
  "action": "done",
  "summary": "任务已完成"
}
"""


# ── Prompt builders ──

def build_analysis_prompt(
    user_message: str,
    roster: str,
    context: str = "",
    workflow_template: dict | None = None,
) -> str:
    """Build the analysis prompt for M1, injecting workflow template if available."""
    template_section = ""
    if workflow_template:
        template_section = f"""
## 团队协作流程参考（来自团队工作流模板）
{json.dumps(workflow_template, ensure_ascii=False, indent=2)}

**注意**: 以上模板仅供参考。你可以：
- 沿用模板的阶段划分
- 根据实际需求裁剪/合并/跳过阶段
- 根据需求增加模板中没有的步骤
"""

    return f"""
## 团队可用角色
{roster}
{template_section}
## 对话上下文
{context or "(新对话)"}

## 用户消息
{user_message}

请分析需求并输出 JSON 决策。
如果信息不够，action=need_clarify，提出具体问题，并给出 clarity_score（0~1）。
如果信息足够，action=need_confirm，给出完整分析和 phases 计划，并给出 clarity_score（0~1）。
"""


def build_team_roster(team_agents: list[dict]) -> str:
    """Build team roster string for the prompt."""
    if not team_agents:
        return "pm, architect, backend_dev, frontend_dev, tester"

    lines = []
    for a in team_agents:
        name = a.get("name", "?")
        role = a.get("role", "?")
        lines.append(f"- {name}: {role}")
    return "\n".join(lines)


def build_conversation_context(messages: list[dict], limit: int = 6) -> str:
    """Build conversation context from recent messages."""
    if len(messages) <= 1:
        return ""

    recent = messages[-limit:]
    return "\n".join(
        f"{'用户' if m.get('role') == 'user' else 'Agent'}: {str(m.get('content', ''))[:200]}"
        for m in recent[:-1]  # Exclude current message
    )


# ── LLM output parsing ──

def parse_supervisor_output(raw_output: str) -> dict[str, Any]:
    """Parse Supervisor LLM output into structured dict.

    Handles: clean JSON, JSON-in-markdown, JSON-in-braces.
    """
    # Try direct JSON parse
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    if "```json" in raw_output:
        start = raw_output.index("```json") + 7
        end = raw_output.index("```", start)
        try:
            return json.loads(raw_output[start:end].strip())
        except json.JSONDecodeError:
            pass

    # Try extracting from curly braces
    if "{" in raw_output:
        start = raw_output.index("{")
        end = raw_output.rindex("}") + 1
        try:
            return json.loads(raw_output[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse Supervisor output: {raw_output[:200]}")


def validate_supervisor_output(data: dict[str, Any]) -> list[str]:
    """Validate required fields based on action type.

    Returns list of validation errors (empty = valid).
    """
    errors = []

    if "action" not in data:
        errors.append("Missing 'action' field")
        return errors

    action = data["action"]

    if action == "need_clarify":
        if not data.get("questions"):
            errors.append("need_clarify requires 'questions' list")
        if data.get("clarity_score") is None:
            errors.append("need_clarify requires 'clarity_score'")

    elif action == "need_confirm":
        required = ["problem_type", "complexity", "summary", "required_roles"]
        for field in required:
            if field not in data:
                errors.append(f"need_confirm requires '{field}'")
        if data.get("clarity_score") is None:
            errors.append("need_confirm requires 'clarity_score'")

    elif action == "execute_task":
        if not data.get("tasks"):
            errors.append("execute_task requires 'tasks' list")
        for task in data.get("tasks", []):
            if "assigned_role" not in task:
                errors.append(f"Task missing 'assigned_role': {task.get('title', '?')}")

    elif action not in ("done", "invite_agent"):
        errors.append(f"Unknown action: {action}")

    return errors


def supervisor_decision_to_state(decision: dict[str, Any]) -> dict[str, Any]:
    """Convert M1 LLM output to CollabState field updates."""
    action = decision.get("action", "need_confirm")
    updates: dict[str, Any] = {
        "status": {
            "need_clarify": "clarifying",
            "need_confirm": "awaiting_confirm",
            "execute_task": "executing",
            "done": "completed",
            "invite_agent": "clarifying",
        }.get(action, "analyzing"),
    }

    if action == "need_clarify":
        import re
        updates["hitl_type"] = "clarification"
        questions = decision.get("questions", [])
        # Strip existing numbering (LLM often outputs "1. xxx" already)
        cleaned = [re.sub(r'^\d+[\.\)、]\s*', '', str(q)).strip() for q in questions]
        updates["hitl_message"] = "\n".join(
            f"{i+1}. {q}" for i, q in enumerate(cleaned)
        )
        updates["hitl_options"] = [
            {"label": "我来回答", "value": "answer"},
        ]
        updates["clarity_score"] = decision.get("clarity_score", 0.3)

    elif action == "need_confirm":
        updates["problem_type"] = decision.get("problem_type", "")
        updates["complexity"] = decision.get("complexity", "medium")
        updates["analysis_summary"] = decision.get("summary", "")
        updates["required_roles"] = decision.get("required_roles", [])
        updates["phases_plan"] = decision.get("phases", [])
        updates["clarity_score"] = decision.get("clarity_score", 0.8)
        updates["hitl_type"] = "confirmation"

        # ── 组装可读的分析确认内容 ──
        summary = decision.get("summary", "")
        problem_type = updates["problem_type"]
        complexity = updates["complexity"]
        required_roles = updates["required_roles"]
        phases = updates["phases_plan"]

        plan_outline = decision.get("plan_outline", "")
        parts = []
        if summary:
            parts.append(f"📋 **分析摘要**: {summary}")
        if plan_outline:
            parts.append(f"💡 **整体方案**: {plan_outline}")
        if problem_type:
            type_labels = {
                "feature_request": "功能开发",
                "bug_fix": "Bug 修复",
                "refactoring": "代码重构",
                "architecture": "架构设计",
                "testing": "测试",
                "documentation": "文档",
                "deployment": "部署运维",
                "analysis": "分析调研",
            }
            parts.append(f"🏷️ **问题类型**: {type_labels.get(problem_type, problem_type)}")
        if complexity:
            comp_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(complexity, "⚪")
            parts.append(f"{comp_emoji} **复杂度**: {complexity}")

        if required_roles:
            role_labels = {
                "product_manager": "产品经理",
                "ui_designer": "UI 设计师",
                "architect": "架构师",
                "backend_dev": "后端工程师",
                "frontend_dev": "前端工程师",
                "tester": "测试员",
                "devops": "部署运维",
            }
            roles_str = "、".join(role_labels.get(r, r) for r in required_roles)
            parts.append(f"👥 **需要的角色**: {roles_str}")

        if phases:
            parts.append("")
            parts.append("📅 **执行计划**:")
            for i, phase in enumerate(phases):
                phase_name = phase.get("name", f"阶段 {i+1}")
                parts.append(f"  {i+1}. {phase_name}")
                for task in phase.get("tasks", []):
                    task_title = task.get("title", task.get("name", ""))
                    assigned = task.get("assigned_role", "")
                    if task_title:
                        assigned_label = role_labels.get(assigned, assigned) if assigned else ""
                        parts.append(f"     ├→ {task_title}" + (f" ({assigned_label})" if assigned_label else ""))

        if parts:
            hitl_msg = "\n".join(parts)
        else:
            hitl_msg = decision.get("hitl_message", "需求分析完成，请确认是否正确。")

        updates["hitl_message"] = hitl_msg
        updates["hitl_options"] = [
            {"label": "✅ 确认", "value": "approve"},
            {"label": "✎ 修改", "value": "modify"},
            {"label": "✗ 重新来", "value": "reject"},
        ]
        # Low clarity warning
        if updates["clarity_score"] < 0.7:
            updates["hitl_message"] += (
                "\n\n⚠️ 当前信息完整度较低，建议确认后再进入执行。"
            )

    elif action == "execute_task":
        tasks = decision.get("tasks", [])
        updates["task_dag"] = {
            "phases": [
                {"id": "phase_0", "name": "执行任务", "tasks": tasks}
            ]
        }
        if decision.get("guidance"):
            updates["requirements_anchor"] = decision["guidance"]

    elif action == "invite_agent":
        updates["missing_roles"] = decision.get("missing_roles", [])
        updates["hitl_type"] = "agent_invite"
        updates["hitl_message"] = decision.get(
            "hitl_message",
            f"缺少以下角色: {', '.join(decision.get('missing_roles', []))}，是否邀请？",
        )
        updates["hitl_options"] = [
            {"label": "📋 邀请Agent", "value": "invite"},
            {"label": "🆕 创建Agent", "value": "create"},
            {"label": "⏭ 跳过", "value": "skip"},
        ]

    elif action == "done":
        updates["status"] = "completed"

    return updates


# ── LangGraph node ──

async def m1_analyze_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M1 requirement analysis.

    Calls Supervisor LLM with workflow template context,
    parses structured output, converts to state updates.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"status": "completed"}

    last_msg = messages[-1]
    user_message = last_msg.get("content", "") if isinstance(last_msg, dict) else str(messages[-1])

    team_agents = state.get("team_agents", [])
    workflow_template = state.get("workflow_template")

    # Build prompt components
    roster = build_team_roster(team_agents)
    context = build_conversation_context(messages)
    full_prompt = SUPERVISOR_SYSTEM_PROMPT + "\n\n" + build_analysis_prompt(
        user_message=user_message,
        roster=roster,
        context=context,
        workflow_template=workflow_template,
    )

    # Call LLM
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from app.models.model import Model as ModelModel
        from sqlalchemy import select
        import uuid as _uuid

        async with async_session() as db:
            # ── 选择用于 M1 分析的 Agent ──
            # 优先从 team_agents 选择，避免选到 test-model Agent
            agent = None
            team_agents = state.get("team_agents", [])

            # 策略 1: 使用 team_agents 中第一个 agent
            if team_agents:
                first_id = team_agents[0].get("agent_id")
                if first_id:
                    try:
                        stmt = select(Agent).where(Agent.id == _uuid.UUID(first_id))
                        result = await db.execute(stmt)
                        agent = result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        pass

            # 策略 2: 找任意一个使用非 test provider 模型的 Agent
            if not agent:
                stmt = (
                    select(Agent)
                    .join(ModelModel, Agent.default_model_id == ModelModel.id)
                    .where(ModelModel.provider != "test")
                    .limit(1)
                )
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                logger.warning("No agent found for M1, using stub")
                return _stub_response(user_message)

            llm_result = await agent_chat(
                db=db, agent=agent, message=full_prompt,
                return_reasoning=True, save_memory=False,
            )

            # Parse LLM output
            raw_content = llm_result.get("content", "")
            reasoning = llm_result.get("reasoning", {})

            try:
                decision = parse_supervisor_output(raw_content)
            except ValueError:
                logger.warning(f"M1 parse failed, using raw content. Raw: {raw_content[:200]}")
                decision = {
                    "action": "need_confirm",
                    "summary": raw_content[:500],
                    "clarity_score": 0.8,
                }

            # If user approved on clarification HITL, force confirmation mode
            if state.get("force_confirm"):
                decision["action"] = "need_confirm"
                decision["clarity_score"] = max(decision.get("clarity_score", 0.8), 0.8)
                logger.info("M1: force_confirm flag set, forcing need_confirm")

            # Validate
            errors = validate_supervisor_output(decision)
            if errors:
                logger.warning(f"M1 validation errors: {errors}")

            # Convert to state updates
            updates = supervisor_decision_to_state(decision)

            # Inject LLM reasoning for frontend display
            # supervisor_analysis: prioritize thinking_steps (full reasoning),
            # then decision_summary, then raw content
            thinking_steps = reasoning.get("thinking_steps", "")
            decision_summary = reasoning.get("decision_summary", "")
            analysis_for_frontend = thinking_steps or decision_summary or raw_content[:1000]

            updates["_reasoning"] = {
                "thinking_steps": thinking_steps,
                "model_routing": reasoning.get("model_routing", {}),
                "tool_calls": reasoning.get("tool_calls", []),
                "latency": reasoning.get("latency", 0),
                "supervisor_analysis": analysis_for_frontend,
            }
            updates["_content"] = updates.get("hitl_message", updates.get("analysis_summary", ""))
            # Use actual agent name, not the internal node name
            agent_display_name = agent.name if agent else "Supervisor"
            updates["_agent_name"] = agent_display_name
            updates["_model"] = llm_result.get("model", "")
            updates["_latency"] = llm_result.get("latency", 0)

            # ── Auto-save analysis to workspace ROOT (PRD.md, no per-agent folder) ──
            try:
                from app.services.workspace.manager import workspace_manager
                import os as _os
                session_id = state.get("session_id", "")
                if session_id:
                    ws = workspace_manager.get_workspace(session_id)
                    if ws and getattr(ws, 'path', None):
                        _os.makedirs(ws.path, exist_ok=True)
                        filepath = _os.path.join(ws.path, "PRD.md")
                        content = f"# 产品需求文档 (PRD)\n\n## 任务\n{state.get('messages', [{}])[-1].get('content', '') if state.get('messages') else ''}\n\n{updates.get('_content', '')}\n\n"
                        if updates.get("_reasoning", {}).get("thinking_steps"):
                            content += f"\n## 分析推理\n\n{updates['_reasoning']['thinking_steps']}\n"
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(content)
                        logger.info(f"M1 PRD saved to {filepath}")
            except Exception as e:
                logger.warning(f"Failed to save M1 analysis to workspace: {e}")

            return updates

    except Exception as e:
        logger.error(f"M1 LLM call failed: {e}", exc_info=True)
        return _stub_response(user_message)


def _stub_response(user_message: str) -> dict[str, Any]:
    """Fallback when LLM is unavailable."""
    return {
        "status": "awaiting_confirm",
        "problem_type": "feature_request",
        "complexity": "medium",
        "analysis_summary": "需求分析完成，请确认是否正确。",
        "clarity_score": 0.6,
        "required_roles": ["architect", "backend_dev"],
        "phases_plan": [],
        "hitl_type": "confirmation",
        "hitl_message": (
            "📋 **分析摘要**: 需求分析完成\n"
            "🏷️ **问题类型**: 功能开发\n"
            "🟡 **复杂度**: medium\n"
            "👥 **需要的角色**: 架构师、后端工程师\n"
            "\n"
            "⚠️ LLM 暂不可用，以上为默认分析结果。"
        ),
        "hitl_options": [
            {"label": "✅ 确认", "value": "approve"},
            {"label": "✎ 修改", "value": "modify"},
            {"label": "✗ 重新来", "value": "reject"},
        ],
        "_content": "需求分析完成，请确认是否正确。",
        "_agent_name": "产品经理-Agent",
        "_reasoning": {
            "thinking_steps": (
                "1. 接收到用户请求，正在分析需求类型...\n"
                f"2. 用户消息: \"{user_message[:100]}\"\n"
                "3. 判断为代码编写类需求（功能开发）\n"
                "4. 复杂度评估: medium — 单一功能实现\n"
                "5. 需要角色: 架构师（设计）、后端工程师（编码）\n"
                "6. ⚠️ LLM 服务暂不可用，使用默认分析"
            ),
            "model_routing": {"complexity": "medium", "selected_model": "stub"},
            "tool_calls": [],
            "latency": 0,
            "supervisor_analysis": (
                "分析用户需求: 代码编写类任务\n"
                "问题类型: 功能开发\n"
                "复杂度: medium\n"
                "⚠️ LLM 暂不可用"
            ),
        },
    }


# ── Route function for graph edges ──

def route_after_m1(state: CollabState) -> str:
    """Determine next node after M1.

    Returns:
        "m2_clarify"  → clarity too low, need clarification
        "hitl"        → need user confirmation / invite agent
        "__end__"     → done
    """
    hitl_type = state.get("hitl_type", "")
    if hitl_type == "clarification":
        return "m2_clarify"
    if hitl_type in ("confirmation", "agent_invite", "review"):
        return "hitl"
    if state.get("status") == "completed":
        return "__end__"
    return "hitl"  # Default: show HITL card
