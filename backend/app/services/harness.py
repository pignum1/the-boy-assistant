"""Harness — Agent 执行的横切拦截层

将三个引擎中重复的横切关注点（上下文注入、Token 管控、文件提取、
记忆持久化、独立验证、审计日志、资源清理）统一为标准接口。

使用方式：
    harness = Harness(db, send_fn)
    await engine.run(..., harness=harness)

引擎内部调用：
    ctx = ExecutionContext(...)
    enriched = await harness.before_execution(ctx)
    if not enriched.can_proceed:
        return  # Token budget exceeded

    result = await agent_chat(...)

    exec_result = ExecutionResult(...)
    await harness.after_execution(ctx, exec_result)
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from sqlalchemy import select as _sel

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]


# ═══════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════

@dataclass
class ExecutionContext:
    """单次 Agent 执行的上下文。"""
    session_id: str
    team_id: str
    agent_id: str
    agent_name: str
    node_key: str              # 工作流节点 key / 角色名
    task_id: Optional[str] = None
    instruction: str = ""       # 本次执行的任务描述
    # ── Prompt 构建所需字段 ──
    user_message: str = ""      # 原始用户需求
    artifacts: dict[str, str] = field(default_factory=dict)  # 前置节点产物 {node_id: content}
    depends_on: list[str] = field(default_factory=list)      # 依赖的前置节点 ID 列表
    workspace_path: str = ""    # 工作空间路径
    code_output_required: bool = False  # 是否需要代码输出格式要求


@dataclass
class ExecutionResult:
    """单次 Agent 执行的结果。"""
    content: str
    model: str
    provider: str
    latency_ms: float
    usage: dict                 # {prompt_tokens, completion_tokens, total_tokens}
    tool_results: list[dict] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class BeforeExecutionResult:
    """before_execution 的返回结果（强类型替代 dict）。"""
    prompt: Optional[str] = None           # 构建好的完整 prompt（包含上下文 + 产物 + 格式要求）
    context: Optional[str] = None          # 注入的额外上下文（记忆 + RAG）
    token_budget: Optional[dict] = None    # {"remaining": int, "total": int}
    is_blocked: bool = False               # 是否被阻止执行
    block_reason: str = ""                 # 阻止原因

    @property
    def can_proceed(self) -> bool:
        return not self.is_blocked


@dataclass
class VerificationRequest:
    """验证请求。"""
    task_id: str
    task_name: str
    requirements: str
    artifacts: dict[str, str]       # node_key → content
    produced_by_agent: str


@dataclass
class VerificationResult:
    """验证结果。"""
    passed: bool
    score: float                    # 0.0 - 1.0
    issues: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    reviewer_agent: str = ""


# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════

@dataclass
class HarnessConfig:
    """Harness 行为配置（全部可开关，渐进式启用）。"""

    enable_context_injection: bool = True
    enable_file_extraction: bool = True
    enable_token_tracking: bool = True
    enable_token_budget: bool = True
    enable_persistence: bool = True
    enable_audit_log: bool = True
    enable_lifecycle_events: bool = True
    enable_memory_cleanup: bool = True

    min_token_budget: int = 1000
    max_session_tokens: int = 1_000_000
    persist_max_retries: int = 2
    persist_retry_delay_ms: int = 500


# ═══════════════════════════════════════════
# Harness
# ═══════════════════════════════════════════

class Harness:
    """Agent 执行的横切拦截器。注入到三引擎中统一处理配套设施。"""

    def __init__(
        self,
        db,
        send_fn: SendFn,
        config: Optional[HarnessConfig] = None,
        loop_engine=None,  # Optional[LoopEngine]
    ):
        self.db = db
        self.send_fn = send_fn
        self.config = config or HarnessConfig()
        self.loop_engine = loop_engine

    # ── Loop Engine 集成 ──

    async def handle_verification_failure(
        self,
        error: str,
        task_id: str,
        agent_id: str,
        session_id: str,
        retry_count: int = 0,
    ) -> "LoopResult":
        """验证失败时调用 Loop Engine 进行错误恢复。

        Returns:
            LoopResult 指示下一步：retry / retry_with_feedback / escalate_hitl
        """
        if not self.loop_engine:
            from app.services.loop_engine import LoopResult
            return LoopResult(
                recovered=False, action="escalate_hitl",
                hitl_data={"type": "no_loop_engine", "error": error[:200]},
                final_error=error[:200],
            )

        from app.services.loop_engine import LoopContext
        ctx = LoopContext(
            task_id=task_id, agent_id=agent_id, session_id=session_id,
            retry_count=retry_count, max_retries=self.loop_engine.max_retries,
        )
        return await self.loop_engine.handle_failure(error, ctx)

    # ── 事件发射 ──

    def _emit(self, event_type: "str", **payload) -> None:
        """发射事件并持久化到 Observer。"""
        try:
            from app.services.observer.events import EventType as ET, make_event
            from app.services.observer.persister import ensure_table, persist
            from app.core.database import async_session as _async_session
            import logging
            _log = logging.getLogger(__name__)
            et = ET(event_type) if isinstance(event_type, str) else event_type
            event = make_event(et, source="harness", **payload)

            # 同步持久化（不用 create_task，确保事件落盘）
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._persist_event(event))
                else:
                    asyncio.run(self._persist_event(event))
            except RuntimeError:
                asyncio.run(self._persist_event(event))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Harness _emit failed: {e}")

    async def _persist_event(self, event) -> None:
        """持久化单个事件（独立 DB 会话）。"""
        try:
            from app.services.observer.persister import ensure_table, persist
            from app.core.database import async_session as _async_session
            async with _async_session() as db:
                await ensure_table(db)
                await persist(db, event)
        except Exception:
            pass

    # ── 执行前 ──

    async def before_execution(self, ctx: ExecutionContext) -> BeforeExecutionResult:
        """Agent 执行前准备：Prompt 构建 + 上下文注入 + Token 预算检查 + 事件通知。"""
        result = BeforeExecutionResult()

        # 0. 构建标准化 Prompt（统一所有引擎的输出格式）
        result.prompt = await self._build_prompt(ctx)

        if self.config.enable_context_injection:
            result.context = await self._inject_context(ctx)

        if self.config.enable_token_budget:
            budget = await self._check_token_budget(ctx)
            result.token_budget = budget
            if budget and budget.get("remaining", 0) < self.config.min_token_budget:
                result.is_blocked = True
                result.block_reason = (
                    f"Session {ctx.session_id[:8]} token budget exceeded "
                    f"({budget['remaining']}/{budget.get('total', '?')})"
                )

        if self.config.enable_lifecycle_events:
            await self.send_fn({
                "type": "agent_status", "source": "harness",
                "timestamp": "",
                "payload": {
                    "agent_id": ctx.agent_id, "agent_name": ctx.agent_name,
                    "status": "preparing", "task_id": ctx.task_id,
                    "node_key": ctx.node_key,
                }
            })

        # 事件：Agent 执行开始
        from app.services.observer.events import EventType as ET
        self._emit(
            ET.AGENT_EXECUTION_STARTED.value,
            session_id=ctx.session_id, team_id=ctx.team_id,
            agent_id=ctx.agent_id, agent_name=ctx.agent_name,
            task_id=ctx.task_id, node_key=ctx.node_key,
        )

        return result

    # ── 执行后 ──

    async def after_execution(self, ctx: ExecutionContext, result: ExecutionResult) -> None:
        """Agent 执行后处理：文件提取 + Token 统计 + 持久化 + 审计。"""
        import logging as _logging
        _log = _logging.getLogger(__name__)
        _log.info(f"Harness after_execution START for {ctx.agent_name}")

        if self.config.enable_file_extraction and result.content:
            _log.info(f"Harness extracting files for {ctx.agent_name}")
            result.files_written = await self._extract_files(ctx, result)

        if self.config.enable_token_tracking:
            self._record_tokens(ctx, result)

        if self.config.enable_persistence:
            try:
                await self._persist_with_retry(ctx, result)
            except Exception:
                pass  # 持久化失败不影响主流程，_emit 会直接写 observer_events

        if self.config.enable_audit_log:
            self._audit_log(ctx, result)

        # 事件：Agent 执行完成
        _log.info(f"Harness emitting event for {ctx.agent_name}")
        from app.services.observer.events import EventType as ET
        tokens = result.usage.get("total_tokens", 0) if isinstance(result.usage, dict) else 0
        self._emit(
            ET.AGENT_EXECUTION_COMPLETED.value,
            session_id=ctx.session_id, team_id=ctx.team_id,
            agent_id=ctx.agent_id, agent_name=ctx.agent_name,
            task_id=ctx.task_id, node_key=ctx.node_key,
            model=result.model, provider=result.provider,
            latency_ms=result.latency_ms, tokens=tokens,
            files_written=result.files_written,
        )
        _log.info(f"Harness after_execution DONE for {ctx.agent_name}")

    # ── 验证 ──

    async def verify(self, req: VerificationRequest) -> VerificationResult:
        """独立验证 Agent 输出。选择非生产者的 Agent 进行审查。"""
        reviewer = await self._select_reviewer(exclude_agent=req.produced_by_agent)
        if not reviewer:
            return VerificationResult(
                passed=False, score=0.0,
                issues=[{"severity": "error", "description": "无可用验证 Agent"}],
                suggestions=["请人工审查"], reviewer_agent="system",
            )

        prompt = self._build_verification_prompt(req)
        try:
            from app.services.agent_chat import agent_chat
            llm_result = await agent_chat(
                db=self.db, agent=reviewer, message=prompt,
                return_reasoning=False, save_memory=False,
            )
            return self._parse_verification_result(llm_result, reviewer.name)
        except Exception as e:
            logger.error(f"Harness verification failed: {e}")
            return VerificationResult(
                passed=False, score=0.0,
                issues=[{"severity": "error", "description": f"验证执行失败: {str(e)[:200]}"}],
                suggestions=["请人工审查"], reviewer_agent=reviewer.name,
            )

    # ── 清理 ──

    async def cleanup(self, session_id: str) -> None:
        """会话结束时清理计数器、暂停状态、Token 预算。"""
        if self.config.enable_token_tracking:
            try:
                from app.services.observer import token_tracker
                token_tracker.reset_session(session_id)
            except Exception:
                pass

        if self.config.enable_memory_cleanup:
            try:
                from app.services.collaboration.engines.langgraph_pause import (
                    _paused,
                )
                _paused.pop(session_id, None)
            except Exception:
                pass

    # ═══════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════

    async def _build_prompt(self, ctx: ExecutionContext) -> str:
        """构建标准化 Agent Prompt。

        统一所有引擎（Swarm/Supervisor/LangGraph）的 prompt 结构，
        使用 M5 context_pipeline + M8 peer_mailbox。

        各引擎只需要传入 ExecutionContext 即可获得完整 prompt。
        """
        try:
            from app.services.collaboration.m5_context_pipeline import context_pipeline
            from app.services.collaboration.m8_peer_mailbox import peer_mailbox

            # 拉取对等 Agent 消息
            peer_msgs = peer_mailbox.format_for_context(ctx.session_id, ctx.agent_name)

            # 筛选该节点依赖的前置产物
            dependent_artifacts = ctx.artifacts  # 由调用方按 depends_on 预过滤

            task_dict = {
                "id": ctx.task_id or ctx.node_key,
                "title": ctx.node_key,
                "description": ctx.instruction,
                "assigned_role": ctx.agent_name,
                "depends_on": ctx.depends_on,
            }

            worker_ctx = context_pipeline.build_context(
                requirement_anchor=ctx.user_message,
                task=task_dict,
                all_artifacts=dependent_artifacts,
                peer_messages=peer_msgs,
            )
            prompt = context_pipeline.format_context(worker_ctx, workspace_path=ctx.workspace_path)

            # 代码输出格式要求（LangGraph / 需要产出代码文件的场景）
            if ctx.code_output_required:
                prompt += (
                    "\n\n## ⚠️ 代码输出格式（不遵守将被丢弃）\n"
                    "**每个文件必须用一个代码块输出，代码块第一行必须标注语言和相对路径。**\n\n"
                    "✅ 正确：```python backend/app/main.py\n"
                    "❌ 错误（没有路径）：```python\n\n"
                    "项目目录约定：后端→`backend/`、前端→`frontend/`、测试→`tests/`、部署→`deploy/`、文档→`docs/`\n"
                    "**语义化文件名**（`todo_service.py`），禁止 `code_1.py` / `snippet_1.txt`。\n\n"
                    "请输出本节点的产物。"
                )

            return prompt
        except Exception:
            # 回退：简单拼接
            return f"{ctx.instruction}\n\n## 用户需求\n{ctx.user_message}"

    async def _inject_context(self, ctx: ExecutionContext) -> Optional[str]:
        """从记忆和 RAG 注入上下文。"""
        try:
            from app.services.context_manager import ContextManager
            cm = ContextManager(self.db)
            context_data = await cm.build_context_for_agent(
                agent_id=ctx.agent_id,
                team_id=ctx.team_id,
                session_id=ctx.session_id,
                task_description=ctx.instruction,
            )
            return context_data
        except Exception as e:
            logger.warning(f"Harness context injection failed: {e}")
            return None

    async def _check_token_budget(self, ctx: ExecutionContext) -> Optional[dict]:
        """检查 per-session Token 预算。"""
        try:
            from app.services.observer import token_tracker
            return token_tracker.get_session_budget(ctx.session_id)
        except Exception:
            return None

    def _record_tokens(self, ctx: ExecutionContext, result: ExecutionResult) -> None:
        """记录 Token 使用统计。"""
        try:
            usage = result.usage if isinstance(result.usage, dict) else {}
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            if prompt_tokens + completion_tokens > 0:
                from app.services.observer import token_tracker
                token_tracker.record(
                    trace_id=ctx.session_id or "unknown",
                    span_id=f"{ctx.agent_name}-{ctx.node_key}",
                    model=result.model,
                    provider=result.provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
        except Exception as e:
            logger.warning(f"Harness token tracking failed: {e}")

    async def _extract_files(self, ctx: ExecutionContext, result: ExecutionResult) -> list[str]:
        """从 Agent 输出提取代码块到 workspace。"""
        try:
            from app.services.workspace.manager import workspace_manager
            from app.services.collaboration.workspace_utils import extract_files_from_content
            ws = workspace_manager.get_or_create(ctx.session_id)
            return extract_files_from_content(
                result.content, ws.path,
                source_label=f"{ctx.agent_name}/{ctx.node_key}",
            )
        except Exception as e:
            logger.warning(f"Harness file extraction failed: {e}")
            return []

    async def _persist_with_retry(self, ctx: ExecutionContext, result: ExecutionResult) -> None:
        """持久化记忆，最多重试 N 次。"""
        for attempt in range(self.config.persist_max_retries):
            try:
                from app.services.memory_manager import MemoryManager
                mm = MemoryManager(self.db)
                await mm.save_memory(
                    level="context",
                    content=f"[{ctx.agent_name}] {result.content[:2000]}",
                    type="standard",
                    team_id=uuid.UUID(ctx.team_id) if ctx.team_id else None,
                    session_id=ctx.session_id,
                    importance=0.5,
                    created_by="harness",
                    metadata_={
                        "agent": ctx.agent_name,
                        "model": result.model,
                        "provider": result.provider,
                        "latency_ms": result.latency_ms,
                        "node_key": ctx.node_key,
                        "task_id": ctx.task_id,
                    },
                )
                await self.db.commit()
                return
            except Exception as e:
                if attempt < self.config.persist_max_retries - 1:
                    await asyncio.sleep(
                        self.config.persist_retry_delay_ms / 1000 * (attempt + 1)
                    )
                else:
                    logger.error(
                        f"Harness persist FAILED after {self.config.persist_max_retries} "
                        f"attempts for {ctx.agent_name}: {e}"
                    )

    def _audit_log(self, ctx: ExecutionContext, result: ExecutionResult) -> None:
        """记录审计日志。"""
        logger.info(
            "harness.audit | session=%s agent=%s node=%s model=%s "
            "latency=%.0fms tokens=%s",
            ctx.session_id[:8], ctx.agent_name, ctx.node_key,
            result.model, result.latency_ms,
            result.usage.get("total_tokens", 0) if isinstance(result.usage, dict)
            else result.usage,
        )

    async def _select_reviewer(self, exclude_agent: str):
        """选择验证 Agent。优先选 reviewed_count 最少的，公平分配审查负载。"""
        from app.models.agent import Agent
        result = await self.db.execute(
            _sel(Agent).where(
                Agent.status == "idle",
                Agent.name != exclude_agent,
            ).order_by(Agent.reviewed_count.asc()).limit(1)
        )
        agent = result.scalar_one_or_none()
        if agent:
            agent.reviewed_count = (agent.reviewed_count or 0) + 1
            await self.db.commit()
        return agent

    def _truncate_artifact(self, content: str, max_chars: int = 4000) -> str:
        """智能截断产物：代码保留头尾，文档保留章节标题。"""
        if len(content) <= max_chars:
            return content
        lines = content.split('\n')
        if any(kw in content[:200] for kw in ['def ', 'class ', 'import ', 'package ']):
            head = '\n'.join(lines[:50])
            tail = '\n'.join(lines[-20:])
            return f"{head}\n\n... ({len(lines) - 70} lines truncated) ...\n\n{tail}"
        sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
        if len(sections) > 1:
            return sections[0][:1500] + "\n\n... (后续章节省略) ..."
        return content[:max_chars] + f"\n\n... (total {len(content)} chars, truncated)"

    def _build_verification_prompt(self, req: VerificationRequest) -> str:
        parts = []
        for k, v in req.artifacts.items():
            truncated = self._truncate_artifact(v)
            parts.append(f"### {k}\n{truncated}")
        artifacts_text = '\n'.join(parts)

        return f"""请独立审查以下任务的输出质量：

