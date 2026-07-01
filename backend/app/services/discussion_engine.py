"""Discussion Engine：自由讨论模式的多 Agent 轮流响应引擎

职责：
1. 在 session 上下文中处理用户消息（无需 SOP 约束）
2. 根据 team.collaboration_mode 选择调度策略（supervisor / swarm / round_robin / direct）
3. 捕获并广播推理中间步骤（路由决策、工具调用、上下文注入）
4. 保存对话记忆 + 更新 session 消息计数
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession as DBAsyncSession

from app.services.mailbox_service import mailbox_service, MailboxMessageType
from app.services.trace_context import TraceContext

logger = logging.getLogger(__name__)


class DiscussionEventType(str, Enum):
    """讨论模式事件类型"""
    THINKING = "thinking_update"       # Agent 思考步骤
    REASONING = "reasoning_complete"   # Agent 推理完成
    AGENT_MESSAGE = "agent_message"    # Agent 回复内容
    MESSAGE_COMPLETE = "message_complete"  # 消息处理完成
    STREAM_TOKEN = "stream_token"      # 流式 token（thinking 或 content）
    AGENT_STATUS = "agent_status"      # Agent 状态灯事件
    AGENT_TO_AGENT = "agent_to_agent"  # Agent 间 Mailbox 消息
    STORAGE = "storage_update"         # 记忆存储完成（含 memory_id）
    TASK_CREATED = "task_created"      # 任务创建
    TASK_UPDATED = "task_updated"      # 任务状态更新


@dataclass
class DiscussionEvent:
    """讨论模式事件"""
    type: DiscussionEventType
    source: str  # agent_id or "system"
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DiscussionEngine:
    """自由讨论模式引擎"""

    def __init__(self, db: DBAsyncSession):
        self.db = db

    async def process_message(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team_id: uuid.UUID,
        history: Optional[list[dict]] = None,
        mentioned_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """处理用户消息，yield 事件流

        流程：
        1. 获取团队 + 确定调度策略
        2. Supervisor 选择响应的 Agent（supervisor 模式）或直接响应（swarm）
        3. Agent 执行 agent_chat（带推理捕获）
        4. (可选) Supervisor 审核
        5. 保存记忆 + 更新计数
        """
        # 创建 root trace，覆盖整个 session 生命周期
        session_id_str = str(session_id)
        with TraceContext.create_trace(
            name="discussion",
            session_id=session_id_str,
            metadata={"team_id": str(team_id)},
        ):
            async for event in self._process_message_events(
                session_id=session_id,
                user_message=user_message,
                team_id=team_id,
                history=history,
                mentioned_agents=mentioned_agents,
            ):
                yield event

    async def _process_message_events(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team_id: uuid.UUID,
        history: Optional[list[dict]] = None,
        mentioned_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """Inner generator — trace context already set up by process_message."""
        from app.models.team import Team
        from app.models.agent import Agent
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager, SessionManager

        # 0. 确保团队所有 Agent 已注册到 Pool
        from app.services.agent_pool import agent_pool
        await agent_pool.register_team_agents(self.db, team_id)

        # 1. 获取团队信息
        team = await self.db.get(Team, team_id)
        if not team:
            yield self._error("找不到团队")
            return

        team_mode = team.collaboration_mode or "supervisor"

        # 2. 选择执行策略（每个模式用 span 包裹，自动挂到 root trace）
        if team_mode == "swarm":
            async for event in self._execute_swarm_mode(
                session_id=session_id,
                user_message=user_message,
                team=team,
                history=history,
                mentioned_agents=mentioned_agents,
            ):
                yield event
        elif team_mode == "round_robin":
            # RoundRobin 模式：轮流发言 → 达成共识
            async for event in self._execute_round_robin_mode(
                session_id=session_id,
                user_message=user_message,
                team=team,
                history=history,
            ):
                yield event
        elif team_mode == "supervisor":
            async for event in self._execute_supervisor_mode(
                session_id=session_id,
                user_message=user_message,
                team=team,
                history=history,
            ):
                yield event
        else:
            async for event in self._execute_direct_mode(
                session_id=session_id,
                user_message=user_message,
                team=team,
                history=history,
            ):
                yield event

        # 3. 保存记忆 + 更新 session 计数（在子函数中分别处理）

    # ── Supervisor 模式：三阶段 ──

    async def _execute_supervisor_mode(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team,
        history: Optional[list[dict]],
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """Supervisor 模式：调度 → 执行 → 审核"""
        from app.models.agent import Agent
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager
        from app.services.agent_pool import agent_pool

        # 获取 supervisor：优先 team.leader_id，否则自动选第一个成员
        supervisor = None
        if team.leader_id:
            supervisor = await self.db.get(Agent, team.leader_id)
        if not supervisor:
            # 自动选取第一个团队成员作为 supervisor
            members = await self._get_all_workers(team)
            if members:
                supervisor = members[0][0]  # (agent, meta)
                logger.info(f"Auto-selected supervisor: {supervisor.name}")
        if not supervisor:
            yield self._error("团队没有可用成员作为 supervisor")
            return

        # 构建团队花名册
        team_roster = await self._build_team_roster(team)

        yield self._agent_status(
            str(supervisor.id), supervisor.name, "thinking",
            f"{supervisor.name} 正在分析消息..."
        )
        yield self._thinking(
            source=str(supervisor.id),
            step="supervisor_analysis",
            detail=f"{supervisor.name} (主管) 正在分析消息并指派成员...",
            agent_name=supervisor.name,
        )

        # 阶段 1: Supervisor 调度 — 选择哪个 Worker + 给出指导
        # 构建详细的成员描述
        role_descriptions = {
            "pm": "产品经理（PM）：需求分析、文档编写、产品规划",
            "dev": "开发工程师：代码实现、技术方案、开发任务",
            "qa": "测试工程师：质量保证、测试用例、bug 验证",
            "designer": "设计师：UI/UX 设计、视觉设计、交互设计",
            "lead": "技术主管：架构设计、技术决策、代码审查",
        }
        roster_text = "\n".join(
            f"- {r['icon']} {r['name']} (角色: {r['role']}) - {role_descriptions.get(r['role'], '通用成员')}"
            for r in team_roster
        )

        # 构建可选的 worker 角色列表
        available_roles = [r["role"] for r in team_roster]
        roles_list = ", ".join(available_roles)
        dispatch_prompt = (
            f"你是团队主管，负责协调 AI Agent 团队协作。\n\n"
            f"## 你的团队\n"
            f"团队名称: {team.name}\n"
            f"可选成员及角色:\n{roster_text}\n"
            f"可用角色代码: [{roles_list}]\n\n"
            f"## 用户消息\n{user_message}\n\n"
            f"## 任务\n"
            f"分析用户意图，从 [{roles_list}] 中选择最合适的人选。\n"
            f"多个成员可选多个。开放性问题选 [\"ALL\"]。\n"
            f"注意：你不回复用户，只负责派发任务。\n\n"
            f"回复格式（JSON）：\n"
            f'{{"workers": ["角色码"], "guidance": "执行指导", "reason": "选择原因"}}'
        )

        sv_id = str(supervisor.id)
        await agent_pool.acquire_with_retry(
            agent_id=sv_id, role_slot="pm",
            task_id=str(session_id), max_retries=2, interval=1.0,
        )
        try:
            session_mgr = get_session_manager(self.db)
            agent_session = await session_mgr.get_or_create_session(
                team_id=str(team.id),
                agent_id=sv_id,
                task_id=str(session_id),
            )

            t0 = time.time()
            dispatch_result = await agent_chat(
                db=self.db,
                agent=supervisor,
                message=dispatch_prompt,
                team_id=str(team.id),
                session_id=str(session_id),
                return_reasoning=True,
                save_memory=False,  # 主管调度内部消息，不保存到聊天历史
            )
            dispatch_elapsed = time.time() - t0

            # 解析 supervisor 的选择
            dispatch_content = dispatch_result.get("content", "")
            selected_roles = self._parse_workers(dispatch_content)

            yield self._reasoning(
                source=sv_id,
                agent_name=supervisor.name,
                reasoning={
                    **(dispatch_result.get("reasoning", {})),
                    "supervisor_analysis": (
                        f"主管分析了用户消息并决定指派。\n"
                        f"指派给: {', '.join(selected_roles or ['所有成员'])}\n"
                        f"调度内容: {dispatch_content[:400]}"
                    ),
                    "latency": round(dispatch_elapsed, 2),
                },
            )

            yield self._thinking(
                source=sv_id,
                step="supervisor_dispatch",
                detail=(
                    f"📋 调度结果: {', '.join(selected_roles or ['所有成员'])}\n"
                    f"📝 指导: {dispatch_content[:200]}"
                ),
                result=dispatch_content[:500],
                agent_name=supervisor.name,
            )

            try:
                await session_mgr.close_session(agent_session.session_id)
            except Exception:
                pass
        finally:
            await agent_pool.release(sv_id)

        # 阶段 2: 获取所有需要响应的 Worker（由 Supervisor 语义判断）
        workers_to_call = await self._select_workers(team, selected_roles, dispatch_content)
        if not workers_to_call:
            workers_to_call = [supervisor]  # fallback

        # 为每个被选中的 Agent 显示独立的 thinking 事件
        for worker in workers_to_call:
            role_display = "主管" if worker.name == supervisor.name else "成员"
            guidance_summary = (dispatch_content[:100] + "...") if len(dispatch_content) > 100 else dispatch_content
            yield self._agent_status(
                str(worker.id), worker.name, "thinking",
                f"{worker.name} ({role_display}) 正在分析..."
            )
            yield self._thinking(
                source=str(worker.id),
                step="worker_thinking",
                detail=f"{worker.name} ({role_display}) 正在分析需求并思考...",
                result=guidance_summary,
                agent_name=worker.name,
            )

        # 阶段 2.5: 从 dispatch 指导中自动执行文件操作
        from app.services.session_task_service import SessionTaskService
        from app.tools.file_ops import FileOpsTool
        task_service = SessionTaskService(self.db)
        created_tasks = []
        role_desc_map = {"pm": "需求分析与文档", "dev": "代码实现", "qa": "测试验证", "designer": "UI/UX 设计", "lead": "架构设计"}

        # 从 supervisor 的 dispatch 内容中提取文件操作指令并直接执行
        _dispatch_text = dispatch_content[:1000]
        file_ops_tool = FileOpsTool()
        if "file-ops" in _dispatch_text.lower() or "创建" in _dispatch_text or "写入" in _dispatch_text or "write" in _dispatch_text.lower():
            import re as _re
            # 提取文件名（仅匹配合法文件名，不包含空格、中文、标点）
            path_match = _re.search(r"([a-zA-Z_][\w.-]{0,60}\.(?:py|txt|md|json|yml|yaml|js|ts|html|css|sh|cfg|ini|toml|env))", _dispatch_text)
            if path_match:
                file_path = path_match.group(1)
                if _re.search(r'[一-鿿\s]', file_path):
                    file_path = file_path.split()[0]
                file_content = ""
                code_match = _re.search(r"内容为[：:]\s*(.+?)(?:。|$)", _dispatch_text)
                if code_match:
                    file_content = code_match.group(1).replace("。", "").replace("，", "").strip()
                if not file_content:
                    file_content = f"# File created by agent\n# Request: {user_message[:100]}"
                try:
                    result = await file_ops_tool.execute(
                        {"operation": "write", "path": file_path, "content": file_content},
                        session_id=str(session_id),
                    )
                    if result.success:
                        logger.info(f"📁 自动创建文件: {file_path} ({len(file_content)} chars)")
                    else:
                        logger.warning(f"📁 自动创建文件失败: {file_path} - {result.error}")
                except Exception as fe:
                    logger.warning(f"📁 自动创建文件异常: {file_path} - {fe}")

        default_role = selected_roles[0] if selected_roles else "dev"
        for i, worker in enumerate(workers_to_call):
            role = selected_roles[i] if i < len(selected_roles) else default_role
            task_title = f"[{role}] {role_desc_map.get(role, '任务')}: {user_message[:60]}"
            task = await task_service.create_task(
                session_id=session_id,
                title=task_title,
                description=f"用户请求: {user_message[:200]}",
                priority="medium",
                assigned_agent_id=worker.id,
                assigned_agent_name=worker.name,
                expected_output=dispatch_content[:300] if dispatch_content else None,
            )
            created_tasks.append(task)
            yield self._event(DiscussionEventType.TASK_CREATED, source="system", payload={
                "task": task_service.task_to_dict(task),
                "seq": i + 1,
                "total": len(workers_to_call),
            })

        # 阶段 3: 执行 — DynamicExecutor（有依赖时）或串行（无依赖时）
        has_dependencies = any(
            task.depends_on and len(task.depends_on) > 0
            for task in created_tasks
        ) if created_tasks else False

        if has_dependencies and len(workers_to_call) > 1:
            # 使用 DynamicExecutor 并行执行有依赖关系的任务
            from app.services.dynamic_executor import DynamicExecutor, ExecutorEventType
            executor = DynamicExecutor(max_parallel=min(3, len(workers_to_call)))
            async for exec_event in executor.execute_plan(
                plan_tasks=created_tasks,
                team_id=team.id,
                session_id=session_id,
                user_message=user_message,
                db=self.db,
                task_service=task_service,
            ):
                # 将 ExecutorEvent 转换为 DiscussionEvent
                if exec_event.type == ExecutorEventType.PLAN_CREATED:
                    yield self._event(DiscussionEventType.TASK_CREATED, source="system", payload={
                        "plan": exec_event.payload, "is_dag": True,
                    })
                elif exec_event.type == ExecutorEventType.TASK_STARTED:
                    wid = exec_event.payload.get("task_id", "")
                    agent_name = exec_event.payload.get("agent_name", "Agent")
                    yield self._agent_status(wid, agent_name, "working", f"执行: {exec_event.payload.get('title', '')}")
                elif exec_event.type == ExecutorEventType.TASK_COMPLETED:
                    wid = exec_event.payload.get("task_id", "")
                    yield self._event(DiscussionEventType.TASK_UPDATED, source=wid, payload={
                        "task_id": wid, "status": "done",
                        "title": exec_event.payload.get("title", ""),
                    })
                elif exec_event.type == ExecutorEventType.TASK_FAILED:
                    wid = exec_event.payload.get("task_id", "")
                    yield self._event(DiscussionEventType.AGENT_MESSAGE, source=wid, payload={
                        "agent": "⚠️ 错误", "content": f"任务失败: {exec_event.payload.get('error', '')}",
                        "type": "progress",
                    })
                elif exec_event.type == ExecutorEventType.PROGRESS:
                    done = exec_event.payload.get("done", 0)
                    total = exec_event.payload.get("total", 0)
                    if total > 0:
                        yield self._event(DiscussionEventType.AGENT_MESSAGE, source="system", payload={
                            "agent": "📊 进度", "content": f"📊 进度: {done}/{total} 任务完成",
                            "type": "progress",
                        })
                elif exec_event.type == ExecutorEventType.PLAN_COMPLETE:
                    pass  # message_complete will be sent after

        else:
            # 原有串行执行逻辑（无依赖或单 worker）
            async for event in self._execute_workers_sequential(
                session_id=session_id, user_message=user_message, team=team,
                workers_to_call=workers_to_call, dispatch_content=dispatch_content,
                selected_roles=selected_roles, default_role=default_role,
                created_tasks=created_tasks, task_service=task_service,
            ):
                yield event

        yield self._event(DiscussionEventType.MESSAGE_COMPLETE, source="system")

    # ── 串行 Worker 执行（保留原逻辑，供 DynamicExecutor fallback 使用）──

    async def _execute_workers_sequential(
        self,
        session_id, user_message, team, workers_to_call,
        dispatch_content, selected_roles, default_role,
        created_tasks, task_service,
    ):
        """串行执行 worker 列表（原有逻辑）"""
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager
        from app.services.agent_pool import agent_pool
        session_mgr = get_session_manager(self.db)

        for i, worker in enumerate(workers_to_call):
            role_slot = default_role
            wid = str(worker.id)
            mailbox_context = mailbox_service.format_for_agent_context(str(session_id), wid)
            from app.services.session_service import SessionService
            svc = SessionService(self.db)
            ws_info = await svc.get_workspace_info(session_id)
            workspace_path = ws_info["path"] if ws_info else "未知"
            prompt = (
                f"## 工作空间\n当前工作目录: {workspace_path}\n"
                f"## 执行指导\n{dispatch_content[:500]}\n\n"
                f"## 用户消息\n{user_message}\n\n"
                f"{mailbox_context}\n"
                f"请根据上述指导完成你的工作。回复要简洁、直接。"
            )

            await agent_pool.acquire_with_retry(
                agent_id=wid, role_slot=role_slot,
                task_id=str(session_id), max_retries=2, interval=1.0,
            )
            full_content, full_thinking = "", ""
            t1 = time.time()
            yield self._agent_status(wid, worker.name, "working", f"{worker.name} 正在生成回复...")
            try:
                w_s = await session_mgr.get_or_create_session(
                    team_id=str(team.id), agent_id=wid, task_id=str(session_id),
                )
                try:
                    from app.services.collaboration.agent_executor import agent_executor as _exec2
                    result = await _exec2.execute(
                        prompt=prompt, agent=worker, db=self.db,
                        session_id=str(session_id), team_id=str(team.id),
                        node_key="supervisor_worker",
                    )
                    full_content = result.get("content", "")
                    reasoning = result.get("reasoning", {})
                    full_thinking = reasoning.get("thinking_steps", "") or ""
                    if full_thinking:
                        for chunk in [full_thinking[i:i+20] for i in range(0, len(full_thinking), 20)]:
                            yield self._event(DiscussionEventType.STREAM_TOKEN, source=wid,
                                payload={"agent": worker.name, "token_type": "thinking_token", "token": chunk})
                    if full_content:
                        preview = full_content[:80] + ("..." if len(full_content) > 80 else "")
                        yield self._event(DiscussionEventType.STREAM_TOKEN, source=wid,
                            payload={"agent": worker.name, "token_type": "content_token", "token": preview})
                except Exception as e:
                    logger.warning(f"Worker {worker.name} failed: {e}")
                    full_content = f"抱歉，处理请求时出错: {str(e)}"
                    full_thinking = ""
                finally:
                    try: await session_mgr.close_session(w_s.session_id)
                    except Exception: pass
            finally:
                await agent_pool.release(wid)

            elapsed = time.time() - t1
            yield self._agent_status(wid, worker.name, "done", f"{worker.name} 完成 · {elapsed:.1f}s")
            # 合并 agent_chat 原始 reasoning + supervisor 附加字段
            original_decision = reasoning.get("decision_summary", "")
            reasoning_data = {
                "agent": worker.name,
                "thinking_steps": full_thinking,
                # 保留 agent_chat 的原始 decision_summary（工具调用、记忆参考等），附加耗时
                "decision_summary": (
                    f"{original_decision} · 耗时 {elapsed:.1f}s"
                    if original_decision and original_decision != "直接回复"
                    else f"{worker.name} 完成回复 · 耗时 {elapsed:.1f}s"
                ),
                # 透传 agent_chat 的模型路由信息
                "model_routing": reasoning.get("model_routing", {}),
                # 透传工具调用详情
                "tool_calls": reasoning.get("tool_calls", []),
                # 透传上下文使用统计
                "context_used": reasoning.get("context_used", {}),
                "prompt_length": reasoning.get("prompt_length"),
                "input_content": reasoning.get("input_content"),
                # Supervisor 分析 — 包含完整指派过程和原因
                "supervisor_analysis": (
                    f"主管指派给: {', '.join(selected_roles or ['成员'])}\n"
                    f"选择原因: {dispatch_content[:300]}"
                ),
                # 主管的执行指导（完整内容）
                "dispatch_guidance": dispatch_content[:500] if dispatch_content else "",
                # 耗时
                "latency": round(elapsed, 2),
            }
            yield self._reasoning(source=wid, agent_name=worker.name, reasoning=reasoning_data)
            yield self._agent_message(source=wid, agent_name=worker.name, content=full_content, model="", latency=round(elapsed, 2))

            memory = await self._save_message(
                session_id=session_id, team_id=team.id, user_message=user_message,
                assistant_message=full_content, agent_id=uuid.UUID(wid), agent_name=worker.name,
                reasoning=reasoning_data,
            )
            if memory:
                yield self._event(DiscussionEventType.STORAGE, source=wid, payload={
                    "agent": worker.name, "memory_id": str(memory.id),
                    "memory_level": "context", "session_id": str(session_id),
                })
            # 进度更新
            if created_tasks and i < len(created_tasks):
                task_to_complete = created_tasks[i]
                await task_service.update_task(task_id=task_to_complete.id, status="done", actual_output=full_content[:500])
                stats = await task_service.get_stats(session_id)
                yield self._event(DiscussionEventType.TASK_UPDATED, source=wid, payload={
                    "task_id": str(task_to_complete.id), "status": "done", "assigned_agent_name": worker.name, "stats": stats,
                })
                progress_text = f"✅ 任务 {stats['done']}/{stats['total']} 完成: **{task_to_complete.title}**"
                if stats['done'] == stats['total']:
                    progress_text = f"🎉 所有任务已完成！({stats['total']}/{stats['total']})"
                yield self._event(DiscussionEventType.AGENT_MESSAGE, source=wid, payload={
                    "agent": "📊 进度", "content": progress_text, "model": "", "latency": 0, "type": "progress",
                })

    # ── Swarm 模式：所有成员自主回复 ──

    async def _execute_swarm_mode(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team,
        history: Optional[list[dict]],
        mentioned_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """Swarm 模式：所有团队成员自主决定是否回复，无需 Supervisor 指派

        如果 mentioned_agents 包含 "__all__" 或消息中有 @all，则通知所有成员
        如果 mentioned_agents 包含具体成员，则只通知被 @ 的成员
        否则所有成员自主判断是否回复
        """
        from app.models.agent import Agent
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager
        from app.services.agent_pool import agent_pool

        # 获取所有团队成员
        all_workers = await self._get_all_workers(team)
        if not all_workers:
            yield self._error("团队没有可用成员")
            return

        # 判断通知哪些成员
        workers_to_notify = all_workers
        is_mention_all = mentioned_agents and len(mentioned_agents) == 1 and mentioned_agents[0] == "__all__"

        if is_mention_all:
            yield self._thinking(
                source="system", step="swarm_notify",
                detail=f"📢 @all：通知所有 {len(all_workers)} 个成员回复...",
            )
        elif mentioned_agents and len(mentioned_agents) > 0:
            workers_to_notify = [
                (agent, meta) for agent, meta in all_workers
                if str(agent.id) in mentioned_agents
            ]
            if not workers_to_notify:
                yield self._thinking(
                    source="system", step="swarm_notify",
                    detail=f"⚠️ @ 的成员不在当前团队中",
                )
                return
            yield self._thinking(
                source="system", step="swarm_notify",
                detail=f"@ {len(workers_to_notify)} 个成员，正在等待回复...",
            )
        else:
            yield self._thinking(
                source="system", agent_name="📢 通知",
                step="swarm_thinking",
                detail=f"通知 {len(all_workers)} 个团队成员，等待他们分析并回复...",
            )

        workers = workers_to_notify

        # 为所有 worker 发送 thinking 状态
        for worker, meta in workers:
            yield self._agent_status(str(worker.id), worker.name, "thinking",
                                     f"{worker.name} 正在分析...")

        # 并行让所有 agent 回复
        import asyncio

        async def swarm_reply(worker, role_slot: str) -> dict | None:
            wid = str(worker.id)

            if is_mention_all:
                prompt = (
                    f"你是「{team.name}」团队的 {worker.name}（角色: {role_slot}）。\n"
                    f"用户使用了 @all，要求所有成员必须回复。\n\n"
                    f"## 用户消息\n{user_message}\n\n"
                    f"请必须回复这条消息。"
                )
            else:
                prompt = (
                    f"你是「{team.name}」团队的 {worker.name}（角色: {role_slot}）。\n"
                    f"团队其他成员也会看到这条消息并各自回复。\n\n"
                    f"## 用户消息\n{user_message}\n\n"
                    f"如果与你的角色相关 → 说明你准备做什么，回复开头用「[TASK] 具体任务描述」。\n"
                    f"如果不相关 → 回复「[SKIP] 不相关」并说明原因。"
                )
            acquired = await agent_pool.acquire_with_retry(
                agent_id=wid, role_slot=role_slot,
                task_id=str(session_id), max_retries=2, interval=1.0,
            )
            if not acquired:
                return {"agent_name": worker.name, "content": "[SKIP] Agent繁忙，跳过",
                        "reasoning": {}, "latency": 0, "agent_id": wid}
            try:
                session_mgr = get_session_manager(self.db)
                w_s = await session_mgr.get_or_create_session(
                    team_id=str(team.id), agent_id=wid, task_id=str(session_id),
                )
                t0 = time.time()
                from app.services.collaboration.agent_executor import agent_executor as _exec
                result = await _exec.execute(
                    prompt=prompt, agent=worker, db=self.db,
                    session_id=str(session_id), team_id=str(team.id),
                    node_key="swarm_agent",
                )
                elapsed = time.time() - t0
                try:
                    await session_mgr.close_session(w_s.session_id)
                except Exception:
                    pass
                return {
                    "agent_name": worker.name,
                    "content": result.get("content", ""),
                    "reasoning": result.get("reasoning", {}),
                    "latency": round(elapsed, 2),
                    "agent_id": wid,
                    "exec_mode": result.get("exec_mode", "single_pass"),
                    "iterations": result.get("iterations", 1),
                }
            finally:
                await agent_pool.release(wid)

        tasks = [swarm_reply(w, m.get("role_slot", "dev")) for w, m in workers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        replied_count = 0
        skipped_count = 0
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Swarm worker failed: {r}")
                continue
            if not r:
                continue
            content = r["content"]
            reasoning = r.get("reasoning", {})

            # Always emit agent status done
            yield self._agent_status(r["agent_id"], r["agent_name"], "done",
                                     f"{r['agent_name']} 完成 · {r.get('latency', 0):.1f}s")

            if "[SKIP]" in content:
                skipped_count += 1
                yield self._reasoning(source=r["agent_id"], agent_name=r["agent_name"], reasoning=reasoning)
                yield self._thinking(
                    source=r["agent_id"], step="agent_skipped",
                    detail=f"{r['agent_name']} 跳过: {content.replace('[SKIP]', '').strip() or '不相关'}",
                    agent_name=r["agent_name"],
                )
                continue

            replied_count += 1
            yield self._reasoning(source=r["agent_id"], agent_name=r["agent_name"], reasoning=reasoning)
            yield self._agent_message(
                source=r["agent_id"], agent_name=r["agent_name"], content=content,
                model="", latency=r["latency"], questions=r.get("questions", []),
            )
            memory = await self._save_message(
                session_id=session_id, team_id=team.id,
                user_message=user_message, assistant_message=content,
                agent_id=uuid.UUID(r["agent_id"]),
                agent_name=r["agent_name"],
                reasoning=reasoning,
            )
            if memory:
                yield self._event(DiscussionEventType.STORAGE, source=r["agent_id"], payload={
                    "agent": r["agent_name"],
                    "memory_id": str(memory.id),
                    "memory_level": "context",
                    "session_id": str(session_id),
                })

        # 自动从回复中提取 [TASK] 创建任务
        import re as _re2
        task_count = 0
        for r in results:
            if isinstance(r, Exception) or not r: continue
            content = r.get("content", "")
            task_matches = _re2.findall(r'\[TASK\]\s*(.+?)(?:\n|$)', content)
            for task_desc in task_matches:
                try:
                    from app.services.session_task_service import SessionTaskService
                    tsvc = SessionTaskService(self.db)
                    await tsvc.create_task(
                        session_id=session_id,
                        title=task_desc.strip()[:200],
                        description=f"用户请求: {user_message[:200]}",
                        assigned_agent_id=uuid.UUID(r["agent_id"]),
                        assigned_agent_name=r["agent_name"],
                    )
                    task_count += 1
                    yield self._event(DiscussionEventType.TASK_CREATED, source="system", payload={
                        "task": {"id": str(uuid.uuid4()), "title": task_desc.strip()[:200],
                                 "status": "claimed", "assigned_agent_name": r["agent_name"]},
                        "seq": task_count, "total": task_count,
                    })
                except Exception as e:
                    logger.warning(f"Swarm task creation failed: {e}")

        # 显示实际回复数量
        total_msg = f"✅ 完成：{replied_count} 个成员回复，{skipped_count} 个跳过"
        if task_count > 0:
            total_msg += f"，{task_count} 个任务已创建"
        yield self._thinking(
            source="system",
            step="swarm_complete",
            detail=total_msg,
        )

        yield self._event(DiscussionEventType.MESSAGE_COMPLETE, source="system")

    # ── RoundRobin 模式：轮流发言 → 达成共识 ──

    async def _execute_round_robin_mode(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team,
        history: Optional[list[dict]],
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """RoundRobin 模式：所有成员按顺序轮流发言

        适用于: 代码审查、方案评审、头脑风暴后达成共识
        流程:
        1. 获取所有团队成员
        2. 每个成员按固定顺序发言（看到前面的发言 + 用户消息）
        3. 最后一个成员做总结
        """
        from app.models.agent import Agent
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager
        from app.services.agent_pool import agent_pool
        import asyncio

        all_workers = await self._get_all_workers(team)
        if not all_workers:
            yield self._error("团队没有可用成员")
            return

        workers = all_workers
        session_mgr = get_session_manager(self.db)

        yield self._thinking(
            source="system",
            step="round_robin_start",
            detail=f"🔄 轮流发言模式：{len(workers)} 个成员按顺序发言",
        )

        all_responses = []  # 累积所有发言

        for idx, (worker, meta) in enumerate(workers):
            wid = str(worker.id)
            role_slot = meta.get("role_slot", "成员")

            yield self._agent_status(
                wid, worker.name, "thinking",
                f"{worker.name} 准备发言 ({idx + 1}/{len(workers)})"
            )

            # 构建 prompt：看到前面的发言 + 用户消息
            previous_context = "\n".join(
                f"- **{r['name']}** 说: {r['content'][:300]}"
                for r in all_responses
            ) if all_responses else "(你是第一个发言)"

            prompt = (
                f"你是「{team.name}」团队的 {worker.name}。\n\n"
                f"## 轮流发言模式\n"
                f"你排在第 {idx + 1}/{len(workers)} 位。\n\n"
                f"## 之前的发言\n{previous_context}\n\n"
                f"## 用户消息\n{user_message}\n\n"
                f"## 任务\n"
                f"请根据之前的发言和用户消息，发表你的观点。"
                f"{'作为最后一个发言者，请做总结。' if idx == len(workers) - 1 else ''}\n"
                f"回复要简洁、有建设性。"
            )

            await agent_pool.acquire_with_retry(
                agent_id=wid, role_slot=role_slot,
                task_id=str(session_id), max_retries=2, interval=1.0,
            )
            try:
                yield self._agent_status(
                    wid, worker.name, "working",
                    f"{worker.name} 正在发言..."
                )
                w_s = await session_mgr.get_or_create_session(
                    team_id=str(team.id), agent_id=wid, task_id=str(session_id),
                )
                t0 = time.time()
                from app.services.collaboration.agent_executor import agent_executor as _exec3
                result = await _exec3.execute(
                    prompt=prompt, agent=worker, db=self.db,
                    session_id=str(session_id), team_id=str(team.id),
                    node_key="round_robin",
                )
                elapsed = time.time() - t0
                try:
                    await session_mgr.close_session(w_s.session_id)
                except Exception:
                    pass
            finally:
                await agent_pool.release(wid)

            content = result.get("content", "")
            all_responses.append({
                "name": worker.name,
                "content": content,
                "idx": idx,
            })

            yield self._agent_status(
                wid, worker.name, "done",
                f"{worker.name} 发言完毕 · {elapsed:.1f}s"
            )
            yield self._reasoning(
                source=wid,
                agent_name=worker.name,
                reasoning=result.get("reasoning", {}),
            )
            yield self._agent_message(
                source=wid,
                agent_name=worker.name,
                content=content,
                model=result.get("model", ""),
                latency=round(elapsed, 2),
            )
            memory = await self._save_message(
                session_id=session_id,
                team_id=team.id,
                user_message=user_message,
                assistant_message=content,
                agent_id=uuid.UUID(wid),
                agent_name=worker.name,
                reasoning=result.get("reasoning"),
            )
            if memory:
                yield self._event(DiscussionEventType.STORAGE, source=wid, payload={
                    "agent": worker.name,
                    "memory_id": str(memory.id),
                    "memory_level": "context",
                    "session_id": str(session_id),
                })

        # RoundRobin 完成
        yield self._thinking(
            source="system",
            step="round_robin_complete",
            detail=f"✅ 轮流发言完成：{len(workers)} 个成员发言",
        )
        yield self._event(DiscussionEventType.MESSAGE_COMPLETE, source="system")

    # ── Direct 模式：直接执行 ──

    async def _execute_direct_mode(
        self,
        session_id: uuid.UUID,
        user_message: str,
        team,
        history: Optional[list[dict]],
    ) -> AsyncGenerator[DiscussionEvent, None]:
        """Swarm/Hierarchy 模式：选择一个 Agent 直接对话"""
        from app.models.agent import Agent
        from app.services.agent_factory import agent_chat
        from app.services.session_manager import get_session_manager
        from app.services.agent_pool import agent_pool

        # 取团队中第一个可用的 Agent
        worker = await self._get_any_worker(team)
        if not worker:
            yield self._error("团队没有可用的 Agent")
            return

        # 构建团队上下文
        team_roster = await self._build_team_roster(team)
        roster_text = "\n".join(f"- {r['icon']} {r['name']} ({r['role']})" for r in team_roster) if team_roster else "暂无成员"

        yield self._thinking(
            source=str(worker.id),
            step="agent_response",
            detail=f"{worker.name} 正在回复（团队: {team.name}）...",
        )

        worker_id = str(worker.id)
        await agent_pool.acquire_with_retry(
            agent_id=worker_id, role_slot="dev",
            task_id=str(session_id), max_retries=2, interval=1.0,
        )
        try:
            session_mgr = get_session_manager(self.db)
            worker_session = await session_mgr.get_or_create_session(
                team_id=str(team.id),
                agent_id=worker_id,
                task_id=str(session_id),
            )

            # 包含团队信息的提示
            prompted_message = (
                f"你是「{team.name}」团队的 {worker.name}。\n"
                f"团队成员:\n{roster_text}\n\n"
                f"## 用户消息\n{user_message}\n\n"
                f"请以团队成员的身份回复用户。你可以与团队其他成员协作。"
            )

            t0 = time.time()
            from app.services.collaboration.agent_executor import agent_executor as _exec4
            result = await _exec4.execute(
                prompt=prompted_message, agent=worker, db=self.db,
                session_id=str(session_id), team_id=str(team.id),
                node_key="direct_agent",
            )
            elapsed = time.time() - t0

            yield self._reasoning(
                source=worker_id,
                agent_name=worker.name,
                reasoning=result.get("reasoning", {}),
            )

            yield self._agent_message(
                source=worker_id,
                agent_name=worker.name,
                content=result.get("content", ""),
                model=result.get("model", ""),
                latency=round(elapsed, 2),
                questions=result.get("questions", []),
            )

            # 保存对话记忆
            memory = await self._save_message(
                session_id=session_id,
                team_id=team.id,
                user_message=user_message,
                assistant_message=result.get("content", ""),
                agent_id=uuid.UUID(worker_id),
                agent_name=worker.name,
                reasoning=result.get("reasoning"),
            )
            if memory:
                yield self._event(DiscussionEventType.STORAGE, source=worker_id, payload={
                    "agent": worker.name,
                    "memory_id": str(memory.id),
                    "memory_level": "context",
                    "session_id": str(session_id),
                })

            try:
                await worker_session.close_session(worker_session.session_id)
            except Exception:
                pass
        finally:
            await agent_pool.release(worker_id)

        yield self._event(DiscussionEventType.MESSAGE_COMPLETE, source="system")

    # ── 辅助方法 ──

    async def _save_message(
        self,
        session_id: uuid.UUID,
        team_id: uuid.UUID,
        user_message: str,
        assistant_message: str,
        agent_id: uuid.UUID,
        agent_name: str = "",
        reasoning: Optional[dict] = None,
    ) -> Optional[any]:
        """保存对话消息到 Memory + 更新 session 计数，返回 Memory 对象或 None"""
        from app.services.memory_manager import MemoryManager
        from app.services.session_service import SessionService

        # 在 reasoning 中添加 agent name
        meta = dict(reasoning) if reasoning else {}
        meta["agent"] = agent_name

        memory = None
        try:
            mm = MemoryManager(self.db)
            memory = await mm.save_dialog_memory(
                agent_id=agent_id,
                team_id=team_id,
                user_message=user_message,
                assistant_message=assistant_message,
                session_id=str(session_id),
                reasoning_meta=meta,
            )
        except Exception as e:
            logger.warning(f"Failed to save dialog memory: {e}")

        try:
            svc = SessionService(self.db)
            await svc.increment_message_count(session_id)
        except Exception as e:
            logger.warning(f"Failed to increment message count: {e}")

        return memory

    async def _build_team_roster(self, team) -> list[dict]:
        """构建团队花名册（Agent 名称 + 角色）"""
        from app.models.agent import Agent
        from sqlalchemy import select
        roster = []
        try:
            from app.models.team_member import TeamMember
            stmt = select(TeamMember).where(TeamMember.team_id == team.id)
            result = await self.db.execute(stmt)
            members = result.scalars().all()
            for m in members:
                agent = await self.db.get(Agent, m.agent_id)
                if agent:
                    icon_map = {"pm": "📋", "dev": "💻", "qa": "🔍", "designer": "🎨"}
                    roster.append({
                        "name": agent.name,
                        "role": m.role_name,
                        "icon": icon_map.get(m.role_name, "🤖"),
                    })
        except Exception:
            pass

        if not roster and team.leader_id:
            leader = await self.db.get(Agent, team.leader_id)
            if leader:
                roster.append({"name": leader.name, "role": "leader", "icon": "👑"})

        return roster

    async def _select_workers(self, team, selected_roles: list[str], dispatch_content: str) -> list:
        """根据 Supervisor 指定的角色列表选择 Agent"""
        from app.models.agent import Agent
        from sqlalchemy import select

        try:
            from app.models.team_member import TeamMember
            stmt = select(TeamMember).where(TeamMember.team_id == team.id)
            result = await self.db.execute(stmt)
            members = result.scalars().all()

            # ALL → 返回所有成员
            if "ALL" in selected_roles or "all" in [r.lower() for r in selected_roles]:
                workers = []
                for m in members:
                    agent = await self.db.get(Agent, m.agent_id)
                    if agent:
                        workers.append(agent)
                return workers[:5]

            workers = []
            for m in members:
                if m.role_name in selected_roles:
                    agent = await self.db.get(Agent, m.agent_id)
                    if agent:
                        workers.append(agent)

            seen = set()
            unique = []
            for w in workers:
                if w.id not in seen:
                    seen.add(w.id)
                    unique.append(w)
            return unique[:5] if unique else unique
        except Exception:
            return []

    async def _get_worker_for_role(self, team, role_slot: str):
        """按角色槽位获取 Worker Agent"""
        from app.services.team_manager import TeamManager
        try:
            tm = TeamManager(self.db)
            agent = await tm.get_agent_for_slot(team.id, role_slot)
            return agent
        except Exception:
            return None

    async def _get_all_workers(self, team) -> list[tuple]:
        """获取团队所有成员（Agent + role_slot）"""
        from app.models.agent import Agent
        from sqlalchemy import select
        workers = []
        try:
            from app.models.team_member import TeamMember
            stmt = select(TeamMember).where(TeamMember.team_id == team.id)
            result = await self.db.execute(stmt)
            for m in result.scalars().all():
                agent = await self.db.get(Agent, m.agent_id)
                if agent:
                    workers.append((agent, {"role_slot": m.role_name}))
        except Exception:
            pass
        return workers

    async def _get_any_worker(self, team):
        """获取团队中任意一个可用 Agent

        优先级：TeamMember → leader_id → 任意 Agent
        """
        from app.models.agent import Agent
        from sqlalchemy import select

        # 1. 从 TeamMember 查找
        try:
            from app.models.team_member import TeamMember
            stmt = select(TeamMember).where(TeamMember.team_id == team.id).limit(1)
            result = await self.db.execute(stmt)
            member = result.scalar_one_or_none()
            if member:
                agent = await self.db.get(Agent, member.agent_id)
                if agent:
                    return agent
        except Exception:
            pass

        # 2. 使用 leader_id
        if team.leader_id:
            agent = await self.db.get(Agent, team.leader_id)
            if agent:
                return agent

        # 3. 从任意 Agent
        try:
            stmt = select(Agent).limit(1)
            result = await self.db.execute(stmt)
            agent = result.scalar_one_or_none()
            return agent
        except Exception:
            pass

        return None

    def _parse_workers(self, content: str) -> list[str]:
        """从 Supervisor 回复中解析要派发的角色列表"""
        import json
        try:
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                data = json.loads(content[start:end].strip())
            elif content.strip().startswith("{"):
                data = json.loads(content.strip())
            else:
                return ["dev"]
            workers = data.get("workers", [])
            if isinstance(workers, list) and len(workers) > 0:
                return workers
            # 兼容旧格式 selected_role
            role = data.get("selected_role", "dev")
            return [role] if role else ["dev"]
        except Exception:
            return ["dev"]

    # ── 事件构建辅助 ──

    def _thinking(self, source: str, step: str, detail: str, result: str = "", agent_name: str = ""):
        return self._event(DiscussionEventType.THINKING, source=source, payload={
            "step": step, "detail": detail, "result": result,
            "agent": agent_name or "System",
        })

    def _reasoning(self, source: str, agent_name: str, reasoning: dict):
        """Agent 推理完成：路由决策 + 工具调用 + 上下文 + 思考步骤 + 执行模式"""
        return self._event(DiscussionEventType.REASONING, source=source, payload={
            "agent": agent_name,
            "model_routing": reasoning.get("model_routing", {}),
            "tool_calls": reasoning.get("tool_calls", []),
            "context_used": reasoning.get("context_used", {}),
            "decision_summary": reasoning.get("decision_summary"),
            "thinking_steps": reasoning.get("thinking_steps"),
            "prompt_length": reasoning.get("prompt_length"),
            "input_content": reasoning.get("input_content"),
            "supervisor_analysis": reasoning.get("supervisor_analysis"),
            "dispatch_guidance": reasoning.get("dispatch_guidance"),
            "latency": reasoning.get("latency"),
            "exec_mode": reasoning.get("exec_mode", ""),
            "iterations": reasoning.get("iterations", 1),
        })

    def _agent_message(self, source: str, agent_name: str, content: str, model: str, latency: float, questions: list = None):
        # 清理内容中的 tool_call JSON（防止泄露到前端）
        cleaned = _clean_tool_call_from_content(content)
        return self._event(DiscussionEventType.AGENT_MESSAGE, source=source, payload={
            "agent": agent_name,
            "content": cleaned,
            "model": model,
            "latency": latency,
            "questions": questions or [],
        })

    def _agent_status(self, agent_id: str, agent_name: str, status: str, summary: str = ""):
        """Agent 状态灯: idle | thinking | working | done | error"""
        return self._event(DiscussionEventType.AGENT_STATUS, source=agent_id, payload={
            "agent_id": agent_id,
            "agent_name": agent_name,
            "status": status,
            "summary": summary or f"{agent_name} {status}",
        })

    def _agent_to_agent(self, from_id: str, from_name: str, to_id: str, to_name: str, content: str, msg_type: str = "direct"):
        """Agent 间 Mailbox 消息"""
        return self._event(DiscussionEventType.AGENT_TO_AGENT, source=from_id, payload={
            "from_agent_id": from_id,
            "from_agent_name": from_name,
            "to_agent_id": to_id,
            "to_agent_name": to_name,
            "content": content,
            "message_type": msg_type,
        })

    def _error(self, detail: str):
        return self._event(DiscussionEventType.MESSAGE_COMPLETE, source="system", payload={
            "error": detail,
        })

    def _event(self, type_: DiscussionEventType, source: str = "system", payload: dict = None):
        return DiscussionEvent(type=type_, source=source, payload=payload or {})


def _clean_tool_call_from_content(content: str) -> str:
    """从内容中移除所有形式的 tool_call，防止泄露到前端"""
    if not content:
        return ""
    import re
    cleaned = content
    # 移除 TOOL_CALL: {"name": "...", "params": {...}} 格式（含嵌套花括号）
    cleaned = re.sub(
        r'TOOL_CALL:\s*\{[^}]*?"name"\s*:\s*"[^"]*"[^}]*?"params"\s*:\s*\{[^}]*?\}\s*\}\s*\}?',
        '', cleaned, flags=re.DOTALL,
    )
    # 移除 ```json\n{"tool_call":...}\n``` 代码块
    cleaned = re.sub(r'```json\s*\n?\{[^`]*?"tool_call"[^`]*?\}\s*\n?```', '', cleaned, flags=re.DOTALL)
    # 移除内联的 {"tool_call": ...}
    if '{"tool_call"' in cleaned:
        idx = cleaned.index('{"tool_call"')
        depth = 0; end = idx
        for i, c in enumerate(cleaned[idx:], idx):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: end = i + 1; break
        if end > idx: cleaned = cleaned[:idx] + cleaned[end:]
    # 清理残留
    cleaned = re.sub(r'```json\s*\n?\s*```', '', cleaned)
    return cleaned.strip()
