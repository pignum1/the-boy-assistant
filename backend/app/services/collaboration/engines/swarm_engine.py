"""群聊式引擎（AutoGen / OpenAI Swarm 风格）

三阶段机制：
  Phase 1 讨论：多轮辩论 — Agent 互相质疑、协商、达成共识
  Phase 2 执行：每个 agent 产出角色对应的交付物（PRD/架构/代码）
  Phase 3 HITL：超出轮次或出现分歧时 → 提请用户裁决

事件流：
  agent_status → agent_message → reasoning_complete → task_output → storage_update → message_complete
"""

import asyncio
import logging
import re
import time as _t
import uuid
from datetime import datetime
from typing import Callable, Awaitable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# HITL 触发时的轮次记录，供 resume 恢复（避免 max_rounds 重置）
_swarm_hitl_round: dict[str, int] = {}

SendFn = Callable[[dict], Awaitable[None]]


SPEAKER_SELECT_PROMPT = """你是群聊调度员，根据对话历史选择下一个最合适的发言者。

## 团队成员
{members_desc}

## 对话历史（最近 {history_count} 条）
{history}

## 终止条件：**仅当全部满足时**才输出 "__DONE__"：
1. 已发言 ≥ {min_speakers} 人，每个角色均发表了专业意见
2. 团队已产出具体可评审的内容
3. 没有未解决的实质性分歧

## 继续讨论条件（满足任一即继续）：
- 还有角色未发言
- 存在成员间未解决的分歧
- 只达成方向性共识，缺少具体内容

## 输出格式（严格）
只输出一个 agent_name 或 "__DONE__"，不要任何其它内容。
"""


AGENT_DISCUSS_PROMPT = """你正在参与一个团队群聊，目标是协作完成用户的任务。

## 你的身份
- 名字: {agent_name}
- 角色: {role}
- 能力: {capabilities}

## 用户原始请求
{user_message}

## 团队成员
{members_desc}

## 对话历史
{history}

## 当前进度
{round_context}
本轮已发言 {history_len} 次，剩余最多 {remaining} 轮。

## 发言规则（重要）
作为 {agent_name}，你的发言必须：
1. **回应他人观点**：正面回应与你领域相关的问题或假设
2. **提出质疑**：如果发现方案问题，直接指出并给出替代方案
3. **产出具体内容**：如果你能产出内容，请用 [TASK] 声明任务并给出具体内容
4. **不要急于结束**：用多轮把问题讨论透彻，不要在1-2轮就建议结束
5. **需要用户确认时的格式要求**：在内容开头标注 `__HITL__` 标记，然后列出方案选项。方案用 `**方案X**：摘要` 的粗体格式。例如：
```
__HITL__
分析完成后，需要用户确认以下选择：

**方案A：消费返积分** — 按消费额1:1获得积分，简单直接
**方案B：行为积分** — 签到/评论等行为累积积分，提升活跃度
**推荐：方案B** — 更适合当前DAU增长目标
```
`__HITL__` 标记确保系统准确识别决策请求。方案名称会直接作为选项按钮展示给用户。
"""


AGENT_EXECUTE_PROMPT = """你的团队已完成讨论并达成共识，现在你需要输出**属于你角色的最终交付物**。

## 你的身份
名字: {agent_name}，角色: {role}

## 用户原始需求
{user_message}

## 你的交付物要求
{file_type_guide}

## 输出规则（严格遵守）
1. **不要写开场白/结束语**：禁止"好的"、"收到"、"我将输出"、"以上是..."这类对话文字
2. **第一行就是交付物内容**：文档从标题开始，代码从 import 或注释开始
3. **必须用工具写入文件**：调用 file-ops 工具
   - operation: write
   - path: {suggested_path}
   - content: 完整交付物内容

## 质量要求
- 文档类：结构完整，含目录/章节/表格，可直接评审
- 代码类：可直接运行，含 import、类型注解、docstring、错误处理
"""


TASK_PATTERN = re.compile(r'\[TASK\]\s*(.+?)(?=\n\[TASK\]|\n\n(?:好的|以下|我[^将])|\Z)', re.DOTALL)


# ── 角色 → 文件输出配置 ──

