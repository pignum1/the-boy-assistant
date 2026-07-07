"""图编排式引擎（LangGraph 风格）— 纯图执行器

设计原则：引擎是工作流定义的**执行器**，不参与决策。
所有决策来自工作流定义中的节点配置和边的语义：
  - 节点 (type + config) → 定义"怎么执行"
  - 边 (type: forward/reject/escalate/timeout/fallback) → 定义"往哪走"
  - 条件节点的 expression → 定义"走哪条 forward 边还是 reject 边"

引擎只做：
  1. 加载工作流定义（节点 + 边 + 绑定）
  2. 从 start 节点开始，沿边遍历图
  3. 执行每个节点，存储产出到 artifacts
  4. 根据节点类型和产出解析下一条边
  5. HITL 节点暂停 → 保存遍历位置 → 等待 resume
  6. 循环保护（visit_count 上限）

模块拆分：
  - langgraph_pause.py  — HITL 暂停/恢复状态持久化
  - langgraph_engine.py — 图遍历执行器
"""

import asyncio
import logging
import os as _os
import re as _re
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Awaitable

from sqlalchemy import select

from app.services.collaboration.engines.langgraph_pause import (
    _paused,
    _persist_paused_state,
    _load_paused_state,
    has_paused,
    cancel_paused,
)

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]

# Round-robin 计数器（Router 节点 strategy=round_robin 时使用）
# key = "rr_{session_id}_{node_id}", value = int
_rr_counter: dict[str, int] = {}

# ═══════════════════════════════════════════════════════════
# 图遍历工具函数
# ═══════════════════════════════════════════════════════════

def _bfs_downstream(start_nid: str, adj: dict[str, list[str]]) -> set[str]:
    """BFS 遍历起始节点及其所有下游节点（沿 forward 边）。"""
    result: set[str] = set()
    q = deque([start_nid])
    while q:
        cur = q.popleft()
        if cur in result:
            continue
        result.add(cur)
        for nxt in adj.get(cur, []):
            if nxt not in result:
                q.append(nxt)
    return result


def _follow_reject_edge(target_nid: str, artifacts: dict[str, str],
                         adj: dict[str, list[str]]) -> set[str]:
    """沿 reject 边回退：清除目标节点及下游的所有 artifacts。

    Returns:
        被清除的节点 ID 集合（用于发送 rollback 状态）。
    """
    downstream = _bfs_downstream(target_nid, adj)
    cleared: list[str] = []
    for nid in downstream:
        if nid in artifacts:
            del artifacts[nid]
            cleared.append(nid)
    logger.info(
        f"Follow reject edge to {target_nid}: cleared {len(cleared)} artifacts"
    )
    return downstream


