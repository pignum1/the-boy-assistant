"""M4: Task Decomposer — LLM-driven DAG generation.

Takes confirmed requirements + M1's phases_plan,
calls architect LLM to produce an executable task DAG.

Includes: topological sort, cycle detection, DAG validation.
"""

import json
import logging
from collections import defaultdict, deque
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── System prompt for architect LLM ──

DECOMPOSE_SYSTEM_PROMPT = """你是架构师。将确认的需求分解为具体可执行的任务 DAG。

## 要求
1. 每个任务有明确的文件/接口产出
2. 标注任务间依赖 (depends_on: [task_id])
3. 无依赖的任务标记 parallel=true
4. 为每个任务分配角色 (assigned_role: architect|backend_dev|frontend_dev|tester|devops|pm)
5. 每个任务有验收标准

## 输出格式 (严格 JSON)
{
  "phases": [
    {
      "id": "phase_design",
      "name": "架构设计",
      "parallel": false,
      "tasks": [
        {
          "id": "task_1",
          "title": "设计数据库表结构",
          "description": "设计 users 表结构，包含 id(UUID), email, password_hash 字段。输出到 DB_DESIGN.md",
          "assigned_role": "architect",
          "depends_on": [],
          "expected_output": "workspace/DB_DESIGN.md",
          "parallel": false
        }
      ]
    }
  ]
}

## 任务类型与阶段数
- feature_request → 2-5 个阶段 (需求→架构→实现→测试)
- bug_fix → 2-3 个阶段 (定位→修复→验证)
- refactor → 3-6 个阶段 (审计→方案→重构→测试)
- question → 1 个阶段 (直接回答)
"""


# ── DAG validation ──

def validate_no_cycles(phases: list[dict[str, Any]]) -> list[str]:
    """Check for circular dependencies in task DAG.

    Returns list of cycle descriptions (empty = valid).
    """
    all_tasks: dict[str, set[str]] = {}

    for phase in phases:
        for task in phase.get("tasks", []):
            task_id = task.get("id", "")
            deps = set(task.get("depends_on", []))
            all_tasks[task_id] = deps

    # Topological sort to detect cycles
    in_degree: dict[str, int] = defaultdict(int)
    for task_id, deps in all_tasks.items():
        for dep in deps:
            if dep in all_tasks:
                in_degree[task_id] += 1

    queue = deque([tid for tid in all_tasks if in_degree[tid] == 0])
    sorted_count = 0

    while queue:
        task_id = queue.popleft()
        sorted_count += 1
        for tid, deps in all_tasks.items():
            if task_id in deps:
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    queue.append(tid)

    if sorted_count != len(all_tasks):
        remaining = [tid for tid in all_tasks if in_degree[tid] > 0]
        return [f"检测到循环依赖，涉及任务: {', '.join(remaining)}"]

    return []