ROLE_FILE_CONFIG: dict[str, tuple[str, str]] = {
    "产品经理": ("PRD 文档（Markdown 格式，含需求背景、功能列表、用例描述、验收标准）",
                 "docs/PRD.md"),
    "pm": ("PRD 文档（Markdown 格式，含需求背景、功能列表、用例描述、验收标准）",
           "docs/PRD.md"),
    "product_manager": ("PRD 文档（Markdown 格式）", "docs/PRD.md"),
    "架构师": ("系统架构设计文档（Markdown 格式，含架构图描述、技术选型 ADR、数据库设计、API 契约）",
               "docs/architecture.md"),
    "architect": ("系统架构设计文档（Markdown 格式）", "docs/architecture.md"),
    "后端": ("Python 代码文件，含 models.py（数据库模型）、service.py（业务逻辑）、router.py（API 路由）",
             "src/"),
    "后端工程师": ("Python 代码文件，含 models.py（数据库模型）、service.py（业务逻辑）、router.py（API 路由）",
                   "src/"),
    "backend": ("Python 代码文件", "src/"),
    "backend_dev": ("Python 代码文件", "src/"),
    "前端": ("TypeScript/React 组件文件", "src/"),
    "前端工程师": ("TypeScript/React 组件文件", "src/"),
    "frontend": ("TypeScript/React 组件文件", "src/"),
    "frontend_dev": ("TypeScript/React 组件文件", "src/"),
    "测试": ("测试代码文件（pytest），含测试用例和 fixtures", "tests/"),
    "tester": ("测试代码文件（pytest）", "tests/"),
    "运维": ("部署配置文件（Dockerfile, docker-compose.yml, nginx.conf 等）", "deploy/"),
    "devops": ("部署配置文件", "deploy/"),
    "ui_designer": ("UI 设计规范文档（Markdown 格式）", "docs/ui_design.md"),
    "UI设计师": ("UI 设计规范文档（Markdown 格式）", "docs/ui_design.md"),
}


def _get_role_file_config(role: str, agent_name: str) -> tuple[str, str]:
    """根据角色返回 (file_type_guide, suggested_path)。"""
    for key, (guide, path) in ROLE_FILE_CONFIG.items():
        if key in role or key in agent_name:
            return (guide, path)
    return ("Markdown 格式的总结文档", f"output/{agent_name}_summary.md")


# ── speaker selection ──

async def _select_speaker(
    db: AsyncSession, strategy: str, members: list[dict],
    history: list[dict], last_speaker: Optional[str],
    round_idx: int, min_rounds: int = 3,
) -> Optional[str]:
    if not members:
        return None
    if strategy == "round_robin":
        return members[round_idx % len(members)]["name"]
    if strategy == "priority":
        priority = sorted(members, key=lambda m: (not m.get("is_required"), 0))
        return priority[round_idx % len(priority)]["name"]

    try:
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent

        # Use one of the team members as scheduler instead of random Agent
        scheduler_agent = members[0]["_agent"] if members else None

        if not scheduler_agent:
            return members[round_idx % len(members)]["name"]

        members_desc = "\n".join(
            f"- {m['name']} ({m['role']}): {', '.join(m.get('capabilities', []))}"
            for m in members
        )
        history_text = "\n".join(
            f"[{h['speaker']}] {h['content'][:200]}" for h in history[-8:]
        )
        prompt = SPEAKER_SELECT_PROMPT.format(
            members_desc=members_desc, history_count=min(8, len(history)),
            history=history_text or "(无历史)", min_speakers=min_rounds,
        )
        result = await agent_chat(db=db, agent=scheduler_agent, message=prompt,
                                   return_reasoning=False, save_memory=False)
        choice = (result.get("content") or "").strip()
        if choice == "__DONE__":
            return None
        for m in members:
            if m["name"] in choice or choice in m["name"]:
                if m["name"] != last_speaker:
                    return m["name"]
        return members[round_idx % len(members)]["name"]
    except Exception as e:
        logger.warning(f"swarm speaker select failed: {e}")
        return members[round_idx % len(members)]["name"]


# ── main run ──