def _resolve_next_edge(
    current_nid: str,
    current_result: str | None,
    edges_by_source: dict[str, list],
    artifacts: dict[str, str],
    node_by_id: dict,
    nkey_to_nid: dict[str, str],
    adj: dict[str, list[str]],
    db,
    session_id: str,
    team_id: str,
    exec_fn=None,  # async callable(nid): 用于处理 __multi_reject__ 并行执行
) -> str | None:
    """解析：当前节点执行完后，下一条该走什么边的目标节点。

    边的语义由工作流定义中的 edge.type 决定，引擎只负责沿边走：
    - forward:  正常流转
    - reject:   打回重做（先清除下游 artifacts）
    - timeout:  超时降级
    - fallback: 失败降级
    - escalate: 升级处理

    Returns:
        下一个要执行的节点 ID，或 None 表示流程结束。
    """
    outgoing = edges_by_source.get(current_nid, [])
    if not outgoing:
        return None

    current_node = node_by_id.get(current_nid)
    current_type = (current_node.type or "").lower() if current_node else ""

    # ── 条件节点: 求值 → 选 forward 或 reject 边 ──
    if current_type == 'condition' and current_node:
        cconfig = current_node.config if isinstance(current_node.config, dict) else {}
        expression = cconfig.get("expression", "")
        on_true_key = cconfig.get("on_true_node_key", "")
        on_false_key = cconfig.get("on_false_node_key", "")

        # 收集前置产物（条件节点的输入是前置节点的产出）
        cond_input = current_result or ""
        cond_result = _eval_condition_fast(expression, cond_input)
        if cond_result is None:
            # llm_judge: 需要 LLM 求值
            cond_result = True  # 默认安全

        chosen_key = on_true_key if cond_result else on_false_key
        chosen_nid = nkey_to_nid.get(chosen_key, "") if chosen_key else ""

        # 如果选中的节点已经有 artifact → 这是打回 → 走 reject 边
        if chosen_nid and chosen_nid in artifacts:
            _follow_reject_edge(chosen_nid, artifacts, adj)
        return chosen_nid or None

    # ── 校验节点: 通过走 forward，失败走 reject ──
    if current_type == 'validation' and current_node:
        vconfig = current_node.config if isinstance(current_node.config, dict) else {}
        validator_type = vconfig.get("validator", "llm_check")
        criteria = vconfig.get("criteria", "")
        on_fail = vconfig.get("on_fail", "retry")
        max_retries = int(vconfig.get("max_retries", 3))

        # 收集前置产物用于校验
        combined = current_result or ""
        passed, reason = False, ""

        if validator_type == "test_pass":
            fails = ["FAILED", "FAIL:", "AssertionError", "FAILED TESTS", "FAILURES"]
            passed = not any(f.lower() in combined.lower() for f in fails)
        elif validator_type == "regex_match":
            passed = bool(re.search(criteria, combined, re.DOTALL))
        else:
            # llm_check: 简化处理，默认通过
            passed = True

        if passed:
            # 走 forward 边
            for e in outgoing:
                if (e.type or "forward").lower() == "forward":
                    return str(e.target_id)
            return None

        # 失败: 找 reject 边
        for e in outgoing:
            if (e.type or "").lower() == "reject":
                tid = str(e.target_id)
                if tid in node_by_id:
                    _follow_reject_edge(tid, artifacts, adj)
                    return tid

        # 无 reject 边: 仍然走 forward（不阻塞流程）
        for e in outgoing:
            if (e.type or "forward").lower() == "forward":
                return str(e.target_id)
        return None

    # ── 路由节点: LLM 选择或固定策略 → 走 forward 或 reject ──
    if current_type == 'router' and current_node:
        rconfig = current_node.config if isinstance(current_node.config, dict) else {}
        strategy = rconfig.get("strategy", "llm_select")
        candidates: list = rconfig.get("candidates", [])
        fallback_key = rconfig.get("fallback_node_key", "")

        chosen_key = fallback_key
        if strategy == "round_robin" and candidates:
            rr_key = f"rr_{session_id}_{current_nid}"
            _rr_counter.setdefault(rr_key, 0)
            idx = _rr_counter[rr_key] % len(candidates)
            chosen_key = candidates[idx]
            _rr_counter[rr_key] += 1
        elif candidates:
            chosen_key = candidates[0]  # 默认第一个

        chosen_nid = nkey_to_nid.get(chosen_key, "") if chosen_key else ""
        if chosen_nid and chosen_nid in artifacts:
            # 检查是否有多个 reject 边 → 多目标并行回退
            reject_nids = []
            for e in outgoing:
                if (e.type or "").lower() == "reject":
                    tid = str(e.target_id)
                    if tid in node_by_id and tid in artifacts:
                        reject_nids.append(tid)
            if len(reject_nids) >= 2:
                for tid in reject_nids:
                    _follow_reject_edge(tid, artifacts, adj)
                logger.info(f"Router multi-reject: {len(reject_nids)} targets → parallel rollback")
                return ("__multi_reject__", reject_nids)
            _follow_reject_edge(chosen_nid, artifacts, adj)
        return chosen_nid or None

    # ── 默认: HITL / agent / start → 走 forward 边 ──
    for e in outgoing:
        if (e.type or "forward").lower() == "forward":
            return str(e.target_id)

    return None


# 包装器：处理 _resolve_next_edge 的 __multi_reject__ 返回值
async def _resolve_and_exec(
    current_nid, current_result, edges_by_source, artifacts,
    node_by_id, nkey_to_nid, adj, db, session_id, team_id, exec_fn,
) -> str | None:
    """调用 _resolve_next_edge，如果是多目标回退则并行执行。"""
    result = _resolve_next_edge(
        current_nid, current_result, edges_by_source, artifacts,
        node_by_id, nkey_to_nid, adj, db, session_id, team_id,
    )
    if isinstance(result, tuple) and result[0] == "__multi_reject__":
        reject_nids = result[1]
        logger.info(f"Multi-reject: executing {len(reject_nids)} targets in parallel")
        if len(reject_nids) == 1:
            await exec_fn(reject_nids[0])
        else:
            await asyncio.gather(*[exec_fn(nid) for nid in reject_nids])
        return reject_nids[0]
    return result

async def _handle_multi_reject(
    result, node_by_id, artifacts, adj,
    exec_fn,  # async callable(nid) -> None
) -> str | None:
    """处理 __multi_reject__ 返回值：并行执行所有 reject 目标 agent，返回第一个目标 nid。"""
    if isinstance(result, tuple) and result[0] == "__multi_reject__":
        reject_nids = result[1]
        logger.info(f"Multi-reject: executing {len(reject_nids)} targets in parallel")
        if len(reject_nids) == 1:
            await exec_fn(reject_nids[0])
        else:
            await asyncio.gather(*[exec_fn(nid) for nid in reject_nids])
        return reject_nids[0]
    return result