## 需求
{req.requirements}

## 产物
{artifacts_text}

请评估：
1. 是否满足需求？
2. 是否有逻辑缺陷或安全隐患？
3. 是否有更好的实现方式？

输出格式：PASS 或 FAIL，附简短理由。"""

    def _parse_verification_result(
        self, llm_result: dict, reviewer_name: str
    ) -> VerificationResult:
        content = (llm_result.get("content") or "").strip().lstrip("*_# ")
        passed = content.upper().startswith("PASS")
        return VerificationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            issues=(
                []
                if passed
                else [{"severity": "warning", "description": content[:200]}]
            ),
            suggestions=[] if passed else ["请人工审查"],
            reviewer_agent=reviewer_name,
        )


# ═══════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════

def create_default_harness(db, send_fn: SendFn) -> Harness:
    """创建默认配置的 Harness 实例。"""
    return Harness(db, send_fn, HarnessConfig())


def create_minimal_harness(db, send_fn: SendFn) -> Harness:
    """创建最小化 Harness — 全部功能关闭，完全透明。用于渐进式部署验证。"""
    return Harness(db, send_fn, HarnessConfig(
        enable_context_injection=False,
        enable_file_extraction=False,
        enable_token_tracking=False,
        enable_token_budget=False,
        enable_persistence=False,
        enable_audit_log=False,
        enable_lifecycle_events=False,
        enable_memory_cleanup=False,
    ))