async def run(
    session_id: str, team, user_message: str,
    team_agents: list, available_roles: list, send_fn: SendFn,
    *, _resume_round: int = 0, harness=None,
) -> None:
    print(f"[SWARM] run() called - session={session_id[:8]} user_message={user_message[:30]} resume_round={_resume_round}")
    from app.core.database import async_session
    from app.services.team_mode_service import TeamModeService
    from app.services.agent_chat import agent_chat
    from app.models.agent import Agent
    from app.models.team_member import TeamMember

    async with async_session() as db:
        svc = TeamModeService(db)
        cfg = await svc.get_swarm_config(team.id)
        max_rounds = cfg.max_rounds if cfg else 8
        # HITL resume 时，剩余轮次 = 总轮次 - 已消耗轮次
        remaining_rounds = max_rounds - _resume_round
        strategy = cfg.speak_strategy if cfg else "auto"

        print(f"[SWARM] Config: max_rounds={max_rounds}, remaining={remaining_rounds}, strategy={strategy}")

        rows = (await db.execute(
            select(TeamMember, Agent)
            .join(Agent, TeamMember.agent_id == Agent.id)
            .where(TeamMember.team_id == team.id)
        )).all()
        members = [
            {"name": agent.name, "agent_id": str(agent.id),
             "role": tm.role_name or "", "capabilities": tm.capabilities or [],
             "is_required": tm.is_required, "_agent": agent}
            for tm, agent in rows
        ]
        print(f"[SWARM] Loaded {len(members)} members")
        if not members:
            await send_fn({"type": "error", "payload": {"message": "团队成员为空"}})
            return

        members_desc = "\n".join(
            f"- {m['name']} ({m['role']}): {', '.join(m['capabilities'])}"
            for m in members
        )
        workspace_path = await _get_workspace_path(db, session_id)

        # ========================
        # Phase 1: 多轮讨论
        # ========================
        await send_fn({"type": "routing_decision", "source": "swarm",
                       "timestamp": datetime.now().isoformat(),
                       "payload": {"mode": "multi_agent", "agent_name": "群聊"}})
        await send_fn({"type": "thinking_update", "source": "system",
                       "timestamp": datetime.now().isoformat(),
                       "payload": {"step": "swarm_thinking",
                                   "detail": f"通知 {len(members)} 个团队成员讨论（最多 {max_rounds} 轮）...",
                                   "result": "", "agent": "📢 通知"}})
        for m in members:
            await send_fn({"type": "agent_status", "source": m["agent_id"],
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"agent_id": m["agent_id"], "agent_name": m["name"],
                                       "status": "idle", "summary": "待命中"}})

        history: list[dict] = []
        hitl_triggered = False
        _pre_extracted_options: list[dict] = []  # HitlDetector 提取的选项
        min_rounds = max(2, len(members) + 1)

        print(f"[SWARM] Starting parallel discussion loop - remaining_rounds={remaining_rounds}, members={len(members)}")

        for local_round in range(remaining_rounds):
            round_idx = _resume_round + local_round
            print(f"[SWARM] Round {round_idx + 1}/{max_rounds}")
            remaining = max_rounds - round_idx - 1

            history_text = "\n".join(
                f"[{h['speaker']}] {h['content'][:500]}" for h in history[-15:])

            # All agents speak in parallel this round
            async def _agent_speak(member: dict) -> dict | None:
                name = member["name"]
                await send_fn({"type": "agent_status", "source": member["agent_id"],
                               "timestamp": datetime.now().isoformat(),
                               "payload": {"agent_id": member["agent_id"], "agent_name": name,
                                           "status": "thinking",
                                           "summary": f"{name} 正在思考（第 {round_idx + 1} 轮）"}})
                prompt = AGENT_DISCUSS_PROMPT.format(
                    agent_name=name, role=member["role"],
                    capabilities=", ".join(member["capabilities"]),
                    user_message=user_message, members_desc=members_desc,
                    history=history_text or "(新对话，欢迎各抒己见)", round_context=f"第 {round_idx + 1}/{max_rounds} 轮",
                    history_len=len(history), remaining=remaining)

                try:
                    t_start = _t.monotonic()
                    from app.services.collaboration.agent_executor import agent_executor as _exec
                    result = await _exec.execute(
                        prompt=prompt, agent=member["_agent"], db=db,
                        session_id=session_id, team_id=str(team.id),
                        node_key="swarm_agent",
                    )
                    latency_ms = int((_t.monotonic() - t_start) * 1000)
                    content = (result.get("content") or "").strip()
                    reasoning = result.get("reasoning", {}) or {}
                    logger.info(f"[swarm] agent_chat result for {name}: content_len={len(content)} exec_mode={result.get('exec_mode','?')}")
                except Exception as e:
                    logger.error(f"swarm agent_chat failed for {name}: {e}", exc_info=True)
                    content = f"（{name} 暂时无法发言: {e}）"
                    reasoning, latency_ms = {}, 0

                if not content:
                    logger.warning(f"[swarm] Empty content for {name}, skipping")
                    await send_fn({"type": "agent_status", "source": member["agent_id"],
                                   "timestamp": datetime.now().isoformat(),
                                   "payload": {"agent_id": member["agent_id"], "agent_name": name,
                                               "status": "idle", "summary": f"{name} 本轮未发言"}})
                    return None

                await send_fn({"type": "agent_message", "source": "swarm",
                               "timestamp": datetime.now().isoformat(),
                               "payload": {
                                   "agent": name, "agent_id": member["agent_id"],
                                   "content": content, "type": "message", "round": round_idx + 1,
                                   "model": (reasoning.get("model_routing") or {}).get("selected_model"),
                                   "latency": latency_ms,
                                   "exec_mode": reasoning.get("exec_mode", result.get("exec_mode", "")),
                                   "iterations": reasoning.get("iterations", result.get("iterations", 1)),
                               }})

                if reasoning:
                    await send_fn({"type": "reasoning_complete", "source": "swarm",
                                   "timestamp": datetime.now().isoformat(),
                                   "payload": {
                                       "agent": name,
                                       "thinking_steps": reasoning.get("thinking_steps", ""),
                                       "model_routing": reasoning.get("model_routing", {}),
                                       "tool_calls": reasoning.get("tool_calls", []),
                                       "decision_summary": f"第 {round_idx + 1} 轮发言",
                                       "latency": latency_ms,
                                       "exec_mode": reasoning.get("exec_mode", result.get("exec_mode", "")),
                                       "iterations": reasoning.get("iterations", result.get("iterations", 1)),
                                       # 模式专属数据（前端按模式渲染）
                                       "history": reasoning.get("history", []),
                                       "reflections": reasoning.get("reflections", []),
                                       "samples": reasoning.get("samples", []),
                                       "merged": reasoning.get("merged", False),
                                       "plan": reasoning.get("plan", {}),
                                       "tool_results": reasoning.get("tool_results", []),
                                       "review_score": reasoning.get("review_score"),
                                   }})

                await send_fn({"type": "agent_status", "source": member["agent_id"],
                               "timestamp": datetime.now().isoformat(),
                               "payload": {"agent_id": member["agent_id"], "agent_name": name,
                                           "status": "done",
                                           "summary": f"{name} 完成 · {latency_ms / 1000:.1f}s"}})
                return {"speaker": name, "content": content, "member": member}

            # Start all agents in parallel
            coros = [_agent_speak(m) for m in members]
            results = await asyncio.gather(*coros, return_exceptions=True)

            # Collect valid responses
            round_responses = [r for r in results if isinstance(r, dict) and r is not None]
            if not round_responses:
                logger.warning(f"[swarm] No valid responses in round {round_idx + 1}")
                # If still early, try next round; otherwise break
                if len(history) < max(len(members), 3):
                    continue
                else:
                    break

            for r in round_responses:
                history.append({"speaker": r["speaker"], "content": r["content"]})

            # Check if any agent triggered HITL（HitlDetector 四级检测）
            from app.services.collaboration.hitl_detector import detect_hitl
            for i, r in enumerate(round_responses):
                result = detect_hitl(
                    content=r.get("content", ""),
                    speaker=r["speaker"],
                    round_idx=round_idx,
                    is_last_speaker=(i == len(round_responses) - 1),
                    all_round_contents=[h["content"] for h in history[-5:]],
                )
                if result.triggered:
                    hitl_triggered = True
                    _swarm_hitl_round[session_id] = round_idx + 1
                    logger.info(
                        f"[swarm] HITL detected: speaker={r['speaker']} "
                        f"round={round_idx + 1} confidence={result.confidence.value} "
                        f"matched_by={result.matched_by} reason={result.reason}"
                    )
                    if result.options is not None:
                        _pre_extracted_options = result.options
                    break

            if hitl_triggered:
                break

            # Check if discussion naturally concluded
            done_count = sum(1 for r in round_responses if "__DONE__" in r["content"])
            if done_count >= len(members) // 2 + 1 and len(history) >= min_rounds:
                break

        total_speakers = len(set(h["speaker"] for h in history))

        # ========================
        # Phase 2: 并行执行 — 每个 agent 按角色同时产出交付物
        # ========================
        tasks_executed = 0
        if history:
            await send_fn({"type": "thinking_update", "source": "system",
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"step": "task_execution",
                                       "detail": f"讨论完成，{total_speakers} 个成员开始并行产出交付物...",
                                       "result": "", "agent": "📋 执行"}})

            discussion_summary = "\n".join(
                f"[{h['speaker']}] {h['content'][:300]}" for h in history[-10:])

            async def _agent_execute(member: dict) -> int:
                agent_name = member["name"]
                role = member["role"]
                file_type_guide, suggested_path = _get_role_file_config(role, agent_name)

                await send_fn({"type": "agent_status", "source": member["agent_id"],
                               "timestamp": datetime.now().isoformat(),
                               "payload": {"agent_id": member["agent_id"], "agent_name": agent_name,
                                           "status": "thinking",
                                           "summary": f"{agent_name} 正在输出 {suggested_path}..."}})

                exec_prompt = AGENT_EXECUTE_PROMPT.format(
                    agent_name=agent_name, role=role,
                    user_message=user_message,
                    discussion_summary=discussion_summary,
                    file_type_guide=file_type_guide,
                    suggested_path=suggested_path)

                try:
                    t_start = _t.monotonic()
                    from app.services.collaboration.agent_executor import agent_executor as _exec2
                    exec_result = await _exec2.execute(
                        prompt=exec_prompt, agent=member["_agent"], db=db,
                        session_id=session_id, team_id=str(team.id),
                        node_key="swarm_execute",
                    )
                    latency_ms = int((_t.monotonic() - t_start) * 1000)
                    exec_content = (exec_result.get("content") or "").strip()
                    exec_reasoning = exec_result.get("reasoning", {}) or {}
                except Exception as e:
                    logger.error(f"Task execution failed for {agent_name}: {e}")
                    await send_fn({"type": "agent_status", "source": member["agent_id"],
                                   "timestamp": datetime.now().isoformat(),
                                   "payload": {"agent_id": member["agent_id"], "agent_name": agent_name,
                                               "status": "done", "summary": f"{agent_name} 执行失败"}})
                    return 0

                if not exec_content:
                    await send_fn({"type": "agent_status", "source": member["agent_id"],
                                   "timestamp": datetime.now().isoformat(),
                                   "payload": {"agent_id": member["agent_id"], "agent_name": agent_name,
                                               "status": "done", "summary": f"{agent_name} 无需产出"}})
                    return 0

                exec_content = _clean_deliverable_content(exec_content)

                await send_fn({"type": "agent_message", "source": "swarm",
                               "timestamp": datetime.now().isoformat(),
                               "payload": {
                                   "agent": agent_name, "agent_id": member["agent_id"],
                                   "content": exec_content, "type": "task_output",
                                   "model": (exec_reasoning.get("model_routing") or {}).get("selected_model"),
                                   "latency": latency_ms}})

                # Check tool calls for file writes
                tool_calls = exec_reasoning.get("tool_calls", [])
                has_file_write = _has_file_write_tool_call(tool_calls)
                for tc in tool_calls:
                    if tc.get("tool") in ("file-ops", "write_file", "create_file", "save_file"):
                        params = tc.get("params", {})
                        path = params.get("path", "unknown") if isinstance(params, dict) else str(params)[:100]
                        op = params.get("operation", "save") if isinstance(params, dict) else "save"
                        await send_fn({"type": "storage_update", "source": "swarm",
                                       "timestamp": datetime.now().isoformat(),
                                       "payload": {"agent": agent_name, "tool": tc.get("tool"),
                                                   "path": path, "operation": op,
                                                   "status": tc.get("status", "done")}})

                # Harness: 执行后 Hook（文件提取 + 持久化 + Token 统计）
                if harness:
                    from app.services.harness import ExecutionContext as HEC, ExecutionResult as HER
                    try:
                        h_ctx = HEC(
                            session_id=session_id, team_id=str(team.id),
                            agent_id=member["agent_id"], agent_name=agent_name,
                            node_key=role,
                        )
                        h_result = HER(
                            content=exec_content,
                            model=(exec_reasoning.get("model_routing") or {}).get("selected_model", "unknown"),
                            provider=(exec_reasoning.get("model_routing") or {}).get("provider", "unknown"),
                            latency_ms=latency_ms,
                            usage=exec_result.get("usage", {}),
                        )
                        await harness.after_execution(h_ctx, h_result)
                    except Exception as e:
                        logger.warning(f"Harness hook failed for {agent_name}: {e}")

                # Fallback: auto-save if no explicit file write
                if not has_file_write and len(exec_content) > 100:
                    saved_files = await _auto_save_by_role(
                        db, session_id, agent_name, role, exec_content, workspace_path)
                    for sf in saved_files:
                        await send_fn({"type": "storage_update", "source": "swarm",
                                       "timestamp": datetime.now().isoformat(),
                                       "payload": {"agent": agent_name, "tool": "file-ops",
                                                   "path": sf, "operation": "write", "status": "done"}})

                await send_fn({"type": "agent_status", "source": member["agent_id"],
                               "timestamp": datetime.now().isoformat(),
                               "payload": {"agent_id": member["agent_id"], "agent_name": agent_name,
                                           "status": "done",
                                           "summary": f"{agent_name} 交付完成 · {latency_ms / 1000:.1f}s"}})
                return 1

            exec_results = await asyncio.gather(
                *[_agent_execute(m) for m in members], return_exceptions=True)
            tasks_executed = sum(r for r in exec_results if isinstance(r, int))

        # ========================
        # Phase 3: 完成 / HITL
        # ========================
        # HITL 触发条件：1) 讨论卡住 或 2) Agent 提出需要用户确认
        if hitl_triggered:
            hitl_message, hitl_type, options = _build_hitl_payload(
                history, user_message, members, stuck=False,
                pre_extracted_options=_pre_extracted_options)
            hitl_id = f"hitl-{uuid.uuid4().hex[:8]}"

            await send_fn({"type": "hitl_notification", "source": "swarm",
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"id": hitl_id,
                                       "hitl_type": hitl_type,
                                       "message": hitl_message,
                                       "options": options}})

            # Persist HITL notification to memory so it survives page refresh
            try:
                from app.services.memory_manager import MemoryManager
                from app.schemas.memory import MemoryLevel, MemoryType
                mm = MemoryManager(db)
                await mm.save_memory(
                    level=MemoryLevel.context,
                    content=f"⚠️ **需要您的决策**\n\n{hitl_message}",
                    type=MemoryType.context,
                    team_id=team.id,
                    session_id=session_id,
                    importance=0.5,
                    created_by="system",
                    metadata_={
                        "role": "system",
                        "hitl_notification": True,
                        "hitl_id": hitl_id,
                        "hitl_type": hitl_type,
                        "hitl_options": options,
                    },
                )
                await db.commit()
            except Exception as e:
                logger.warning(f"Failed to persist HITL notification: {e}")

        status_parts = [f"{len(history)} 轮讨论", f"{total_speakers} 人参与"]
        if tasks_executed > 0:
            status_parts.append(f"{tasks_executed} 个交付物已产出")
        status_msg = f"群聊结束（{'，'.join(status_parts)}）"

        await send_fn({"type": "thinking_update", "source": "system",
                       "timestamp": datetime.now().isoformat(),
                       "payload": {"step": "done", "detail": f"✅ {status_msg}",
                                   "result": "", "agent": "📢 通知"}})
        await send_fn({"type": "message_complete", "source": "swarm",
                       "timestamp": datetime.now().isoformat(),
                       "payload": {"message": status_msg}})


