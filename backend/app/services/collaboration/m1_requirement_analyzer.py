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

SUPERVISOR_SYSTEM_PROMPT = """你是资深产品经理(PM)兼技术主管。你的职责是深度分析需求并输出专业的需求分析报告。

## 你的核心能力
1. **需求洞察**：不只复述用户的话，要挖掘隐含需求、边界条件、非功能性要求
2. **方案设计**：给出具体可执行的技术方案，包含架构选型理由、关键决策、风险点
3. **任务拆解**：将方案拆解为可独立执行的任务，明确每个任务的输入/输出/验收标准
4. **角色匹配**：根据任务特点分配合适的角色

## 输出原则
- **详尽优于简洁**：分析报告应该足够详细，让后续的 Agent 可以直接按报告执行，不需要反复追问
- **具体优于抽象**：不说"设计数据库"，说"设计 users/roles/permissions 三张表，包含字段X/Y/Z"
- **有理由的决策**：每个技术选择都要说明为什么，不列清单式的"方案A/B/C"
- **尽量确认而非澄清**：技术细节(端口号、字段名等)可用合理默认值，只在阻塞性问题时才提问

## 输出格式

你必须输出一个 JSON 对象，包含 `action` 字段和对应的详细内容。

### need_clarify（仅在关键决策缺失时使用）
```json
{
  "action": "need_clarify",
  "analysis_report": "已理解的部分需求分析（Markdown格式）",
  "questions": [
    {"question": "阻塞性问题", "context": "为什么这个问题很关键", "default_answer": "如果用户不回答，默认采用什么方案"}
  ],
  "clarity_score": 0.5
}
```

### need_confirm（正常流程，输出完整分析报告）
```json
{
  "action": "need_confirm",
  "problem_type": "feature_request",
  "complexity": "medium",
  "clarity_score": 0.85,
  "required_roles": ["architect", "backend_dev"],
  "phases": [
    {
      "name": "阶段名称",
      "role": "负责角色",
      "goal": "阶段目标（具体可衡量）",
      "tasks": ["具体任务1", "具体任务2"],
      "expected_output": "产出物清单",
      "acceptance_criteria": ["验收标准1", "验收标准2"]
    }
  ],
  "analysis_report": "## 需求分析报告\n\n### 1. 需求理解\n...\n\n### 2. 技术方案\n...\n\n（完整的 Markdown 文档，见下方模板）",
  "hitl_message": "展示给用户的简短确认消息（1-2句话）"
}
```

## 分析报告模板 (analysis_report 字段)

你的 analysis_report 必须按以下结构输出，每个部分都要足够详细：

```
## 1. 需求理解与范围定义
### 1.1 用户核心目标
- 用户想要达成什么（用自己的话重述，体现你的理解）

### 1.2 功能范围
- 包含哪些功能（具体列出）
- 不包含哪些功能（明确边界）

### 1.3 非功能性需求
- 性能要求（如并发量、响应时间）
- 安全要求（如认证方式、数据加密）
- 可维护性要求

## 2. 技术方案设计
### 2.1 整体架构
- 技术栈选型及理由（每个选择都要有理由）
- 系统架构概述

### 2.2 核心数据模型
- 关键实体及其关系
- 核心表结构概要

### 2.3 关键设计决策 (ADR)
- 决策1：为什么选X不选Y
- 决策2：...

### 2.4 风险点与缓解措施
- 技术风险
- 业务风险

## 3. 任务分解与执行计划
### 3.1 阶段划分
- 每个阶段的输入、输出、验收标准
- 阶段间的依赖关系

### 3.2 详细任务清单
| 阶段 | 任务 | 负责人 | 预估工时 | 前置依赖 | 验收标准 |
|------|------|--------|---------|----------|---------|
| ... | ... | ... | ... | ... | ... |

## 4. API 契约概要（如适用）
- 核心 API 端点列表
- 请求/响应格式概要
```

## 示例（参考风格）

用户说"做一个用户认证系统"，好的分析报告应该是：

```
## 1. 需求理解与范围定义
### 1.1 用户核心目标
构建一个完整的用户认证与授权系统，支持用户注册、登录、Token管理、基于角色的权限控制(RBAC)。

### 1.2 功能范围
包含：用户注册(邮箱+密码)、JWT登录(access+refresh token双Token机制)、角色管理(CRUD)、权限分配(用户-角色-权限多对多)、Token自动刷新、登出(token黑名单)
不包含：OAuth2.0第三方登录、SSO单点登录、MFA多因素认证、前端登录页面

### 1.3 非功能性需求
- 并发：支持500 QPS的认证请求
- 安全：密码bcrypt加密、JWT HS256签名、refresh token rotation
- 响应时间：登录接口P99 < 500ms
...（持续展开）

## 2. 技术方案设计
### 2.1 整体架构
后端：FastAPI + SQLAlchemy 2.0 + PostgreSQL
认证：python-jose (JWT) + passlib (密码哈希)
理由：FastAPI原生支持JWT验证依赖注入，PostgreSQL成熟稳定

### 2.2 核心数据模型
- users: id, email, password_hash, is_active, created_at
- roles: id, name, description
- permissions: id, resource, action
- user_roles: user_id, role_id (多对多)
- role_permissions: role_id, permission_id (多对多)

### 2.3 关键设计决策
ADR-001: 双Token机制(access 15min + refresh 7day) — 平衡安全性和用户体验
ADR-002: refresh token rotation — 每次刷新颁发新refresh token，旧token失效，防重放攻击

...（持续展开）
```

**重要**：分析报告的详细程度直接决定后续 Agent 的执行质量。宁可多写，不要省略。
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

    return f"""## 团队可用角色
{roster}
{template_section}
## 对话上下文
{context or "(新对话)"}

