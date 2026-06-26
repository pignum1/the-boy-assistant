"""M1' Rebalance — 介入后的增量重规划
=====================================

输入：
  - 原始需求 (requirements_anchor)
  - 已完成的产物 (artifacts)
  - 当前任务图 (task_dag) + 状态
  - 用户介入消息 (interrupt_message)

输出 delta_plan：
  {
    "summary": "用户的修改意图概括",
    "keep":   [task_id...],           # 已完成且不受影响的任务，原样保留
    "modify": [{"task_id", "reason", "new_version"}],
    "add":    [WorkTask...],          # 新增的任务
    "cancel": [{"task_id", "reason"}],
  }

实现策略（MVP）：
  - 调 LLM (复用 Supervisor agent) 让它分析 delta
  - 失败时降级为启发式：保留已 done 的 task，其余的列为 modify
"""

import json
import logging
import re
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


REBALANCE_PROMPT = """你是协作系统的架构师，负责处理用户的介入修改请求。

## 原始需求
{original_requirement}

## 当前任务进度
已完成的任务（含产出）：
{completed_tasks}

未完成的任务（pending/running）：
{pending_tasks}

## 用户的介入修改
"{interrupt_message}"

## 任务
分析用户的修改请求对当前任务图的影响，输出 JSON 格式的 delta_plan：

```json
{{
  "summary": "用一句话概括用户的修改意图，如 'PG→MySQL + 增加优先级字段'",
  "keep": ["已完成且不受影响的 task_id，原样保留"],
  "modify": [
    {{"task_id": "受影响、需重做的 task_id", "reason": "为什么要重做", "new_version": 2}}
  ],
  "add": [
    {{
      "id": "T_new_1", "phase_id": "phase-X",
      "name": "新增任务标题", "assigned_role": "角色名",
      "depends_on": ["前置 task_id"]
    }}
  ],
  "cancel": [
    {{"task_id": "已不需要的 task_id", "reason": "为什么取消"}}
  ]
}}
```

只输出 JSON，不要其他文字。
"""


async def m1_rebalance_node(state: CollabState) -> dict[str, Any]:
    """LangGraph 节点：M1' 增量重规划"""
    interrupt_message = state.get("interrupt_message", "")
    if not interrupt_message:
        # 没有介入消息，跳过
        return {"status": "executing"}

    original_req = state.get("requirements_anchor", "") or state.get("clarified_requirements", "")
    task_dag = state.get("task_dag", {})
    artifacts = state.get("artifacts", {})

    # 构建任务清单
    completed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for phase in task_dag.get("phases", []):
        for t in phase.get("tasks", []):
            tid = t.get("id", "")
            if tid in artifacts:
                completed.append({
                    "id": tid,
                    "name": t.get("title") or t.get("name", ""),
                    "phase": phase.get("name", ""),
                    "summary": (artifacts.get(tid, "") or "")[:200],
                })
            else:
                pending.append({
                    "id": tid,
                    "name": t.get("title") or t.get("name", ""),
                    "phase": phase.get("name", ""),
                    "assigned_role": t.get("assigned_role", ""),
                    "depends_on": t.get("depends_on", []),
                })

    delta = await _call_rebalance_llm(
        original_req=original_req,
        completed=completed,
        pending=pending,
        interrupt_message=interrupt_message,
    )

    if delta is None:
        # LLM 失败 → 启发式降级
        delta = _heuristic_delta(
            interrupt_message=interrupt_message,
            completed=completed,
            pending=pending,
        )

    # 摘要文案（用作 HITL message）
    summary = delta.get("summary") or interrupt_message[:80]
    hitl_message = (
        f"📋 收到你的修改：{summary}\n\n"
        f"✓ 保留 {len(delta.get('keep', []))} 个已完成任务\n"
        f"🔄 重做 {len(delta.get('modify', []))} 个任务\n"
        f"🆕 新增 {len(delta.get('add', []))} 个任务\n"
        f"❌ 取消 {len(delta.get('cancel', []))} 个任务\n"
    )

    return {
        "delta_plan": delta,
        "status": "awaiting_delta_confirm",
        "hitl_type": "delta_plan",
        "hitl_message": hitl_message,
        "hitl_options": [
            {"label": "✅ 应用修改", "value": "approve"},
            {"label": "✍️ 我再补充", "value": "modify"},
            {"label": "❌ 撤回介入", "value": "reject"},
        ],
        "_agent_name": "Supervisor",
        "_content": hitl_message,
    }