async def resume(session_id: str, user_response: dict, send_fn: SendFn, harness=None) -> None:
    hitl_type = user_response.get("hitl_type", "select")
    logger.info(f"swarm resume session={session_id[:8]} type={hitl_type}")

    # Format user's decision into a message for the agents
    response_text = _format_hitl_response_for_resume(user_response)

    from app.core.database import async_session
    from app.models.agent import Agent
    from app.models.team_member import TeamMember
    from sqlalchemy import select
    import uuid as _uuid

    async with async_session() as db:
        from app.models.session import Session as SessionModel
        session = await db.get(SessionModel, _uuid.UUID(session_id))
        if not session:
            logger.warning(f"swarm resume: session {session_id[:8]} not found")
            return
        from app.models.team import Team
        team = await db.get(Team, session.team_id)
        if not team:
            return

        rows = (await db.execute(
            select(TeamMember, Agent)
            .join(Agent, TeamMember.agent_id == Agent.id)
            .where(TeamMember.team_id == team.id)
        )).all()
        team_agents = [a for _, a in rows]
        available_roles = list({tm.role_name for tm, _ in rows if tm.role_name})

        # 恢复时传递已消耗的轮次，避免 max_rounds 重新计数
        resume_round = _swarm_hitl_round.pop(session_id, 0)
        await run(
            session_id=session_id,
            team=team,
            user_message=f"用户决策: {response_text}\n请根据这个决策继续推进，进入下一阶段的讨论和执行。",
            team_agents=team_agents,
            available_roles=available_roles,
            send_fn=send_fn,
            _resume_round=resume_round,
        )


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _clean_deliverable_content(content: str) -> str:
    """Remove conversational prefixes from deliverable content."""
    prefixes = [
        "好的，", "好的，各位", "收到", "根据讨论", "根据团队",
        "我将输出", "我将生成", "以下是我的", "以下是", "现在开始",
        "好的，我", "我同意", "明白了",
    ]
    content = content.strip()
    for p in prefixes:
        if content.startswith(p):
            # Find the first newline after prefix
            nl = content.find("\n", len(p))
            if nl > 0:
                content = content[nl + 1:].strip()
            break
    return content