## 用户消息
{user_message}

---

请以资深产品经理的身份，深度分析以上需求，输出完整的需求分析报告。

要求：
1. **analysis_report 字段必须是完整的 Markdown 文档**，包含需求理解、技术方案、任务分解、API契约四个章节，每个章节都要具体可执行，不要一两句话带过
2. **phases 字段是给后续 M4 任务分解用的结构化数据**，每个 phase 要有 name/role/goal/tasks/expected_output/acceptance_criteria
3. 如果用户需求描述很简短（如"做一个用户认证系统"），请基于行业最佳实践**主动补充**典型的功能范围和技术方案，而不是问一堆澄清问题
4. 技术栈默认采用 Python FastAPI + PostgreSQL + JWT，除非用户明确要求其他技术栈
5. 输出必须是合法 JSON，analysis_report 内的 Markdown 需要正确转义换行符

如果信息不够（clarity_score < 0.5），action=need_clarify，提出关键阻塞问题。
如果信息足够，action=need_confirm，给出完整分析和 phases 计划。
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
        clarity_val = decision.get("clarity_score", 0.3)
        updates["clarity_score"] = clarity_val
        # ── 评分：需求清晰度 ──
        from app.services.trace_context import TraceContext
        TraceContext.score("clarity_score", clarity_val, comment="需求分析: 信息不足需澄清")

    elif action == "need_confirm":
        updates["problem_type"] = decision.get("problem_type", "")
        updates["complexity"] = decision.get("complexity", "medium")
        updates["analysis_summary"] = decision.get("summary", "")
        updates["required_roles"] = decision.get("required_roles", [])
        updates["phases_plan"] = decision.get("phases", [])
        clarity_val = decision.get("clarity_score", 0.8)
        updates["clarity_score"] = clarity_val
        updates["hitl_type"] = "confirmation"
        # ── 评分：需求清晰度 ──
        from app.services.trace_context import TraceContext
        TraceContext.score("clarity_score", clarity_val, comment="需求分析完成，等待用户确认")

        # ── 组装可读的分析确认内容 ──
        # prompt 不产出 summary（用 analysis_report 代替），这里做兜底
        summary = decision.get("summary", "") or decision.get("hitl_message", "")
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
                # 防御：LLM 可能把 phase 输出为字符串而非对象
                if isinstance(phase, dict):
                    phase_name = phase.get("name", f"阶段 {i+1}")
                    phase_tasks = phase.get("tasks", []) or []
                else:
                    phase_name = str(phase) if phase else f"阶段 {i+1}"
                    phase_tasks = []
                parts.append(f"  {i+1}. {phase_name}")
                for task in phase_tasks:
                    # 防御：prompt 模板里 tasks 是字符串数组，但代码曾按对象取值
                    if isinstance(task, dict):
                        task_title = task.get("title", task.get("name", ""))
                        assigned = task.get("assigned_role", "")
                    else:
                        task_title = str(task)
                        assigned = ""
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

            # ── AgentExecutor 统一调度 (按节点类型自动选择执行模式) ──
            from app.services.collaboration.agent_executor import agent_executor as _exec

            pe_result = await _exec.execute(
                prompt=full_prompt,
                agent=agent,
                db=db,
                session_id=state.get("session_id", ""),
                team_id=state.get("team_id", ""),
                node_key="m1_analyze",
            )

            # Parse LLM output
            raw_content = pe_result.get("content", "")
            reasoning = pe_result.get("reasoning", {})
            logger.info(
                f"M1 exec_mode={pe_result.get('exec_mode')} "
                f"iterations={pe_result.get('iterations', 1)}"
            )

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
            # supervisor_analysis: 优先展示完整的 PM 分析报告（analysis_report），
            # 其次推理过程，最后兜底原始内容
            analysis_report_md = decision.get("analysis_report", "") if isinstance(decision, dict) else ""
            thinking_steps = reasoning.get("thinking_steps", "")
            decision_summary = reasoning.get("decision_summary", "")
            analysis_for_frontend = analysis_report_md or thinking_steps or decision_summary or raw_content[:1000]

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
            updates["_model"] = reasoning.get("model_routing", {}).get("selected_model", "") if reasoning else ""
            updates["_latency"] = reasoning.get("latency", 0) if reasoning else 0

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
