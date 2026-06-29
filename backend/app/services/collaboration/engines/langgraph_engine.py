"""图编排式引擎（LangGraph 风格）

机制：
  1. 读取团队绑定的 workflow（节点 + 边）
  2. 把每个节点绑定到一个具体 Agent（via TeamLanggraphNodeBinding）
  3. 用 LangGraph StateGraph 动态构建图
  4. 流式执行，每个节点完成时推送进度

简化设计：当前实现走"拓扑顺序+条件分支"，不支持循环（足够覆盖大部分 SOP 场景）。

模块拆分：
- langgraph_pause.py  — HITL 暂停/恢复状态持久化
- langgraph_engine.py — 主执行引擎（拓扑排序、节点执行、流程控制）
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

        # 检查是否需要非 default 执行模式
        node_config = node.config if isinstance(node.config, dict) else {}
        exec_mode = node_config.get("execution_mode", "")
        use_executor = exec_mode in ("plan_execute", "react")

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
) -> None:
    """加载 workflow + node_bindings，按图执行各节点。"""
    from app.core.database import async_session
    from app.services.team_mode_service import TeamModeService
    from app.models.workflow import Workflow, WorkflowNode, WorkflowEdge
    from app.models.agent import Agent
    from app.services.agent_chat import agent_chat

    async with async_session() as db:
        svc = TeamModeService(db)
        cfg = await svc.get_langgraph_config(team.id)
        if not cfg or not cfg.workflow_id:
            await send_fn({
                "type": "error",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": "该团队未绑定 workflow，无法执行图编排"},
            })
            return

        # 加载 workflow + nodes + edges
        wf = await db.get(Workflow, cfg.workflow_id)
        if not wf:
            await send_fn({
                "type": "error",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": "workflow 不存在"},
            })
            return

        nodes = (await db.execute(
            select(WorkflowNode).where(WorkflowNode.workflow_id == cfg.workflow_id)
        )).scalars().all()
        edges = (await db.execute(
            select(WorkflowEdge).where(WorkflowEdge.workflow_id == cfg.workflow_id)
        )).scalars().all()
        if not nodes:
            await send_fn({
                "type": "error",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": "workflow 没有节点"},
            })
            return

        # 加载节点 → Agent 绑定
        bindings = await svc.get_node_bindings(team.id)
        node_to_agent: dict[str, uuid.UUID] = {
            b.node_key: b.agent_id for b in bindings
        }

        # 推送 routing
        await send_fn({
            "type": "routing_decision",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"mode": "multi_agent", "agent_name": wf.name or "图编排"},
        })

        # Start / End 是工作流标记节点，不参与实际执行
        NON_EXECUTABLE = frozenset({'start', 'end'})
        executable_nodes = [n for n in nodes if n.type.lower() not in NON_EXECUTABLE]

        # 计算节点依赖关系（从 Forward 边推导），只保留可执行节点间的依赖
        # Reject/Escalate/Timeout/Fallback 是异常路径，不参与拓扑排序
        node_deps: dict[str, list[str]] = defaultdict(list)
        executable_ids = {str(n.id) for n in executable_nodes}
        for e in edges:
            sid, tid = str(e.source_id), str(e.target_id)
            if (e.type or "").lower() != "forward":
                continue
            if sid in executable_ids and tid in executable_ids:
                node_deps[tid].append(sid)

        # 推送 task_dag：只展示可执行节点
        normalized_phases = [{
            "id": "phase-flow",
            "name": wf.name or "执行流程",
            "tasks": [
                {
                    "id": str(n.id),
                    "name": n.label or n.node_key or "节点",
                    "agent_id": str(node_to_agent.get(n.node_key, "")),
                    "agent_name": "",
                    "agent_emoji": "🔀",
                    "depends_on": node_deps.get(str(n.id), []),
                }
                for n in executable_nodes
            ],
        }]
        await send_fn({
            "type": "task_dag",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "phases": normalized_phases,
                "total_tasks": len(executable_nodes),
            },
        })

        # 拓扑排序（只对可执行节点，只考虑 Forward 边）
        # Reject/Escalate/Timeout/Fallback 是异常路径，不参与 DAG 排序
        node_by_id = {str(n.id): n for n in executable_nodes}
        in_degree: dict[str, int] = defaultdict(int)
        adj: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            sid, tid = str(e.source_id), str(e.target_id)
            if (e.type or "").lower() != "forward":
                continue
            if sid in node_by_id and tid in node_by_id:
                adj[sid].append(tid)
                in_degree[tid] += 1
        # 保存原始入度（拓扑排序会修改 in_degree，层级计算需要原始值）
        _in_degree_orig = defaultdict(int, in_degree)
        queue = deque([nid for nid in node_by_id if in_degree[nid] == 0])
        execution_order: list[str] = []
        while queue:
            nid = queue.popleft()
            execution_order.append(nid)
            for nxt in adj[nid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(execution_order) < len(node_by_id):
            await send_fn({
                "type": "error",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"message": "workflow 存在循环依赖，无法执行"},
            })
            return

        # 按拓扑层级分组（同层节点无相互依赖，可并行执行）
        levels: list[list[str]] = []
        _in_deg = defaultdict(int, _in_degree_orig)  # 使用保存的原始入度
        _lvl_q = deque([nid for nid in node_by_id if _in_deg[nid] == 0])
        while _lvl_q:
            lvl = list(_lvl_q)
            _lvl_q.clear()
            levels.append(lvl)
            for nid in lvl:
                for nxt in adj.get(nid, []):
                    _in_deg[nxt] -= 1
                    if _in_deg[nxt] == 0:
                        _lvl_q.append(nxt)

        artifacts: dict[str, str] = {}

        # 节点 key → id 映射（Condition/Router 的 config 用 node_key 引用目标）
        nkey_to_nid: dict[str, str] = {}
        for n in executable_nodes:
            if n.node_key:
                nkey_to_nid[n.node_key] = str(n.id)

        # 活跃节点集（Condition/Router 会从中移除未选择的分支）
        active_nodes: set[str] = set(node_by_id.keys())

        def _compute_exclusive_downstream(nid: str, exclude_nids: set[str]) -> set[str]:
            """BFS from nid, only following nodes whose ALL active predecessors are in the result set.
            Stops at nodes that have another active path into them (not in exclude_nids)."""
            result: set[str] = set()
            q = deque([nid])
            while q:
                cur = q.popleft()
                if cur in result:
                    continue
                result.add(cur)
                for nxt in adj.get(cur, []):
                    if nxt in result:
                        continue
                    # Check if nxt has ANY active predecessor not in (result ∪ exclude_nids)
                    preds = node_deps.get(nxt, [])
                    other_active = [
                        p for p in preds
                        if p in active_nodes and p != cur and p not in result and p not in exclude_nids
                    ]
                    if not other_active:
                        q.append(nxt)
            return result

        async def _eval_condition(expression: str, artifact_text: str, node_label: str) -> bool:
            """Evaluate a condition expression, using LLM only when needed."""
            fast = _eval_condition_fast(expression, artifact_text)
            if fast is not None:
                return fast

            # llm_judge or unknown pattern → LLM
            expr = expression.strip()
            criteria = expr[len("llm_judge:"):].strip() if expr.startswith("llm_judge:") else expr
            try:
                stmt2 = select(Agent).limit(1)
                result2 = await db.execute(stmt2)
                j_agent = result2.scalar_one_or_none()
                if not j_agent:
                    return True
                jp = (f"你是一个条件判断器。请根据以下条件判断前置产物的内容是否符合。\n\n"
                      f"## 判断条件\n{criteria}\n\n## 前置产物内容\n{artifact_text[:2000]}\n\n请只回答 YES 或 NO。")
                jr = await agent_chat(
                    db=db, agent=j_agent, message=jp,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=str(team.id),
                )
                return (jr.get("content") or "").strip().upper().lstrip('*_# ').startswith("YES")
            except Exception:
                return True
        ws_path = ""
        try:
            from app.services.workspace.manager import workspace_manager
            ws = workspace_manager.get_or_create(session_id)
            ws_path = ws.path if ws else ""
        except Exception:
            pass

        # 特殊边映射（Timeout / Fallback 是异常路径，不参与拓扑排序）
        timeout_edge: dict[str, str] = {}   # source_nid → target_nid
        fallback_edge: dict[str, str] = {}  # source_nid → target_nid
        for e in edges:
            sid, tid = str(e.source_id), str(e.target_id)
            etype = (e.type or "").lower()
            if etype == "timeout" and sid in node_by_id and tid in node_by_id:
                timeout_edge[sid] = tid
            elif etype == "fallback" and sid in node_by_id and tid in node_by_id:
                fallback_edge[sid] = tid

        async def _exec_one(nid: str) -> None:
            """Thin wrapper around shared _execute_agent_node."""
            node = node_by_id[nid]
            node_key = node.node_key or str(node.id)
            label = node.label or node_key

            agent_id = node_to_agent.get(node_key)
            if not agent_id:
                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(node.id), "status": "failed", "error": "未绑定 Agent"},
                })
                return
            agent = await db.get(Agent, agent_id)
            if not agent:
                return

            await _execute_agent_node(
                nid=nid, node=node, agent=agent, db=db,
                artifacts=artifacts, node_deps=node_deps,
                node_key=node_key, label=label,
                user_message=user_message,
                session_id=session_id, team_id=str(team.id),
                send_fn=send_fn, ws_path=ws_path,
                harness=harness,
                timeout_edge=timeout_edge, fallback_edge=fallback_edge,
            )

        # 逐层执行：层内节点 parallel，层间 sequential
        hitl_paused = False
        for level_idx, level in enumerate(levels):
            # 按节点类型分组，同时过滤掉 inactive 节点
            agent_nids = [nid for nid in level
                          if node_by_id[nid].type.lower() == 'agent'
                          and nid in active_nodes]
            condition_nids = [nid for nid in level
                              if node_by_id[nid].type.lower() == 'condition'
                              and nid in active_nodes]
            router_nids = [nid for nid in level
                           if node_by_id[nid].type.lower() == 'router'
                           and nid in active_nodes]
            validation_nids = [nid for nid in level
                               if node_by_id[nid].type.lower() == 'validation'
                               and nid in active_nodes]
            hitl_nids = [nid for nid in level
                         if node_by_id[nid].type.lower() == 'hitl'
                         and nid in active_nodes]

            # 1) 执行 Agent 节点
            if agent_nids:
                if len(agent_nids) == 1:
                    await _exec_one(agent_nids[0])
                else:
                    await asyncio.gather(*[_exec_one(nid) for nid in agent_nids])

            # 2) 求值 Condition 节点（裁剪分支）
            for cnid in condition_nids:
                cnode = node_by_id[cnid]
                clabel = cnode.label or cnode.node_key or str(cnid)
                cconfig = cnode.config if isinstance(cnode.config, dict) else {}
                expression = cconfig.get("expression", "")
                on_true_key = cconfig.get("on_true_node_key", "")
                on_false_key = cconfig.get("on_false_node_key", "")

                # 收集前置 artifact 用于条件求值
                prev_ids = node_deps.get(cnid, [])
                combined_artifact = "\n".join(
                    artifacts.get(pid, "") for pid in prev_ids
                )

                cond_result = await _eval_condition(expression, combined_artifact, clabel)

                chosen_key = on_true_key if cond_result else on_false_key
                unchosen_key = on_false_key if cond_result else on_true_key

                logger.info(
                    f"Condition [{clabel}]: expr='{expression[:60]}' → {cond_result}, "
                    f"chosen={chosen_key}, pruned={unchosen_key}"
                )

                # 裁剪未选择的分支
                if unchosen_key and unchosen_key in nkey_to_nid:
                    prune_nid = nkey_to_nid[unchosen_key]
                    # 查找从 condition node 到此 target 的边（用于 exclude_nids）
                    pruned = _compute_exclusive_downstream(prune_nid, {cnid})
                    active_nodes.difference_update(pruned)
                    for pnid in pruned:
                        pn = node_by_id.get(pnid)
                        plabel = pn.label if pn else pnid
                        await send_fn({
                            "type": "task_status",
                            "source": "langgraph",
                            "timestamp": datetime.now().isoformat(),
                            "payload": {"task_id": pnid, "status": "skipped",
                                        "error": f"条件节点 [{clabel}] 未选择此路径"},
                        })

                # Condition 节点本身标记完成
                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(cnode.id), "status": "done", "duration": 0},
                })

            # 3) Router 节点
            for rnid in router_nids:
                rnode = node_by_id[rnid]
                rlabel = rnode.label or rnode.node_key or str(rnid)
                rconfig = rnode.config if isinstance(rnode.config, dict) else {}
                strategy = rconfig.get("strategy", "llm_select")
                candidates: list[str] = rconfig.get("candidates", [])
                fallback_key = rconfig.get("fallback_node_key", "")

                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(rnode.id), "status": "running"},
                })

                # 收集前置产物
                prev_ids = node_deps.get(rnid, [])
                combined_artifact = "\n".join(
                    artifacts.get(pid, "") for pid in prev_ids
                )

                chosen_key = fallback_key
                chosen_reason = ""

                if strategy == "broadcast":
                    # 广播模式：所有候选都激活，不裁剪
                    chosen_key = "__broadcast__"
                    chosen_reason = "广播到所有候选节点"
                elif strategy == "llm_select":
                    # LLM 选择最佳候选
                    if candidates:
                        cand_lines = []
                        for ckey in candidates:
                            cnid = nkey_to_nid.get(ckey, "")
                            cnode = node_by_id.get(cnid)
                            clabel = cnode.label if cnode else ckey
                            cand_lines.append(f"- {ckey}: {clabel}")
                        cand_list = "\n".join(cand_lines)
                        stmt_r = select(Agent).limit(1)
                        result_r = await db.execute(stmt_r)
                        r_agent = result_r.scalar_one_or_none()
                        if r_agent:
                            route_prompt = (
                                f"你是一个路由器。请根据前置产物内容，从候选节点中选择最合适的一个。\n\n"
                                f"## 候选节点\n{cand_list}\n\n"
                                f"## 前置产物\n{combined_artifact[:2000]}\n\n"
                                f"请只回复最合适的候选节点的 key（如 `{candidates[0]}`），"
                                f"不要回复其他内容。"
                            )
                            route_result = await agent_chat(
                                db=db, agent=r_agent, message=route_prompt,
                                return_reasoning=False, save_memory=False,
                                session_id=session_id, team_id=str(team.id),
                            )
                            route_content = (route_result.get("content") or "").strip()
                            # Extract candidate key from response
                            for ckey in candidates:
                                if ckey in route_content:
                                    chosen_key = ckey
                                    chosen_reason = f"LLM 选择: {route_content[:100]}"
                                    break
                            if not chosen_key:
                                chosen_key = candidates[0]
                                chosen_reason = f"LLM 无法确定，默认选第一个: {route_content[:80]}"
                        else:
                            chosen_key = candidates[0] if candidates else fallback_key
                            chosen_reason = "无可用 Agent，默认选第一个候选"
                    else:
                        chosen_reason = "无候选节点"
                elif strategy == "round_robin":
                    if candidates:
                        # 使用模块级计数器
                        rr_key = f"rr_{session_id}_{rnid}"
                        _rr_counter.setdefault(rr_key, 0)
                        idx = _rr_counter[rr_key] % len(candidates)
                        chosen_key = candidates[idx]
                        _rr_counter[rr_key] += 1
                        chosen_reason = f"Round-robin 第 {idx+1}/{len(candidates)} 个候选"
                    else:
                        chosen_reason = "无候选节点"
                elif strategy == "best_match":
                    if candidates:
                        # 简单匹配：找 artifact 中出现次数最多的候选 key
                        best_count = -1
                        best_ckey = candidates[0]
                        for ckey in candidates:
                            count = combined_artifact.lower().count(ckey.lower())
                            if count > best_count:
                                best_count = count
                                best_ckey = ckey
                        chosen_key = best_ckey
                        chosen_reason = f"Best match: '{best_ckey}' 在产物中出现 {best_count} 次"
                    else:
                        chosen_reason = "无候选节点"

                # 裁剪未选择的候选分支
                if strategy != "broadcast" and chosen_key and chosen_key != fallback_key:
                    for ckey in candidates:
                        if ckey != chosen_key and ckey in nkey_to_nid:
                            prune_nid = nkey_to_nid[ckey]
                            pruned = _compute_exclusive_downstream(prune_nid, {rnid})
                            active_nodes.difference_update(pruned)
                            for pnid in pruned:
                                pn = node_by_id.get(pnid)
                                plabel = pn.label if pn else pnid
                                await send_fn({
                                    "type": "task_status",
                                    "source": "langgraph",
                                    "timestamp": datetime.now().isoformat(),
                                    "payload": {"task_id": pnid, "status": "skipped",
                                                "error": f"路由器 [{rlabel}] 未选择此路径"},
                                })

                logger.info(
                    f"Router [{rlabel}]: strategy={strategy}, chosen={chosen_key}, "
                    f"reason={chosen_reason}"
                )
                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(rnode.id), "status": "done", "duration": 0,
                                "error": f"路由决策: {chosen_reason}" if chosen_reason else None},
                })

            # 4) Validation 节点
            for vnid in validation_nids:
                vnode = node_by_id[vnid]
                vlabel = vnode.label or vnode.node_key or str(vnid)
                vconfig = vnode.config if isinstance(vnode.config, dict) else {}
                validator = vconfig.get("validator", "llm_check")
                criteria = vconfig.get("criteria", "")
                on_fail = vconfig.get("on_fail", "retry")
                max_retries = int(vconfig.get("max_retries", 3))

                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(vnode.id), "status": "running"},
                })

                # 获取前置产物
                prev_ids = node_deps.get(vnid, [])
                combined_artifact = "\n".join(
                    artifacts.get(pid, "") for pid in prev_ids
                )

                async def _run_validator(validator_type: str, criteria_text: str,
                                         artifact_to_check: str) -> tuple[bool, str]:
                    """Returns (pass, reason)."""
                    if validator_type == "regex_match":
                        m = _re.search(criteria_text, artifact_to_check, _re.DOTALL)
                        return (m is not None,
                                "匹配成功" if m else f"未匹配到模式: {criteria_text[:80]}")

                    if validator_type == "schema_check":
                        import json as _json
                        try:
                            schema = _json.loads(criteria_text) if criteria_text else {}
                            obj = _json.loads(artifact_to_check)
                            # Simple field-level check
                            missing = [k for k in schema if k not in obj]
                            type_mismatch = [
                                f"{k}: expected {schema[k]}, got {type(obj.get(k)).__name__}"
                                for k in schema
                                if k in obj and not isinstance(obj[k], type(schema[k]))
                            ]
                            if missing or type_mismatch:
                                return (False,
                                        f"schema 不匹配: {', '.join(missing + type_mismatch)}")
                            return (True, "schema 校验通过")
                        except _json.JSONDecodeError as je:
                            return (False, f"JSON 解析失败: {je}")

                    if validator_type == "test_pass":
                        # Check if content contains test failure indicators
                        fails = ["FAILED", "FAIL:", "AssertionError", "FAILED TESTS",
                                  "FAILURES", "tests failed", "✗", "❌"]
                        has_failure = any(f.lower() in artifact_to_check.lower() for f in fails)
                        return (not has_failure,
                                "测试通过" if not has_failure else "发现测试失败")

                    # Default: llm_check
                    stmt3 = select(Agent).limit(1)
                    result3 = await db.execute(stmt3)
                    v_agent = result3.scalar_one_or_none()
                    if not v_agent:
                        return (True, "无可用 Agent 做校验，默认通过")
                    val_prompt = (
                        f"你是一位严格的质量校验员。请根据校验标准判断以下产物是否合格。\n\n"
                        f"## 校验标准\n{criteria_text}\n\n"
                        f"## 产物内容\n{artifact_to_check[:3000]}\n\n"
                        f"请先回答 PASS 或 FAIL，然后给出简短理由。\n"
                        f"如果产物明显不满足校验标准，请返回 FAIL。"
                    )
                    val_result = await agent_chat(
                        db=db, agent=v_agent, message=val_prompt,
                        return_reasoning=False, save_memory=False,
                        session_id=session_id, team_id=str(team.id),
                    )
                    val_content = (val_result.get("content") or "").strip()
                    # Strip markdown bold/italic formatting
                    clean = val_content.upper().lstrip('*_# ')
                    passed = clean.startswith("PASS") or "合格" in val_content
                    return (passed, val_content[:300])

                passed, reason = await _run_validator(validator, criteria, combined_artifact)
                retry_count = 0
                while not passed and on_fail == "retry" and retry_count < max_retries:
                    logger.warning(
                        f"Validation [{vlabel}] FAIL (attempt {retry_count+1}/{max_retries}): {reason}"
                    )
                    # 回退到前置节点重新执行
                    for pid in prev_ids:
                        if pid not in node_by_id:
                            continue
                        pnode = node_by_id[pid]
                        if pnode.type.lower() == 'agent':
                            # 保存原始 config，注入 retry feedback 后重新执行
                            saved_config = dict(pnode.config) if isinstance(pnode.config, dict) else {}
                            feedback = (
                                f"## ⚠️ 校验未通过（第 {retry_count+1} 次重试）\n"
                                f"校验标准: {criteria}\n"
                                f"失败原因: {reason}\n"
                                f"请针对性修改后重新输出。"
                            )
                            retry_config = dict(saved_config)
                            if retry_config.get("instruction"):
                                retry_config["instruction"] = (
                                    feedback + "\n\n" + retry_config["instruction"]
                                )
                            else:
                                retry_config["instruction"] = feedback
                            pnode.config = retry_config
                            await _exec_one(pid)
                            # 恢复原始 config
                            pnode.config = saved_config
                            break
                    retry_count += 1
                    # 获取更新后的产物
                    combined_artifact = "\n".join(
                        artifacts.get(pid, "") for pid in prev_ids
                    )
                    passed, reason = await _run_validator(validator, criteria, combined_artifact)

                if passed:
                    await send_fn({
                        "type": "task_status",
                        "source": "langgraph",
                        "timestamp": datetime.now().isoformat(),
                        "payload": {"task_id": str(vnode.id), "status": "done", "duration": 0,
                                    "error": f"校验通过{f'（{retry_count} 次重试后）' if retry_count else ''}"},
                    })
                    logger.info(f"Validation [{vlabel}] PASS: {reason[:100]}")
                elif on_fail == "escalate":
                    # 升级为 HITL
                    esc_msg = (
                        f"## ⚠️ 质量校验失败 — 需要人工决策\n\n"
                        f"**校验节点**: {vlabel}\n"
                        f"**校验标准**: {criteria}\n"
                        f"**失败原因**: {reason}\n"
                        f"**已重试**: {retry_count}/{max_retries}\n\n"
                        f"请审核产物并决定：批准继续 / 手动修改 / 终止流程。"
                    )
                    await send_fn({
                        "type": "request_clarification",
                        "source": "langgraph",
                        "timestamp": datetime.now().isoformat(),
                        "payload": {
                            "task_id": str(vnode.id),
                            "node_key": vnode.node_key,
                            "label": vlabel,
                            "message": esc_msg,
                            "timeout": vconfig.get("timeout", 600),
                            "mode": "langgraph_hitl",
                        },
                    })
                    # 保存恢复状态（复用 HITL 机制）
                    _paused[session_id] = {
                        "team": team,
                        "user_message": user_message,
                        "team_agents": team_agents,
                        "available_roles": available_roles,
                        "levels": levels,
                        "level_idx": level_idx,
                        "hitl_nid": vnid,
                        "hitl_node_key": vnode.node_key,
                        "hitl_label": vlabel,
                        "artifacts": dict(artifacts),
                        "node_by_id": node_by_id,
                        "node_to_agent": node_to_agent,
                        "node_deps": dict(node_deps),
                        "adj": dict(adj),
                        "ws_path": ws_path,
                        "active_nodes": set(active_nodes),
                        "pending_hitl_nids": [],
                        "from_validation": True,
                    }
                    asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
                    hitl_paused = True
                    break
                else:
                    # on_fail == "reject" or max retries exceeded
                    logger.error(f"Validation [{vlabel}] FAIL after {retry_count} retries: {reason}")
                    await send_fn({
                        "type": "task_status",
                        "source": "langgraph",
                        "timestamp": datetime.now().isoformat(),
                        "payload": {"task_id": str(vnode.id), "status": "failed",
                                    "error": f"校验失败（{retry_count}/{max_retries} 次重试后）: {reason[:200]}"},
                    })

            # 5) 处理 HITL 节点（暂停等待人工输入）
            for hnid in hitl_nids:
                hnode = node_by_id[hnid]
                hlabel = hnode.label or hnode.node_key or str(hnid)
                hconfig = hnode.config if isinstance(hnode.config, dict) else {}
                hitl_msg = hconfig.get("instruction") or hconfig.get("prompt") or f"请审核并确认节点「{hlabel}」的输出。"
                hitl_timeout = hconfig.get("timeout", 300)

                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(hnode.id), "status": "running"},
                })

                await send_fn({
                    "type": "request_clarification",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "task_id": str(hnode.id),
                        "node_key": hnode.node_key,
                        "label": hlabel,
                        "message": hitl_msg,
                        "timeout": hitl_timeout,
                        "mode": "langgraph_hitl",
                    },
                })

                # 保存恢复状态
                _paused[session_id] = {
                    "team": team,
                    "user_message": user_message,
                    "team_agents": team_agents,
                    "available_roles": available_roles,
                    "levels": levels,
                    "level_idx": level_idx,
                    "hitl_nid": hnid,
                    "hitl_node_key": hnode.node_key,
                    "hitl_label": hlabel,
                    "artifacts": dict(artifacts),
                    "node_by_id": node_by_id,
                    "node_to_agent": node_to_agent,
                    "node_deps": dict(node_deps),
                    "adj": dict(adj),
                    "ws_path": ws_path,
                    "active_nodes": set(active_nodes),
                    "nkey_to_nid": dict(nkey_to_nid),
                    "pending_hitl_nids": hitl_nids,  # remaining HITL nodes at this level
                }
                asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
                hitl_paused = True
                break  # 暂停，不继续后续层级

            if hitl_paused:
                break

        # 完成（HITL 暂停时不发送完成消息）
        if not hitl_paused:
            # 清理 round-robin 计数器，防止内存泄漏
            rr_prefix = f"rr_{session_id}_"
            for k in list(_rr_counter.keys()):
                if k.startswith(rr_prefix):
                    del _rr_counter[k]
            await send_fn({
                "type": "message_complete",
                "source": "langgraph",
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
    """从 HITL 节点恢复执行。

    user_response 为用户在 HITL 暂停时的输入。
    该输入会成为 HITL 节点的 artifact，供后续节点引用。
    """
    state = _paused.pop(session_id, None)
    if not state:
        # 尝试从数据库恢复（服务重启后内存丢失）
        state = await _load_paused_state(session_id)
    if not state:
        await send_fn({
            "type": "message_complete",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"message": "没有可恢复的 HITL 暂停状态"},
        })
        return

    from app.core.database import async_session
    from app.models.agent import Agent
    from app.services.agent_chat import agent_chat

    team = state["team"]
    levels: list[list[str]] = state["levels"]
    level_idx: int = state["level_idx"]
    hitl_nid: str = state["hitl_nid"]
    hitl_label: str = state["hitl_label"]
    artifacts: dict[str, str] = state["artifacts"]
    node_by_id: dict = state["node_by_id"]
    node_to_agent: dict = state["node_to_agent"]
    node_deps: dict = state["node_deps"]
    adj: dict = state["adj"]
    ws_path: str = state["ws_path"]
    pending_hitl_nids: list[str] = state["pending_hitl_nids"]
    user_message: str = state["user_message"]
    active_nodes: set[str] = state.get("active_nodes", set(node_by_id.keys()))
    nkey_to_nid: dict[str, str] = state.get("nkey_to_nid", {})

    async with async_session() as db:
        # 标记当前 HITL 节点为完成，用户输入作为其产物
        hitl_node = node_by_id[hitl_nid]
        user_content = user_response.get("content") if isinstance(user_response, dict) else str(user_response)
        artifacts[hitl_nid] = user_content

        await send_fn({
            "type": "task_status",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"task_id": str(hitl_node.id), "status": "done", "duration": 0},
        })

        await send_fn({
            "type": "agent_message",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "agent": "人工审核",
                "content": user_content,
                "type": "message",
                "model": None,
                "latency": 0,
                "task_id": str(hitl_node.id),
                "node_key": hitl_node.node_key or hitl_nid,
            },
        })

        # 继续处理当前层级的剩余 HITL 节点
        remaining_hitl = [n for n in pending_hitl_nids if n != hitl_nid]
        for hnid in remaining_hitl:
            hnode = node_by_id[hnid]
            hlabel = hnode.label or hnode.node_key or str(hnid)
            hconfig = hnode.config if isinstance(hnode.config, dict) else {}
            hitl_msg = hconfig.get("instruction") or hconfig.get("prompt") or f"请审核并确认节点「{hlabel}」的输出。"
            hitl_timeout = hconfig.get("timeout", 300)

            await send_fn({
                "type": "task_status",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {"task_id": str(hnode.id), "status": "running"},
            })
            await send_fn({
                "type": "request_clarification",
                "source": "langgraph",
                "timestamp": datetime.now().isoformat(),
                "payload": {
                    "task_id": str(hnode.id),
                    "node_key": hnode.node_key,
                    "label": hlabel,
                    "message": hitl_msg,
                    "timeout": hitl_timeout,
                    "mode": "langgraph_hitl",
                },
            })

            # 保存新的暂停状态
            _paused[session_id] = {
                **state,
                "level_idx": level_idx,
                "hitl_nid": hnid,
                "hitl_node_key": hnode.node_key,
                "hitl_label": hlabel,
                "artifacts": dict(artifacts),
                "pending_hitl_nids": remaining_hitl,
            }
            asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
            return  # 再次暂停等待用户

        # 当前层级全部完成，继续后续层级
        async def _exec_one_resume(nid: str) -> None:
            """Thin wrapper around shared _execute_agent_node for resume context."""
            node = node_by_id[nid]
            node_key = node.node_key or str(node.id)
            label = node.label or node_key

            agent_id = node_to_agent.get(node_key)
            if not agent_id:
                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(node.id), "status": "failed", "error": "未绑定 Agent"},
                })
                return
            agent = await db.get(Agent, agent_id)
            if not agent:
                return

            await _execute_agent_node(
                nid=nid, node=node, agent=agent, db=db,
                artifacts=artifacts, node_deps=node_deps,
                node_key=node_key, label=label,
                user_message=user_message,
                session_id=session_id, team_id=str(team.id),
                send_fn=send_fn, ws_path=ws_path,
                harness=harness,
                # resume 不传递 timeout_edge/fallback_edge，超时/失败直接标记
            )

        # 继续执行后续层级

        async def _eval_condition_resume(expression: str, artifact_text: str, node_label: str) -> bool:
            """Same as _eval_condition, using shared _eval_condition_fast."""
            fast = _eval_condition_fast(expression, artifact_text)
            if fast is not None:
                return fast
            expr = expression.strip()
            criteria = expr[len("llm_judge:"):].strip() if expr.startswith("llm_judge:") else expr
            try:
                stmt_j = select(Agent).limit(1)
                result_j = await db.execute(stmt_j)
                j_agent = result_j.scalar_one_or_none()
                if not j_agent:
                    return True
                jp = (f"你是一个条件判断器。请根据以下条件判断前置产物的内容是否符合。\n\n"
                      f"## 判断条件\n{criteria}\n\n## 前置产物内容\n{artifact_text[:2000]}\n\n请只回答 YES 或 NO。")
                jr = await agent_chat(
                    db=db, agent=j_agent, message=jp,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=str(team.id),
                )
                return (jr.get("content") or "").strip().upper().lstrip('*_# ').startswith("YES")
            except Exception:
                return True

        for li in range(level_idx + 1, len(levels)):
            lvl = levels[li]
            agent_nids = [nid for nid in lvl
                          if node_by_id[nid].type.lower() == 'agent'
                          and nid in active_nodes]
            condition_nids = [nid for nid in lvl
                              if node_by_id[nid].type.lower() == 'condition'
                              and nid in active_nodes]
            router_nids = [nid for nid in lvl
                           if node_by_id[nid].type.lower() == 'router'
                           and nid in active_nodes]
            hitl_nids = [nid for nid in lvl
                         if node_by_id[nid].type.lower() == 'hitl']

            # Agent 节点
            if agent_nids:
                if len(agent_nids) == 1:
                    await _exec_one_resume(agent_nids[0])
                else:
                    await asyncio.gather(*[_exec_one_resume(nid) for nid in agent_nids])

            # Condition 节点
            for cnid in condition_nids:
                cnode = node_by_id[cnid]
                cconfig = cnode.config if isinstance(cnode.config, dict) else {}
                expression = cconfig.get("expression", "")
                on_true_key = cconfig.get("on_true_node_key", "")
                on_false_key = cconfig.get("on_false_node_key", "")
                prev_ids = node_deps.get(cnid, [])
                combined = "\n".join(artifacts.get(pid, "") for pid in prev_ids)
                cond_result = await _eval_condition_resume(expression, combined, cnode.label or cnid)
                unchosen_key = on_false_key if cond_result else on_true_key
                if unchosen_key and unchosen_key in nkey_to_nid:
                    prune_nid = nkey_to_nid[unchosen_key]
                    # Simple prune: just remove the target node
                    active_nodes.discard(prune_nid)
                    await send_fn({
                        "type": "task_status", "source": "langgraph",
                        "timestamp": datetime.now().isoformat(),
                        "payload": {"task_id": prune_nid, "status": "skipped",
                                    "error": f"条件节点未选择此路径"},
                    })
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(cnode.id), "status": "done", "duration": 0},
                })

            # Router 节点
            for rnid in router_nids:
                rnode = node_by_id[rnid]
                rconfig = rnode.config if isinstance(rnode.config, dict) else {}
                candidates: list = rconfig.get("candidates", [])
                chosen_key = candidates[0] if candidates else ""
                for ckey in candidates:
                    if ckey != chosen_key and ckey in nkey_to_nid:
                        active_nodes.discard(nkey_to_nid[ckey])
                        await send_fn({
                            "type": "task_status", "source": "langgraph",
                            "timestamp": datetime.now().isoformat(),
                            "payload": {"task_id": nkey_to_nid[ckey], "status": "skipped",
                                        "error": "路由器恢复执行时默认选第一个候选"},
                        })
                await send_fn({
                    "type": "task_status", "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(rnode.id), "status": "done", "duration": 0},
                })

            # HITL 节点
            for hnid in hitl_nids:
                hnode = node_by_id[hnid]
                hlabel = hnode.label or hnode.node_key or str(hnid)
                hconfig = hnode.config if isinstance(hnode.config, dict) else {}
                hitl_msg = hconfig.get("instruction") or hconfig.get("prompt") or f"请审核并确认节点「{hlabel}」的输出。"
                hitl_timeout = hconfig.get("timeout", 300)

                await send_fn({
                    "type": "task_status",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {"task_id": str(hnode.id), "status": "running"},
                })
                await send_fn({
                    "type": "request_clarification",
                    "source": "langgraph",
                    "timestamp": datetime.now().isoformat(),
                    "payload": {
                        "task_id": str(hnode.id),
                        "node_key": hnode.node_key,
                        "label": hlabel,
                        "message": hitl_msg,
                        "timeout": hitl_timeout,
                        "mode": "langgraph_hitl",
                    },
                })

                _paused[session_id] = {
                    **state,
                    "levels": levels,
                    "level_idx": li,
                    "hitl_nid": hnid,
                    "hitl_node_key": hnode.node_key,
                    "hitl_label": hlabel,
                    "artifacts": dict(artifacts),
                    "active_nodes": set(active_nodes),
                    "nkey_to_nid": dict(nkey_to_nid),
                    "pending_hitl_nids": hitl_nids,
                }
                asyncio.create_task(_persist_paused_state(session_id, _paused[session_id]))
                return  # 再次暂停

        # 全部完成
        # 清理残留状态和 round-robin 计数器
        _paused.pop(session_id, None)
        rr_prefix = f"rr_{session_id}_"
        for k in list(_rr_counter.keys()):
            if k.startswith(rr_prefix):
                del _rr_counter[k]
        await send_fn({
            "type": "message_complete",
            "source": "langgraph",
            "timestamp": datetime.now().isoformat(),
            "payload": {"message": f"流程执行完成（{len(levels)} 层级）"},
        })