def _has_file_write_tool_call(tool_calls: list) -> bool:
    for tc in tool_calls:
        tool = tc.get("tool", "")
        if tool == "file-ops":
            params = tc.get("params", {})
            if isinstance(params, dict) and params.get("operation") == "write":
                return True
        elif tool in ("write_file", "create_file", "save_file"):
            return True
    return False


# ── auto-save: 按角色拆分文件 ──

async def _auto_save_by_role(
    db: AsyncSession, session_id: str, agent_name: str, role: str,
    content: str, workspace_path: Optional[str],
) -> list[str]:
    """根据角色将内容拆分为合理文件并写入工作空间。"""
    from app.tools.file_ops import FileOpsTool
    tool = FileOpsTool()
    saved = []

    # 确定文件列表：角色 → (path, content_section)
    files_to_create: list[tuple[str, str]] = []

    if "产品经理" in role or "pm" in role or role == "pm":
        files_to_create.append(("docs/PRD.md", content))
    elif "架构师" in role or "architect" in role:
        files_to_create.append(("docs/architecture.md", content))
    elif "后端" in role or "backend" in role:
        parts = _split_code_content(content, "python")
        for filename, code in parts:
            files_to_create.append((f"src/{filename}", code))
        if not files_to_create:
            files_to_create.append(("src/models.py", _extract_section(content, "model", "models.py")))
            files_to_create.append(("src/service.py", _extract_section(content, "service", "auth_service.py")))
            files_to_create.append(("src/router.py", _extract_section(content, "router", "api.py")))
    elif "前端" in role or "frontend" in role:
        parts = _split_code_content(content, "typescript")
        for filename, code in parts:
            files_to_create.append((f"src/{filename}", code))
    elif "测试" in role or "tester" in role:
        files_to_create.append(("tests/test_main.py", content))
    else:
        ext = ".md"
        if "python" in content[:50].lower() or "import " in content[:100]:
            ext = ".py"
        elif "typescript" in content[:50].lower() or "import React" in content[:100]:
            ext = ".tsx"
        files_to_create.append((f"output/{_safe_filename(agent_name)}{ext}", content))

    for path, file_content in files_to_create:
        file_content = file_content.strip()
        if len(file_content) < 50:
            continue
        try:
            result = await tool.execute(
                params={"operation": "write", "path": path, "content": file_content},
                session_id=session_id)
            if result.success:
                saved.append(path)
                logger.info(f"Auto-saved: {path} ({len(file_content)} chars)")
            else:
                logger.warning(f"Auto-save failed for {path}: {result.error}")
        except Exception as e:
            logger.error(f"Auto-save exception for {path}: {e}")
    return saved