async def _execute_agent_node(
    *,
    nid: str,
    node,               # WorkflowNode
    agent,              # Agent
    db,                 # AsyncSession
    artifacts: dict[str, str],
    node_deps: dict[str, list[str]],
    node_key: str,
    label: str,
    user_message: str,
    session_id: str,
    team_id: str,
    send_fn: SendFn,
    ws_path: str,
    harness=None,       # Harness 横切拦截器
    timeout_edge: dict[str, str] | None = None,
    fallback_edge: dict[str, str] | None = None,
) -> None:
    """Execute a single Agent node. Shared by run() and resume()."""
    from app.services.agent_chat import agent_chat as _agent_chat

    if timeout_edge is None:
        timeout_edge = {}
    if fallback_edge is None:
        fallback_edge = {}

    await send_fn({
        "type": "task_status",
        "source": "langgraph",
        "timestamp": datetime.now().isoformat(),
        "payload": {"task_id": str(node.id), "status": "running"},
    })

    instruction = ""
    if isinstance(node.config, dict):
        instruction = node.config.get("instruction", "") or node.config.get("prompt", "")
    if not instruction:
        instruction = f"作为 {agent.name}，根据以下用户需求执行【{label}】节点的工作。"

    prev_ids = node_deps.get(nid, [])
    prev_outputs = "\n\n".join(
        f"### 前置产物 {pid}\n{artifacts[pid][:3000]}"
        for pid in prev_ids
        if pid in artifacts
    )

    # ── Harness: 统一构建 Prompt（替代引擎内联拼接）──
    from app.services.harness import ExecutionContext as HEC
    prompt = f"{instruction}\n\n## 用户需求\n{user_message}"
    if harness:
        try:
            h_ctx = HEC(
                session_id=session_id, team_id=team_id,
                agent_id=str(agent.id), agent_name=agent.name,
                node_key=node_key, task_id=nid,
                instruction=instruction, user_message=user_message,
                artifacts=artifacts, depends_on=prev_ids,
                workspace_path=ws_path, code_output_required=True,
            )
            before_result = await harness.before_execution(h_ctx)
            if before_result.prompt:
                prompt = before_result.prompt
        except Exception:
            pass

    try:
        import time as _t
        t_start = _t.monotonic()
        node_timeout = 600
        if isinstance(node.config, dict):
            node_timeout = int(node.config.get("timeout", 600))

        # 执行模式由 Agent.execution_mode 决定（一处配置、处处生效）；
        # single_pass / chain_of_thought → 流式 token 推送；
        # plan_execute / react / rewoo / reflexion / self_consistency → AgentExecutor。
        node_config = node.config if isinstance(node.config, dict) else {}
        from app.services.collaboration.agent_executor import agent_executor as _exec
        exec_mode = _exec.agent_execution_mode(agent)
        _STREAMING_MODES = ("single_pass", "chain_of_thought")
        use_executor = exec_mode not in _STREAMING_MODES

        # 流式执行：逐 token 推送（仅 single_pass 模式用流式）
        content_parts: list[str] = []
        if not use_executor:
            try:
                from app.services.agent_chat import agent_chat_stream
                stream = agent_chat_stream(
                    db=db, agent=agent, message=prompt,
                    team_id=team_id, session_id=session_id,
                )
                async def _stream_with_timeout():
                    async for token in stream:
                        content_parts.append(token)
                        await send_fn({
                            "type": "stream_token",
                            "source": "langgraph",
                            "timestamp": datetime.now().isoformat(),
                            "payload": {
                                "agent": agent.name,
                                "token": token,
                                "token_type": "content_token",
                                "task_id": str(node.id),
                                "node_key": node_key,
                            },
                        })

                await asyncio.wait_for(_stream_with_timeout(), timeout=node_timeout)
                content = "".join(content_parts).strip()
                reasoning = {}
                latency_ms = int((_t.monotonic() - t_start) * 1000)
            except Exception:
                # 流式失败 → 回退到非流式
                logger.warning(f"Streaming failed for {label}, falling back to non-streaming")
                result = await asyncio.wait_for(
                    _agent_chat(
                        db=db, agent=agent, message=prompt,
                        return_reasoning=True, save_memory=False,
                        session_id=session_id, team_id=team_id,
                    ),
                    timeout=node_timeout,
                )
                latency_ms = int((_t.monotonic() - t_start) * 1000)
                content = (result.get("content") or "").strip()
                reasoning = result.get("reasoning", {}) or {}

        else:
            # ── AgentExecutor 模式 (plan_execute / react) ──
            from app.services.collaboration.agent_executor import agent_executor as _exec

            exec_result = await asyncio.wait_for(
                _exec.execute(
                    prompt=prompt, agent=agent, db=db,
                    session_id=session_id, team_id=team_id,
                    node_key=node_key, node_config=node_config,
                ),
                timeout=node_timeout,
            )
            latency_ms = int((_t.monotonic() - t_start) * 1000)
            content = (exec_result.get("content") or "").strip()
            reasoning = exec_result.get("reasoning", {}) or {}
            logger.info(
                f"LangGraph node [{label}] exec_mode={exec_result.get('exec_mode')} "
                f"iterations={exec_result.get('iterations', 1)}"
            )

        artifacts[nid] = content

        # ── M8: 广播产出就绪消息给其他 Agent ──
        try:
            from app.services.collaboration.m8_peer_mailbox import peer_mailbox as _pm
            _pm.send(
                session_id=session_id,
                from_agent=agent.name,
                to_agent="__all__",
                msg_type="share",
                content=f"完成了节点 [{label}]，产出 {len(content)} 字符。",
                references=[nid],
            )
        except Exception:
            pass

        await send_fn({
            "type": "agent_message",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "agent": agent.name,
                "content": content,
                "type": "message",
                "model": (reasoning.get("model_routing") or {}).get("selected_model"),
                "latency": latency_ms,
                "task_id": str(node.id),
                "node_key": node_key,
                "exec_mode": exec_mode,
            },
        })
        if reasoning:
            await send_fn({
                "type": "reasoning_complete",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "agent": agent.name,
                    "thinking_steps": reasoning.get("thinking_steps", ""),
                    "model_routing": reasoning.get("model_routing", {}),
                    "tool_calls": reasoning.get("tool_calls", []),
                    "decision_summary": f"执行节点 {label}",
                    "latency": latency_ms,
                    "exec_mode": exec_mode,
                    "iterations": reasoning.get("iterations", 1),
                },
            })

        # Harness: 执行后 Hook
        if harness:
            from app.services.harness import ExecutionContext as HEC, ExecutionResult as HER
            try:
                h_ctx = HEC(
                    session_id=session_id, team_id=str(team_id),
                    agent_id=str(agent.id), agent_name=agent.name,
                    node_key=node_key, task_id=str(task_id) if task_id else None,
                )
                h_result = HER(
                    content=content,
                    model=result.get("model", "unknown"),
                    provider=result.get("provider", "unknown"),
                    latency_ms=latency_ms,
                    usage=result.get("usage", {}),
                )
                await harness.after_execution(h_ctx, h_result)
            except Exception:
                pass

        files_written = _extract_node_files(content, node_key, ws_path)
        if files_written:
            logger.info(
                f"langgraph node [{label}] wrote {len(files_written)} files: {files_written}"
            )
            await send_fn({
                "type": "files_changed",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "files": [
                        {"name": f, "status": "created",
                         "producer_agent_name": agent.name,
                         "producer_task_id": str(node.id)}
                        for f in files_written
                    ],
                },
            })

        await send_fn({
            "type": "task_status",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"task_id": str(node.id), "status": "done", "duration": latency_ms},
        })
    except asyncio.TimeoutError:
        logger.warning(f"langgraph node {label} timed out after {node_timeout}s")
        alt_nid = timeout_edge.get(nid)
        if alt_nid:
            alt_node_label = alt_nid  # fallback to ID
            await send_fn({
                "type": "task_status",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": str(node.id), "status": "failed",
                            "error": f"超时，路由到备用节点"},
            })
        else:
            await send_fn({
                "type": "task_status",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": str(node.id), "status": "failed",
                            "error": f"执行超时（{node_timeout}s）"},
            })
    except Exception as e:
        logger.error(f"langgraph node {label} failed: {e}")
        alt_nid = fallback_edge.get(nid)
        if alt_nid:
            await send_fn({
                "type": "task_status",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": str(node.id), "status": "failed",
                            "error": f"执行失败，降级到备用节点: {str(e)[:200]}"},
            })
        else:
            await send_fn({
                "type": "task_status",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": str(node.id), "status": "failed", "error": str(e)},
            })