async def _call_rebalance_llm(
    original_req: str,
    completed: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    interrupt_message: str,
) -> dict[str, Any] | None:
    """调 LLM 生成 delta_plan。失败返回 None。"""
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from app.models.model import Model as ModelModel
        from sqlalchemy import select

        prompt = REBALANCE_PROMPT.format(
            original_requirement=original_req or "(无)",
            completed_tasks=json.dumps(completed, ensure_ascii=False, indent=2) if completed else "(无)",
            pending_tasks=json.dumps(pending, ensure_ascii=False, indent=2) if pending else "(无)",
            interrupt_message=interrupt_message,
        )

        async with async_session() as db:
            # 找一个非 test provider 的 Agent
            stmt = (
                select(Agent)
                .join(ModelModel, Agent.default_model_id == ModelModel.id)
                .where(ModelModel.provider != "test")
                .limit(1)
            )
            result = await db.execute(stmt)
            agent = result.scalar_one_or_none()
            if not agent:
                logger.warning("M1' rebalance: no non-test agent available, falling back to heuristic")
                return None

            llm_result = await agent_chat(
                db=db,
                agent=agent,
                message=prompt,
                return_reasoning=False,
                save_memory=False,
            )

            raw = llm_result.get("content", "")
            delta = _extract_json(raw)
            if delta and isinstance(delta, dict):
                # 确保字段齐全
                delta.setdefault("summary", interrupt_message[:80])
                delta.setdefault("keep", [])
                delta.setdefault("modify", [])
                delta.setdefault("add", [])
                delta.setdefault("cancel", [])
                return delta
            logger.warning(f"M1' rebalance: invalid JSON output, falling back. raw={raw[:200]!r}")
            return None
    except Exception as e:
        logger.error(f"M1' rebalance LLM call failed: {e}")
        return None


def _heuristic_delta(
    interrupt_message: str,
    completed: list[dict[str, Any]],
    pending: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 不可用时的兜底：所有 completed 保留，所有 pending 标 modify"""
    return {
        "summary": interrupt_message[:80],
        "keep": [c["id"] for c in completed],
        "modify": [
            {"task_id": p["id"], "reason": "用户介入，重新评估是否需要调整", "new_version": 2}
            for p in pending
        ],
        "add": [],
        "cancel": [],
    }


def _extract_json(text: str) -> dict | None:
    """从 LLM 输出中提取 JSON（容忍 ```json...``` 包裹）"""
    if not text:
        return None
    # 尝试直接 parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 提取 ```json ... ``` 块
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ── 接收 delta_plan HITL 后的应用逻辑 ──

def apply_delta_to_task_dag(task_dag: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """将 delta_plan 应用到 task_dag，输出新版 task_dag。

    - keep: 不动
    - modify: 标记 status='modified' + version+1
    - cancel: 标记 status='cancelled'
    - add: 追加到对应 phase
    """
    new_dag = json.loads(json.dumps(task_dag))  # deep copy
    cancel_set = {c["task_id"] for c in delta.get("cancel", [])}
    modify_map = {m["task_id"]: m for m in delta.get("modify", [])}

    for phase in new_dag.get("phases", []):
        new_tasks = []
        for t in phase.get("tasks", []):
            tid = t.get("id", "")
            if tid in cancel_set:
                t["status"] = "cancelled"
                t["cancel_reason"] = next((c.get("reason", "") for c in delta.get("cancel", []) if c["task_id"] == tid), "")
                new_tasks.append(t)
                continue
            if tid in modify_map:
                m = modify_map[tid]
                t["status"] = "modified"
                t["version"] = m.get("new_version", t.get("version", 1) + 1)
                t["modify_reason"] = m.get("reason", "")
                new_tasks.append(t)
                continue
            # keep 保留
            new_tasks.append(t)
        phase["tasks"] = new_tasks

    # 处理 add：归属到 phase_id 对应的 phase，若不存在则新建 phase
    for new_task in delta.get("add", []):
        phase_id = new_task.get("phase_id")
        target_phase = None
        if phase_id:
            for p in new_dag.get("phases", []):
                if p.get("id") == phase_id:
                    target_phase = p
                    break
        if not target_phase:
            # 创建新 phase
            target_phase = {
                "id": phase_id or f"phase-extra-{len(new_dag.get('phases', [])) + 1}",
                "name": "介入新增",
                "tasks": [],
            }
            new_dag.setdefault("phases", []).append(target_phase)
        new_task.setdefault("status", "new")
        new_task.setdefault("version", 1)
        target_phase["tasks"].append(new_task)

    return new_dag