def _split_code_content(content: str, lang: str) -> list[tuple[str, str]]:
    """从含 markdown 的代码内容中提取代码块，按文件名拆分。"""
    import re as _re
    results = []
    # 匹配 ```python filename.py 或 ```python 或 # filename.py
    blocks = _re.findall(
        r'(?:###?\s*(.+?\.(?:py|ts|tsx|js|jsx))\s*\n)?'  # optional markdown header
        r'```(?:python|typescript|javascript)?\s*\n(.*?)```',
        content, _re.DOTALL | _re.IGNORECASE)
    for filename, code in blocks:
        if not filename:
            filename = f"module_{len(results) + 1}.{'py' if lang == 'python' else 'tsx'}"
        results.append((filename.strip(), code.strip()))
    if not results:
        # No code blocks found, try splitting by file-like headers
        sections = _re.split(r'\n(?:#|/{2,})\s*(.+?\.(?:py|ts|tsx))\s*\n', content)
        if len(sections) > 1:
            for i in range(1, len(sections), 2):
                filename = sections[i].strip()
                code = sections[i + 1].strip() if i + 1 < len(sections) else ""
                results.append((filename, code))
    return results


def _extract_section(content: str, keyword: str, fallback_name: str) -> str:
    """从内容中提取匹配关键词的章节。"""
    import re as _re
    pattern = _re.compile(
        rf'(?:#+\s*)?{keyword}[:\s]*(.+?)(?=\n#+\s|\n```\w+\n|\Z)',
        _re.IGNORECASE | _re.DOTALL)
    m = pattern.search(content)
    return m.group(1).strip() if m else content[:500]