def _eval_condition_fast(expression: str, artifact_text: str) -> bool | None:
    """Evaluate condition expressions that don't need LLM. Returns None if LLM needed."""
    if not expression or not expression.strip():
        return True
    expr = expression.strip()

    if expr.startswith("contains:"):
        return expr[len("contains:"):].strip().lower() in artifact_text.lower()
    if expr.startswith("not_contains:"):
        return expr[len("not_contains:"):].strip().lower() not in artifact_text.lower()
    if expr.startswith("length_gt:"):
        return len(artifact_text) > int(expr[len("length_gt:"):].strip())
    if expr.startswith("length_lt:"):
        return len(artifact_text) < int(expr[len("length_lt:"):].strip())

    if expr.startswith("json_path:"):
        import json as _json
        rest = expr[len("json_path:"):].strip()
        parts = rest.split("==", 1)
        if len(parts) == 2:
            jpath = parts[0].strip()
            expected = parts[1].strip().strip('\'"')
            try:
                obj = _json.loads(artifact_text)
            except _json.JSONDecodeError:
                m = _re.search(r'\{[^{}]*\}', artifact_text, _re.DOTALL)
                if m:
                    try:
                        obj = _json.loads(m.group(0))
                    except _json.JSONDecodeError:
                        return False
                else:
                    return False
            for p in jpath.lstrip("$").strip(".").split("."):
                if p.isdigit() and isinstance(obj, list):
                    obj = obj[int(p)]
                elif isinstance(obj, dict):
                    obj = obj.get(p)
                else:
                    return False
            return str(obj).strip('"\'') == expected
        return False

    # llm_judge or unknown → caller must handle with LLM
    return None