def topological_sort(phases: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Sort tasks into dependency levels for parallel execution.

    Level 0: tasks with no dependencies → can run in parallel
    Level 1: tasks depending only on Level 0 → can run in parallel
    etc.

    Returns list of levels, each level is a list of tasks that can run in parallel.
    """
    # Collect all tasks
    all_tasks: dict[str, dict[str, Any]] = {}
    for phase in phases:
        for task in phase.get("tasks", []):
            all_tasks[task["id"]] = task

    # Calculate in-degree
    in_degree: dict[str, int] = defaultdict(int)
    for task_id, task in all_tasks.items():
        for dep in task.get("depends_on", []):
            if dep in all_tasks:
                in_degree[task_id] += 1

    # BFS by levels
    queue = deque([tid for tid in all_tasks if in_degree[tid] == 0])
    levels: list[list[dict[str, Any]]] = []

    while queue:
        level_tasks = []
        level_size = len(queue)

        for _ in range(level_size):
            task_id = queue.popleft()
            level_tasks.append(all_tasks[task_id])

            # Decrement in-degree of dependents
            for tid, task in all_tasks.items():
                if task_id in task.get("depends_on", []):
                    in_degree[tid] -= 1
                    if in_degree[tid] == 0:
                        queue.append(tid)

        levels.append(level_tasks)

    return levels


# ── LLM decomposition ──

def build_decompose_prompt(requirements: str, roles: list[str], phases_plan: list[dict]) -> str:
    """Build prompt for architect LLM to decompose tasks."""
    phases_hint = ""
    if phases_plan:
        phases_hint = f"""
## 建议阶段计划（来自 Supervisor 分析，可灵活调整）
{json.dumps(phases_plan, ensure_ascii=False, indent=2)}
"""

    return f"""
## 确认的需求（不可变 — 这是执行基准）
{requirements}
{phases_hint}
## 可用角色
{', '.join(roles)}

请将上述需求分解为可执行的任务 DAG，输出 JSON 格式。
确保:
1. 无循环依赖
2. 每个任务分配给存在的角色
3. 无依赖的任务可以并行执行
4. 每个任务有明确的产出文件或接口
"""


def parse_dag_output(raw: str) -> dict[str, Any]:
    """Parse LLM DAG output (handles JSON-in-markdown)."""
    # Direct JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Markdown code block
    if "```json" in raw:
        start = raw.index("```json") + 7
        end = raw.index("```", start)
        try:
            return json.loads(raw[start:end].strip())
        except json.JSONDecodeError:
            pass

    # Braces extraction
    if "{" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse DAG output: {raw[:200]}")


def validate_dag(dag: dict[str, Any]) -> list[str]:
    """Validate DAG structure. Returns list of errors (empty = valid)."""
    errors = []
    phases = dag.get("phases", [])
    if not phases:
        errors.append("DAG has no phases")
        return errors

    for i, phase in enumerate(phases):
        tasks = phase.get("tasks", [])
        if not tasks:
            errors.append(f"Phase {i} ('{phase.get('name', '?')}') has no tasks")
            continue
        for task in tasks:
            if not task.get("id"):
                errors.append(f"Task in phase {i} missing 'id'")
            if not task.get("title"):
                errors.append(f"Task {task.get('id', '?')} missing 'title'")
            if not task.get("assigned_role"):
                errors.append(f"Task {task.get('id', '?')} missing 'assigned_role'")

    # Cycle check
    cycle_errors = validate_no_cycles(phases)
    errors.extend(cycle_errors)

    return errors


# ── LangGraph node ──

async def m4_decompose_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M4 task decomposition.

    Calls architect LLM to decompose requirements into task DAG.
    Falls back to single-task plan if LLM fails.

    PR5 介入闭环：若 state 中有 delta_plan，则把 delta 应用到现有 task_dag
    （而非从零生成），保留已完成任务的产物。
    """
    # ── PR5 介入路径：应用 delta_plan ──
    delta_plan = state.get("delta_plan")
    existing_dag = state.get("task_dag", {})
    if delta_plan and existing_dag and existing_dag.get("phases"):
        from .m1_rebalance import apply_delta_to_task_dag
        new_dag = apply_delta_to_task_dag(existing_dag, delta_plan)
        logger.info(f"M4: applied delta_plan, new tasks={sum(len(p.get('tasks', [])) for p in new_dag.get('phases', []))}")
        # 清理 delta_plan 防止下一轮 M4 重复应用
        return {
            "status": "executing",
            "task_dag": new_dag,
            "delta_plan": None,
            "interrupt_message": None,
            "_content": f"📋 已应用修改：{delta_plan.get('summary', '')}",
            "_agent_name": "架构师",
        }

    # Build requirements from state
    requirements = state.get("requirements_anchor", "")
    if not requirements:
        msgs = state.get("messages", [])
        parts = []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content", "")
                if c not in ("确认", "ok", "好的", "可以", "yes", "sure", "好的"):
                    parts.append(f"用户需求: {c}")
        requirements = "\n\n".join(parts) if parts else "根据对话上下文执行任务"

    required_roles = state.get("required_roles", ["backend_dev"])
    phases_plan = state.get("phases_plan", [])

    # Try LLM decomposition
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        # Find architect agent
        agent_assignments = state.get("agent_assignments", {})
        architect_info = agent_assignments.get("architect")

        async with async_session() as db:
            agent = None
            if architect_info:
                agent_id = architect_info.get("agent_id")
                if agent_id:
                    stmt = select(Agent).where(Agent.id == agent_id)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
            if not agent:
                stmt = select(Agent).where(Agent.status == "idle").limit(1)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if agent:
                prompt = DECOMPOSE_SYSTEM_PROMPT + "\n\n" + build_decompose_prompt(
                    requirements=requirements,
                    roles=required_roles,
                    phases_plan=phases_plan,
                )

                llm_result = await agent_chat(
                    db=db, agent=agent, message=prompt,
                    return_reasoning=True, save_memory=False,
                )

                raw = llm_result.get("content", "")
                try:
                    dag = parse_dag_output(raw)
                    errors = validate_dag(dag)
                    if errors:
                        logger.warning(f"M4 DAG validation errors: {errors}")
                    else:
                        logger.info(f"M4: generated DAG with {sum(len(p.get('tasks', [])) for p in dag.get('phases', []))} tasks")
                        # Persist architecture design to workspace root as ARCHITECTURE.md
                        try:
                            from app.services.workspace.manager import workspace_manager
                            import os as _os, json as _json
                            _sid = state.get("session_id", "")
                            if _sid:
                                _ws = workspace_manager.get_workspace(_sid)
                                if _ws and getattr(_ws, "path", None):
                                    _os.makedirs(_ws.path, exist_ok=True)
                                    _ap = _os.path.join(_ws.path, "ARCHITECTURE.md")
                                    with open(_ap, "w", encoding="utf-8") as f:
                                        f.write("# 架构设计文档\n\n## 需求\n" + requirements + "\n\n")
                                        f.write("## 任务分解 (DAG)\n\n```json\n" +
                                                _json.dumps(dag, ensure_ascii=False, indent=2) + "\n```\n")
                                    logger.info(f"M4 ARCHITECTURE.md saved to {_ap}")
                        except Exception as _e:
                            logger.warning(f"Failed to save ARCHITECTURE.md: {_e}")
                        return {
                            "status": "executing",
                            "task_dag": dag,
                            "requirements_anchor": requirements,
                            "_content": _format_dag_summary(dag),
                            "_agent_name": "架构师",
                            "_reasoning": {
                                "supervisor_analysis": f"任务分解完成: {sum(len(p.get('tasks', [])) for p in dag.get('phases', []))} 个任务",
                                "thinking_steps": llm_result.get("reasoning", {}).get("thinking_steps", ""),
                            },
                        }
                except ValueError as e:
                    logger.warning(f"M4 DAG parse failed: {e}")

    except Exception as e:
        logger.error(f"M4 LLM decomposition failed: {e}", exc_info=True)

    # Fallback: single-task plan
    logger.info("M4: falling back to single-task plan")
    fallback_dag = {
        "phases": [{
            "id": "phase_impl",
            "name": "实现",
            "parallel": False,
            "tasks": [{
                "id": "task_main",
                "title": "执行主要任务",
                "description": requirements[:500],
                "assigned_role": required_roles[0] if required_roles else "backend_dev",
                "depends_on": [],
                "expected_output": "代码实现",
                "parallel": False,
            }],
        }]
    }

    return {
        "status": "executing",
        "task_dag": fallback_dag,
        "requirements_anchor": requirements,
        "_content": f"📋 任务分解完成（简化模式）: 1 个阶段, 1 个任务",
        "_agent_name": "架构师",
    }


def _format_dag_summary(dag: dict) -> str:
    """Format DAG as readable summary for the chat."""
    phases = dag.get("phases", [])
    total_tasks = sum(len(p.get("tasks", [])) for p in phases)
    lines = [f"📋 **任务分解完成**: {len(phases)} 个阶段, {total_tasks} 个任务\n"]

    for i, phase in enumerate(phases, 1):
        phase_name = phase.get("name", f"阶段{i}")
        tasks = phase.get("tasks", [])
        lines.append(f"**阶段 {i}: {phase_name}**")
        for t in tasks:
            role = t.get("assigned_role", "?")
            title = t.get("title", "?")
            deps = t.get("depends_on", [])
            dep_str = f" (依赖: {', '.join(deps)})" if deps else ""
            lines.append(f"  - `{role}` → {title}{dep_str}")
        lines.append("")

    return "\n".join(lines)


# ── Route function ──

def route_after_m4(state: CollabState) -> str:
    """After M4: proceed to execution."""
    return "m6_execute"