def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)


def _strip_markdown(text: str) -> str:
    """Remove markdown bold/italic markers from text."""
    return re.sub(r'\*{1,3}', '', text).strip()

async def _get_workspace_path(db: AsyncSession, session_id: str) -> Optional[str]:
    try:
        from app.models.session import Session as SessionModel
        session = await db.get(SessionModel, uuid.UUID(session_id))
        if session and session.workspace_path:
            return session.workspace_path
    except Exception:
        pass
    return None


def _build_hitl_payload(
    history: list, user_message: str, members: list, stuck: bool,
    pre_extracted_options: list[dict] | None = None,
) -> tuple[str, str, list[dict]]:
    """Build HITL notification payload. Returns (message, hitl_type, options).

    Args:
        pre_extracted_options: HitlDetector 预先提取的选项（优先使用，跳过文本解析）
    """
    # 如果有预提取的结构化选项，直接使用
    # 额外追加 "其他想法" 选项让用户可以自由输入
    # 注意：用 is not None 而非 truthiness，空列表 [] 应进入默认分支
    if pre_extracted_options is not None:
        opts = list(pre_extracted_options)
        opts.append({
            "label": "💬 我有其他想法（自由输入）",
            "value": "answer",
            "description": "不选已有方案，自己输入想法",
        })
        message = "请从下方按钮中选择，或自由输入你的想法。"
        return message, "select", opts

    # Keywords that indicate ANALYSIS, not decisions — skip these
    _analysis_kw = {
        "利", "弊", "优点", "缺点", "优势", "劣势", "风险", "挑战",
        "提问", "提问架构师", "提问后端", "提问前端", "提问产品",
        "背景", "现状", "说明", "备注", "注意", "前提", "前置条件",
        "前置", "后置", "后置条件", "异常", "异常流程", "正常流程",
        "目标", "指标", "业务", "用户场景", "核心用户",
        "建议", "兼容性", "性能", "核心目标", "用例", "我的推荐",
        "推荐方案", "初步结论", "综合建议",
    }

    # Keywords that indicate a DECISION/OPTION being proposed
    _option_kw = {
        "方案", "推荐", "选择", "选项", "决策", "确认",
        "策略", "方式", "方法", "结论",
        "最终", "选定", "初步结论",
    }

    decision_items: list[dict] = []
    for h in reversed(history[-8:]):
        content = h["content"]
        if not any(kw in content for kw in (
            "需要用户确认", "请用户决定", "请用户选择",
            "需要确认", "关键决策", "暂停点", "请确认",
        )):
            continue

        # Find bold markers: **something**： or **something**:
        raw_items = re.findall(r'\*\*([^*]+)\*\*[：:]\s*(.+?)(?:\n|$)', content)
        for title, detail in raw_items:
            title = title.strip()
            detail = detail.strip()
            # Skip analysis markers
            if title in _analysis_kw:
                continue
            # Only include if title looks like a decision/option
            is_option = any(kw in title for kw in _option_kw)
            if not is_option:
                continue
            # Build clean, short label for button display (strip markdown)
            detail_clean = _strip_markdown(detail)
            short = detail_clean[:30].rstrip() + ('...' if len(detail_clean) > 30 else '')
            label = f"{_strip_markdown(title)}：{short}" if short else _strip_markdown(title)
            if len(label) > 60:
                label = label[:57] + '...'
            # Deduplicate
            if not any(d["label"] == label for d in decision_items):
                decision_items.append({
                    "label": label,
                    "value": f"opt_{len(decision_items)}",
                    "description": detail[:120],
                })

        # Also find plain-text option patterns (方案A / 方案A：detail / 选项B：detail)
        plain_options = re.findall(
            r'(?:(方案[A-C])|(选项\s*[一二三ABC\d]+)|([选策]略\s*[ABC\d]+))[：:]\s*(.+?)(?:\n|$)',
            content)
        for opt_match in plain_options:
            tag = opt_match[0] or opt_match[1] or opt_match[2]
            detail = opt_match[3].strip() if len(opt_match) > 3 else ""
            detail_clean = _strip_markdown(detail)
            short = detail_clean[:30].rstrip() + ('...' if len(detail_clean) > 30 else '')
            label = f"{tag}：{short}" if short else tag
            if len(label) > 60:
                label = label[:57] + '...'
            if not any(d["label"] == label for d in decision_items):
                decision_items.append({
                    "label": label,
                    "value": f"opt_{len(decision_items)}",
                    "description": detail[:120] if detail else tag,
                })

    lines = [
        f"## 团队讨论已持续 {len(history)} 轮\n",
        f"**需求**：{user_message[:200]}\n",
    ]

    # Determine hitl_type and build options
    if decision_items:
        lines.append("**需要决策的具体事项**：")
        for i, item in enumerate(decision_items[:8], 1):
            lines.append(f"{i}. {item['label']}")

        extra_opts = [
            {"label": "继续讨论", "value": "continue"},
            {"label": "重新描述需求", "value": "rephrase"},
        ]

        if len(decision_items) >= 3:
            hitl_type = "multi_select"
            options = decision_items[:8] + extra_opts
        else:
            hitl_type = "select"
            options = decision_items[:8] + extra_opts
    else:
        # No structured options found — show clean generic options
        hitl_type = "select"
        options = [
            {"label": "确认并继续推进", "value": "confirm", "description": "认可当前讨论结果，进入下一阶段"},
            {"label": "需要补充更多方案对比", "value": "more_details", "description": "让 agent 进一步分析各方案利弊"},
            {"label": "重新描述需求", "value": "rephrase", "description": "用不同的角度重新说明需求"},
        ]

    # 追加 "其他想法" 选项
    if options:
        options.append({
            "label": "💬 我有其他想法（自由输入）",
            "value": "answer",
            "description": "不选已有方案，自己输入想法",
        })
    lines.append(f"\n**参与成员**：{', '.join(m['name'] for m in members)}")
    return "\n".join(lines), hitl_type, options