async def run(
    session_id: str,
    team,
    user_message: str,
    team_agents: list,
    available_roles: list,
    send_fn: SendFn,
    harness=None,
) -> None:
    """加载 workflow + node_bindings，沿边遍历图执行各节点。

    设计原则：引擎是工作流定义的执行器，不参与决策。
    所有流程控制由节点类型 + 边的类型 + 条件表达式的求值结果决定。
    """
    logger.info("[LG] run() called")
    from app.core.database import async_session
    from app.services.team_mode_service import TeamModeService
    from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
    from app.models.agent import Agent
    from app.services.agent_chat import agent_chat
    from collections import defaultdict as _defaultdict

    async with async_session() as db:
        svc = TeamModeService(db)
        cfg = await svc.get_langgraph_config(team.id)
        if not cfg or not cfg.workflow_id:
            await send_fn({
                "type": "error", "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": "该团队未绑定 workflow，无法执行图编排"},
            })
            return

        # 加载 workflow + nodes + edges + bindings
        wf = await db.get(Workflow, cfg.workflow_id)
        if not wf:
            await send_fn({"type": "error", "source": "langgraph",
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"message": "workflow 不存在"}})
            return

        nodes = (await db.execute(
            select(WorkflowNode).where(WorkflowNode.workflow_id == cfg.workflow_id)
        )).scalars().all()
        edges = (await db.execute(
            select(WorkflowEdge).where(WorkflowEdge.workflow_id == cfg.workflow_id)
        )).scalars().all()
        if not nodes:
            await send_fn({"type": "error", "source": "langgraph",
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"message": "workflow 没有节点"}})
            return

        # 加载节点 → Agent 绑定
        bindings = await svc.get_node_bindings(team.id)
        node_to_agent: dict[str, uuid.UUID] = {
            b.node_key: b.agent_id for b in bindings
        }

        # ── 构建索引 ──
        node_by_id = {str(n.id): n for n in nodes}
        nkey_to_nid: dict[str, str] = {}
        for n in nodes:
            if n.node_key:
                nkey_to_nid[n.node_key] = str(n.id)

        # 按 source_id 分组边
        edges_by_source: dict[str, list] = _defaultdict(list)
        for e in edges:
            edges_by_source[str(e.source_id)].append(e)

        # 仅 forward 边构建邻接表（用于 BFS 下游查找）
        adj: dict[str, list[str]] = _defaultdict(list)
        for e in edges:
            if (e.type or "forward").lower() == "forward":
                adj[str(e.source_id)].append(str(e.target_id))

        # 特殊边映射（用于 agent 执行异常时的路由）
        timeout_edge: dict[str, str] = {}
        fallback_edge: dict[str, str] = {}
        for e in edges:
            sid, tid = str(e.source_id), str(e.target_id)
            if (e.type or "").lower() == "timeout":
                timeout_edge[sid] = tid
            elif (e.type or "").lower() == "fallback":
                fallback_edge[sid] = tid

        # ── 推送 routing + task_dag ──
        await send_fn({
            "type": "routing_decision", "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"mode": "multi_agent", "agent_name": wf.name or "图编排"},
        })

        executable_nodes = [n for n in nodes if n.type.lower() not in ('start', 'end')]
        normalized_phases = [{
            "id": "phase-flow", "name": wf.name or "执行流程",
            "tasks": [
                {"id": str(n.id), "name": n.label or n.node_key or "节点",
                 "agent_id": str(node_to_agent.get(n.node_key, "")),
                 "agent_name": "", "agent_emoji": "🔀", "depends_on": []}
                for n in executable_nodes
            ],
        }]
        await send_fn({
            "type": "task_dag", "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"phases": normalized_phases, "total_tasks": len(executable_nodes)},
        })

        # ── 初始化遍历状态 ──
        artifacts: dict[str, str] = {}
        visit_count: dict[str, int] = _defaultdict(int)
        MAX_RETRIES = 3  # 循环保护上限
        execution_order: list[str] = []  # 记录执行顺序

        # 找到 start 节点作为入口
        start_node = next((n for n in nodes if n.type.lower() == 'start'), None)
        if not start_node:
            await send_fn({"type": "error", "source": "langgraph",
                           "timestamp": datetime.now().isoformat(),
                           "payload": {"message": "workflow 缺少 start 节点"}})
            return
        current_nid = str(start_node.id)

        # workspace 路径
        ws_path = ""
        try:
            from app.services.workspace.manager import workspace_manager
            ws = workspace_manager.get_or_create(session_id)
            ws_path = ws.path if ws else ""
        except Exception:
            pass

        # ── 主循环：沿边遍历图 ──
        hitl_paused = False
        while True:
            current_node = node_by_id.get(current_nid)
            if not current_node:
                break
            current_type = current_node.type.lower() if current_node.type else ""

            # 到达 end 节点 → 完成
            if current_type == 'end':
                break

            # 循环保护
            visit_count[current_nid] += 1
            if visit_count[current_nid] > MAX_RETRIES:
                logger.warning(f"Node {current_nid} visited {visit_count[current_nid]} times, breaking loop")
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "failed",
                                "error": f"循环次数超限 ({MAX_RETRIES})"},
                })
                break

            # 跳过 start 节点
            if current_type == 'start':
                next_nid = _resolve_next_edge(
                    current_nid, None, edges_by_source, artifacts,
                    node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
                )
                current_nid = next_nid or ""
                continue

            # ── 执行节点 ──
            node_key = current_node.node_key or current_nid
            label = current_node.label or node_key
            execution_order.append(current_nid)

            if current_type in ('agent', 'task', 'worker'):
                # Agent 节点执行
                agent_id = node_to_agent.get(node_key)
                if not agent_id:
                    await send_fn({
                        "type": "task_status", "source": "langgraph",
                        "timestamp": datetime.now().isoformat(),
                        "payload": {"task_id": current_nid, "status": "failed", "error": "未绑定 Agent"},
                    })
                    next_nid = _resolve_next_edge(
                        current_nid, None, edges_by_source, artifacts,
                        node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
                    )
                    current_nid = next_nid or ""
                    continue

                agent = await db.get(Agent, agent_id)
                if not agent:
                    next_nid = _resolve_next_edge(
                        current_nid, None, edges_by_source, artifacts,
                        node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
                    )
                    current_nid = next_nid or ""
                    continue

                # 查找前置 HITL 节点的反馈，注入到 agent 的 instruction 中（打回场景）
                predecessor_artifact = ""
                for pid in adj:
                    if current_nid in adj[pid]:
                        pnode = node_by_id.get(pid)
                        if pnode and pnode.type.lower() == 'hitl' and pid in artifacts:
                            predecessor_artifact = artifacts[pid]
                            break

                saved_instruction = None
                if predecessor_artifact and predecessor_artifact.strip() not in ("approve", "reject", "skip", "cancel", ""):
                    # 有实际反馈内容 → 注入到 instruction 前面
                    if isinstance(current_node.config, dict):
                        saved_instruction = current_node.config.get("instruction", "")
                        current_node.config["instruction"] = (
                            f"## ⚠️ 审核反馈：请根据以下意见修改后重新输出\n"
                            f"{predecessor_artifact[:2000]}\n\n"
                            f"---\n\n"
                            f"{saved_instruction or ''}"
                        )
                    logger.info(f"Agent [{label}]: injected feedback ({len(predecessor_artifact)} chars)")

                await _execute_agent_node(
                    nid=current_nid, node=current_node, agent=agent, db=db,
                    artifacts=artifacts,
                    node_deps={current_nid: [p for p in adj if current_nid in adj[p]]},
                    node_key=node_key, label=label, user_message=user_message,
                    session_id=session_id, team_id=str(team.id),
                    send_fn=send_fn, ws_path=ws_path, harness=harness,
                    timeout_edge=timeout_edge, fallback_edge=fallback_edge,
                )

                # 恢复原始 instruction
                if saved_instruction is not None:
                    current_node.config["instruction"] = saved_instruction

            elif current_type == 'hitl':
                # HITL 节点 → 暂停等待人工输入
                hconfig = current_node.config if isinstance(current_node.config, dict) else {}
                hitl_msg = hconfig.get("instruction") or hconfig.get("prompt") or f"请审核并确认节点「{label}」的输出。"
                hitl_timeout = hconfig.get("timeout", 300)

                # 生成唯一的调用 ID，用于前后端匹配通知和回答
                hitl_invoke_id = str(uuid.uuid4())
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "running"},
                })
                await send_fn({
                    "type": "request_clarification", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "task_id": current_nid, "node_key": node_key, "label": label,
                        "message": hitl_msg, "timeout": hitl_timeout,
                        "mode": "langgraph_hitl", "type": "review",
                        "hitl_invoke_id": hitl_invoke_id,
                        "options": [
                            {"label": "✅ 通过", "value": "approve", "description": "审核通过，继续执行"},
                            {"label": "❌ 打回", "value": "reject", "description": "打回重新修改"},
                            {"label": "💬 自定义回复", "value": "answer", "description": "输入审核意见"},
                        ],
                    },
                })

                # 保存暂停状态
                _paused[session_id] = {
                    "team": team, "user_message": user_message,
                    "team_agents": team_agents, "available_roles": available_roles,
                    "pause_nid": current_nid,
                    "hitl_invoke_id": hitl_invoke_id,
                    "artifacts": dict(artifacts),
                    "visit_count": dict(visit_count),
                    "execution_order": list(execution_order),
                    "node_by_id": {k: v for k, v in node_by_id.items()},
                    "node_to_agent": dict(node_to_agent),
                    "nkey_to_nid": dict(nkey_to_nid),
                    "edges_by_source": {k: list(v) for k, v in edges_by_source.items()},
                    "adj": dict(adj),
                    "ws_path": ws_path,
                }
                asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
                hitl_paused = True
                break  # 暂停，等待 resume

            elif current_type in ('condition', 'router'):
                # 条件/路由节点：不执行 agent，只做边解析
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "running"},
                })
                # 收集前置产物作为当前节点的结果
                combined_input = "\n".join(
                    artifacts.get(pid, "") for pid in adj
                    if current_nid in adj.get(pid, [])
                )
                next_nid = await _resolve_and_exec(
                    current_nid, combined_input, edges_by_source, artifacts,
                    node_by_id, nkey_to_nid, adj, db, session_id, str(team.id), _exec_one,
                )
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "done", "duration": 0},
                })
                current_nid = next_nid or ""
                continue

            elif current_type == 'validation':
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "running"},
                })
                combined_input = "\n".join(
                    artifacts.get(pid, "") for pid in adj
                    if current_nid in adj.get(pid, [])
                )
                next_nid = await _resolve_and_exec(
                    current_nid, combined_input, edges_by_source, artifacts,
                    node_by_id, nkey_to_nid, adj, db, session_id, str(team.id), _exec_one,
                )
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "done", "duration": 0},
                })
                current_nid = next_nid or ""
                continue

            # 解析下一条边
            current_result = artifacts.get(current_nid, "")
            next_nid = _resolve_next_edge(
                current_nid, current_result, edges_by_source, artifacts,
                node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
            )
            if not next_nid:
                break
            current_nid = next_nid

        # ── 完成（HITL 暂停时跳过） ──
        if not hitl_paused:
            # 清理 round-robin 计数器
            rr_prefix = f"rr_{session_id}_"
            for k in list(_rr_counter.keys()):
                if k.startswith(rr_prefix):
                    del _rr_counter[k]
            await send_fn({
                "type": "message_complete", "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": f"流程执行完成（{len(execution_order)} 节点）"},
            })