def _format_hitl_response_for_resume(response: dict) -> str:
    """Format structured HITL response into a user-facing summary string."""
    hitl_type = response.get("hitl_type", "select")
    values = response.get("values", [])
    feedback = response.get("feedback", "")
    approved = response.get("approved", False)

    if hitl_type == "answer":
        return feedback or "（无文本输入）"
    elif hitl_type == "review":
        status = "批准" if approved else "驳回"
        return f"{status}{'，反馈：' + feedback if feedback else ''}"
    elif hitl_type == "multi_select":
        num = len(values)
        return f"选择了 {num} 项：{', '.join(values[:5])}"
    else:  # select
        chosen = values[0] if values else "（无选择）"
        return f"选择了：{chosen}"


def _format_hitl_response_for_display(user_response: dict) -> str:
    """Summarize the user's HITL response for chat display."""
    hitl_type = user_response.get("hitl_type", "select")
    if hitl_type == "answer":
        return f"回答: {user_response.get('feedback', '')}"
    elif hitl_type == "review":
        a = user_response.get("approved", False)
        fb = user_response.get("feedback", "")
        return f"{'已批准' if a else '已驳回'}" + (f' (反馈: {fb})' if fb else '')
    elif hitl_type == "multi_select":
        return f"已选择 {len(user_response.get('values', []))} 项确认"
    else:
        v = user_response.get("values", [])
        return f"选择了: {v[0]}" if v else "已确认"