def _extract_node_files(content: str, node_key: str, ws_path: str) -> list[str]:
    """Extract code blocks from agent output and write them to workspace files.
    Delegates to shared workspace_utils.extract_files_from_content.
    """
    from app.services.collaboration.workspace_utils import extract_files_from_content
    return extract_files_from_content(content, ws_path, source_label=f"langgraph/{node_key}")


async def resume(session_id: str, user_response, send_fn: SendFn, harness=None) -> None:
    """从 HITL 节点恢复执行。用户响应作为 HITL 节点的 artifact，
    然后沿边继续遍历图，复用 run() 的边解析逻辑。
    """
    from collections import defaultdict as _defaultdict

    state = _paused.pop(session_id, None)
    if not state:
        state = await _load_paused_state(session_id)
    if not state:
        await send_fn({
            "type": "message_complete", "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"message": "没有可恢复的 HITL 暂停状态"},
        })
        return

    from app.core.database import async_session
    from app.models.agent import Agent

    # 恢复遍历状态（兼容新旧 pause state 格式）
    pause_nid = state.get("pause_nid", state.get("hitl_nid", ""))
    artifacts: dict[str, str] = state["artifacts"]
    visit_count: dict[str, int] = _defaultdict(int, state.get("visit_count", {}))
    execution_order: list[str] = state.get("execution_order", [])
    node_by_id: dict = state["node_by_id"]
    node_to_agent: dict = state["node_to_agent"]
    nkey_to_nid: dict[str, str] = state.get("nkey_to_nid", {})
    edges_by_source: dict[str, list] = state.get("edges_by_source", {})
    adj: dict[str, list[str]] = _defaultdict(list, state.get("adj", {}))
    ws_path: str = state.get("ws_path", "")
    team = state["team"]
    user_message: str = state.get("user_message", "")
    team_agents = state.get("team_agents", [])
    available_roles = state.get("available_roles", [])
    MAX_RETRIES = 3

    async with async_session() as db:
        user_content = user_response.get("content") if isinstance(user_response, dict) else str(user_response)
        hitl_node = node_by_id.get(pause_nid)
        artifacts[pause_nid] = user_content

        if hitl_node:
            await send_fn({
                "type": "task_status", "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": pause_nid, "status": "done", "duration": 0},
            })
            await send_fn({
                "type": "agent_message", "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "agent": "人工审核", "content": user_content,
                    "type": "message", "model": None, "latency": 0,
                    "task_id": pause_nid,
                    "node_key": hitl_node.node_key or pause_nid,
                },
            })

        # 从 HITL 节点解析下一条边，继续主循环
        # 先走一步：从 HITL 到下一个节点（通常是 condition）
        current_nid = pause_nid
        hitl_paused = False
        next_nid = _resolve_next_edge(
            current_nid, artifacts.get(current_nid, ""), edges_by_source, artifacts,
            node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
        )
        if next_nid:
            current_nid = next_nid

        while True:
            current_node = node_by_id.get(current_nid)
            if not current_node:
                break
            current_type = current_node.type.lower() if current_node.type else ""

            if current_type == 'end':
                break

            visit_count[current_nid] += 1
            if visit_count[current_nid] > MAX_RETRIES:
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "failed",
                                "error": f"循环次数超限 ({MAX_RETRIES})"},
                })
                break

            node_key = current_node.node_key or current_nid
            label = current_node.label or node_key
            execution_order.append(current_nid)

            # ── 执行当前节点 ──
            if current_type in ('agent', 'task', 'worker'):
                agent_id = node_to_agent.get(node_key)
                if not agent_id:
                    next_nid = _resolve_next_edge(current_nid, None, edges_by_source, artifacts, node_by_id, nkey_to_nid, adj, db, session_id, str(team.id))
                    current_nid = next_nid or ""
                    continue
                agent = await db.get(Agent, agent_id)
                if not agent:
                    next_nid = _resolve_next_edge(current_nid, None, edges_by_source, artifacts, node_by_id, nkey_to_nid, adj, db, session_id, str(team.id))
                    current_nid = next_nid or ""
                    continue

                # 注入 HITL 用户反馈
                user_fb = artifacts.get(pause_nid, "")
                if user_fb and user_fb.strip() not in ("approve", "reject", "skip", "cancel", ""):
                    saved_inst = None
                    if isinstance(current_node.config, dict):
                        saved_inst = current_node.config.get("instruction", "")
                        current_node.config["instruction"] = (
                            f"## ⚠️ 审核未通过 — 请根据以下反馈重新执行\n\n"
                            f"**审核意见**: {user_fb[:2000]}\n\n"
                            f"请针对性修改后重新输出。\n\n"
                        ) + (saved_inst or "")
                    await _execute_agent_node(
                        nid=current_nid, node=current_node, agent=agent, db=db,
                        artifacts=artifacts,
                        node_deps={current_nid: [p for p in adj if current_nid in adj[p]]},
                        node_key=node_key, label=label, user_message=user_message,
                        session_id=session_id, team_id=str(team.id),
                        send_fn=send_fn, ws_path=ws_path, harness=harness,
                    )
                    if saved_inst is not None:
                        current_node.config["instruction"] = saved_inst
                else:
                    await _execute_agent_node(
                        nid=current_nid, node=current_node, agent=agent, db=db,
                        artifacts=artifacts,
                        node_deps={current_nid: [p for p in adj if current_nid in adj[p]]},
                        node_key=node_key, label=label, user_message=user_message,
                        session_id=session_id, team_id=str(team.id),
                        send_fn=send_fn, ws_path=ws_path, harness=harness,
                    )

            elif current_type == 'hitl':
                hconfig = current_node.config if isinstance(current_node.config, dict) else {}
                hitl_msg = hconfig.get("instruction") or hconfig.get("prompt") or f"请审核并确认节点「{label}」的输出。"
                hitl_invoke_id = str(uuid.uuid4())
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "running"},
                })
                await send_fn({
                    "type": "request_clarification", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "task_id": current_nid, "node_key": node_key, "label": label,
                        "message": hitl_msg, "timeout": hconfig.get("timeout", 300),
                        "mode": "langgraph_hitl", "type": "review",
                        "hitl_invoke_id": hitl_invoke_id,
                        "options": [
                            {"label": "✅ 通过", "value": "approve", "description": "审核通过，继续执行"},
                            {"label": "❌ 打回", "value": "reject", "description": "打回重新修改"},
                            {"label": "💬 自定义回复", "value": "answer", "description": "输入审核意见"},
                        ],
                    },
                })
                _paused[session_id] = {
                    "team": team, "user_message": user_message,
                    "team_agents": team_agents, "available_roles": available_roles,
                    "pause_nid": current_nid,
                    "hitl_invoke_id": hitl_invoke_id,
                    "artifacts": dict(artifacts),
                    "visit_count": dict(visit_count),
                    "execution_order": list(execution_order),
                    "node_by_id": {k: v for k, v in node_by_id.items()},
                    "node_to_agent": dict(node_to_agent),
                    "nkey_to_nid": dict(nkey_to_nid),
                    "edges_by_source": edges_by_source,
                    "adj": dict(adj),
                    "ws_path": ws_path,
                }
                asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
                hitl_paused = True
                return

            elif current_type in ('condition', 'router', 'validation'):
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "running"},
                })
                combined_input = "\n".join(
                    artifacts.get(pid, "") for pid in adj
                    if current_nid in adj.get(pid, [])
                )
                # resume 中的 exec_fn：执行 agent 节点（带反馈注入）
                async def _exec_resume_target(nid: str):
                    tnode = node_by_id.get(nid)
                    if not tnode: return
                    tkey = tnode.node_key or nid
                    tlabel = tnode.label or tkey
                    taid = node_to_agent.get(tkey)
                    if not taid: return
                    tagent = await db.get(Agent, taid)
                    if not tagent: return
                    await _execute_agent_node(
                        nid=nid, node=tnode, agent=tagent, db=db,
                        artifacts=artifacts,
                        node_deps={nid: [p for p in adj if nid in adj[p]]},
                        node_key=tkey, label=tlabel, user_message=user_message,
                        session_id=session_id, team_id=str(team.id),
                        send_fn=send_fn, ws_path=ws_path, harness=harness,
                    )
                next_edge_nid = await _resolve_and_exec(
                    current_nid, combined_input, edges_by_source, artifacts,
                    node_by_id, nkey_to_nid, adj, db, session_id, str(team.id),
                    _exec_resume_target,
                )
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": current_nid, "status": "done", "duration": 0},
                })
                if next_edge_nid:
                    current_nid = next_edge_nid
                    continue
                break

            # ── 解析下一条边 ──
            current_result = artifacts.get(current_nid, "")
            next_nid = _resolve_next_edge(
                current_nid, current_result, edges_by_source, artifacts,
                node_by_id, nkey_to_nid, adj, db, session_id, str(team.id)
            )
            if not next_nid:
                break
            current_nid = next_nid

        # 完成
        if not hitl_paused:
            _paused.pop(session_id, None)
            rr_prefix = f"rr_{session_id}_"
            for k in list(_rr_counter.keys()):
                if k.startswith(rr_prefix):
                    del _rr_counter[k]
            await send_fn({
                "type": "message_complete", "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": f"流程执行完成（{len(execution_order)} 节点）"},
            })
