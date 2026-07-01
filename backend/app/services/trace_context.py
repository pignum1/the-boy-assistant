"""Trace 上下文传播 — 基于 Python contextvars 的跨异步调用链追踪

在整个异步调用链中自动传播 trace_id 和 parent_span_id，
无需在每个函数签名上加 trace 参数。

三层元数据结构化：
  Trace (根)   — [{mode}] {team_name} | {user_message[:60]}
  Span (执行)   — [{exec_mode}] {agent_name} ({role})
  Generation (LLM) — chat:{model}

用法:
    from app.services.trace_context import TraceContext, trace_metadata as tm

    # 根 trace
    with TraceContext.create_trace(
        name=tm.trace_name(mode="swarm", team_name="产品开发团队", user_message="..."),
        session_id="xxx",
        metadata=tm.trace_meta(mode="swarm", team_name="产品开发团队", ...),
    ):
        # Agent 执行 span
        with TraceContext.span(
            name=tm.span_name(exec_mode="react", agent_name="后端", role="backend_dev"),
            metadata=tm.span_meta(exec_mode="react", agent_name="后端", ...),
        ):
            # LLM 调用
            with TraceContext.generation(
                name=f"chat:{model}",
                metadata=tm.gen_meta(provider="deepseek", agent="后端", ...),
            ):
                ...

设计:
  - ContextVar 在每次 `with` 进入时压栈，退出时弹栈
  - LangFuse v4 SDK: start_observation() + create_trace_id() + create_score()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ── ContextVars ──

_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_parent_span_id: ContextVar[Optional[str]] = ContextVar("parent_span_id", default=None)
_trace_session_id: ContextVar[Optional[str]] = ContextVar("trace_session_id", default=None)

# ── Metadata helpers (trace name + structured metadata for Dashboard) ──


class trace_metadata:
    """结构化元数据构造器。

    确保 Dashboard 中每条 trace/span/generation 有清晰、可筛选的元信息。
    """

    # ── Trace 级别 ──

    @staticmethod
    def trace_name(mode: str, team_name: str, user_message: str) -> str:
        """构造 trace 名称: [{mode}] {team_name} | {user_message_truncated}"""
        msg = user_message.replace("\n", " ").strip()[:60]
        return f"[{mode}] {team_name} | {msg}"

    @staticmethod
    def trace_meta(
        mode: str = "",
        team_name: str = "",
        team_id: str = "",
        session_id: str = "",
        user_message: str = "",
    ) -> dict[str, Any]:
        """Trace 级别元数据。"""
        return {
            "team_name": team_name,
            "team_id": team_id,
            "session_id": session_id,
            "mode": mode,
            "user_message": user_message[:200] if user_message else "",
        }

    @staticmethod
    def trace_tags(mode: str, team_name: str) -> list[str]:
        """Trace 级别标签。"""
        return [f"mode:{mode}", f"team:{team_name}"]

    # ── Span 级别（Agent 执行）──

    @staticmethod
    def span_name(exec_mode: str, agent_name: str, role: str = "") -> str:
        """构造 span 名称: [{exec_mode}] {agent_name} ({role})"""
        role_suffix = f" ({role})" if role else ""
        return f"[{exec_mode}] {agent_name}{role_suffix}"

    @staticmethod
    def span_meta(
        exec_mode: str = "",
        agent_name: str = "",
        agent_role: str = "",
        node_key: str = "",
        provider: str = "",
        iteration: int = 0,
        max_iterations: int = 0,
        session_id: str = "",
        team_id: str = "",
    ) -> dict[str, Any]:
        """Span 级别元数据（Agent 执行）。"""
        return {
            "agent_name": agent_name,
            "agent_role": agent_role,
            "exec_mode": exec_mode,
            "node_key": node_key,
            "provider": provider,
            "iteration": iteration,
            "max_iterations": max_iterations,
            "session_id": session_id,
            "team_id": team_id,
        }

    # ── Span 级别（Phase 子阶段）──

    @staticmethod
    def phase_span_name(mode: str, phase_name: str, phase_index: int = 0) -> str:
        """构造 phase span 名称: [{mode}] Phase {i}: {phase_name}"""
        if phase_index > 0:
            return f"[{mode}] Phase {phase_index}: {phase_name}"
        return f"[{mode}] {phase_name}"

    @staticmethod
    def phase_span_meta(
        mode: str = "",
        phase_name: str = "",
        phase_index: int = 0,
        total_phases: int = 0,
        agent_name: str = "",
    ) -> dict[str, Any]:
        """Phase span 元数据。"""
        return {
            "phase_name": phase_name,
            "phase_index": phase_index,
            "total_phases": total_phases,
            "agent_name": agent_name,
            "exec_mode": mode,
        }

    # ── Generation 级别（LLM 调用）──

    @staticmethod
    def gen_meta(
        provider: str = "",
        model: str = "",
        agent: str = "",
        exec_mode: str = "",
        latency_s: float = 0.0,
        iteration: int = 0,
    ) -> dict[str, Any]:
        """Generation 级别元数据（LLM 调用）。"""
        return {
            "provider": provider,
            "model": model,
            "agent": agent,
            "exec_mode": exec_mode,
            "latency_s": round(latency_s, 2),
            "iteration": iteration,
        }

    # ── Iteration span ──

    @staticmethod
    def iter_span_name(exec_mode: str, iteration: int) -> str:
        """构造迭代 span 名称: [{exec_mode}] Iteration {i}"""
        return f"[{exec_mode}] Iteration {iteration}"

    @staticmethod
    def iter_span_meta(
        exec_mode: str = "",
        iteration: int = 0,
        max_iterations: int = 0,
        agent_name: str = "",
    ) -> dict[str, Any]:
        """迭代 span 元数据。"""
        return {
            "exec_mode": exec_mode,
            "iteration": iteration,
            "max_iterations": max_iterations,
            "agent_name": agent_name,
        }


# ── TraceContext ──


class TraceContext:
    """Trace 上下文管理器，提供 trace/span/generation 的嵌套管理。

    惰性加载 LangFuse client —— import 此模块不会触发 LangFuse 初始化。
    使用 LangFuse SDK v4.x API: start_observation() / create_trace_id() / create_score()
    """

    @staticmethod
    def get_trace_id() -> Optional[str]:
        """获取当前 trace_id。"""
        return _trace_id.get()

    @staticmethod
    def get_parent_span_id() -> Optional[str]:
        """获取当前父 observation_id（用于挂接 generation）。"""
        return _parent_span_id.get()

    @staticmethod
    def get_session_id() -> Optional[str]:
        """获取当前 trace 关联的 session_id。"""
        return _trace_session_id.get()

    @staticmethod
    @contextmanager
    def create_trace(
        name: str,
        session_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> Generator[Optional[Any], None, None]:
        """创建根 trace。

        用法:
            with TraceContext.create_trace(
                name=trace_metadata.trace_name("swarm", "团队", "消息"),
                session_id="xxx",
                metadata=trace_metadata.trace_meta(...),
                tags=trace_metadata.trace_tags("swarm", "团队"),
            ) as trace:
                ...
        """
        from app.services.langfuse_client import (
            get_langfuse_client,
            propagate_attributes as _pa,
            start_as_current_observation,
        )

        client = get_langfuse_client()
        trace_obs = None  # the actual LangFuseSpan (after __enter__)
        trace_id_val: Optional[str] = None
        _prop = None
        _trace_ctx = None  # the context manager (for __exit__)

        if client:
            try:
                merged_meta = {**(metadata or {})}
                if tags:
                    merged_meta["tags"] = tags
                # Create root observation as current context
                _trace_ctx = start_as_current_observation(
                    name=name,
                    as_type="span",
                    metadata=merged_meta,
                )
                if _trace_ctx:
                    # Enter context → returns the actual LangFuseSpan
                    trace_obs = _trace_ctx.__enter__()
                    if trace_obs:
                        trace_id_val = getattr(trace_obs, "trace_id", None)

                    # NOW propagate session_id (after span is active)
                    if session_id:
                        _prop = _pa(session_id=session_id)
                        try:
                            _prop.__enter__()
                        except Exception:
                            _prop = None

                logger.info(f"[TraceContext] Created trace: {trace_id_val} ({name}) session={session_id[:20]}")
            except Exception as e:
                logger.warning(f"[TraceContext] Failed to create trace: {e}", exc_info=True)

        tid_token = _trace_id.set(trace_id_val)
        sid_token = _trace_session_id.set(session_id or None)
        ps_token = _parent_span_id.set(None)

        try:
            yield trace_obs
        finally:
            _trace_id.reset(tid_token)
            _trace_session_id.reset(sid_token)
            _parent_span_id.reset(ps_token)
            if _prop:
                try:
                    _prop.__exit__(None, None, None)
                except Exception:
                    pass
            if _trace_ctx:
                try:
                    _trace_ctx.__exit__(None, None, None)
                except Exception:
                    pass
                try:
                    trace_obs.end()
                except Exception as e:
                    logger.warning(f"[TraceContext] Failed to end trace: {e}")

    @staticmethod
    @contextmanager
    def span(
        name: str,
        metadata: Optional[dict[str, Any]] = None,
        input_data: Optional[Any] = None,
        tags: Optional[list[str]] = None,
    ) -> Generator[Optional[Any], None, None]:
        """创建子 span。

        用法:
            with TraceContext.span(
                name=trace_metadata.span_name("react", "后端", "backend_dev"),
                metadata=trace_metadata.span_meta(...),
            ) as span:
                ...
        """
        from app.services.langfuse_client import start_observation

        span_obj = None
        current_trace_id = _trace_id.get()
        current_parent_id = _parent_span_id.get()
        span_id_val: Optional[str] = None

        if current_trace_id:
            try:
                merged_meta = dict(metadata or {})
                if tags:
                    merged_meta["tags"] = tags
                span_obj = start_observation(
                    trace_id=current_trace_id,
                    name=name,
                    as_type="span",
                    parent_observation_id=current_parent_id or "",
                    input_data=input_data,
                    metadata=merged_meta,
                )
                if span_obj:
                    span_id_val = span_obj.id
                    logger.debug(
                        f"[TraceContext] Created span: {span_id_val} ({name}) "
                        f"parent={current_parent_id} trace={current_trace_id}"
                    )
            except Exception as e:
                logger.warning(f"[TraceContext] Failed to create span: {e}")

        ps_token = _parent_span_id.set(span_id_val)

        try:
            yield span_obj
        finally:
            _parent_span_id.reset(ps_token)
            if span_obj:
                try:
                    span_obj.end()
                except Exception as e:
                    logger.warning(f"[TraceContext] Failed to end span: {e}")

    @staticmethod
    def score(
        name: str,
        value: float,
        comment: str = "",
        data_type: str = "NUMERIC",
    ) -> None:
        """为当前 trace 添加评分（质量追踪）。

        用法:
            TraceContext.score("review_score", 0.95, comment="验证通过")
            TraceContext.score("clarity_score", 0.8, comment="需求清晰度")
        """
        from app.services.langfuse_client import create_score

        current_trace_id = _trace_id.get()

        if current_trace_id:
            try:
                create_score(
                    trace_id=current_trace_id,
                    name=name,
                    value=value,
                    comment=comment,
                    data_type=data_type,
                )
                logger.debug(
                    f"[TraceContext] Score: {name}={value} ({comment[:50]}) "
                    f"trace={current_trace_id}"
                )
            except Exception as e:
                logger.warning(f"[TraceContext] Failed to create score: {e}")

    @staticmethod
    @contextmanager
    def generation(
        name: str = "llm-call",
        model: str = "",
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        usage: Optional[dict[str, int]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Generator[Optional[Any], None, None]:
        """创建 generation（LLM 调用记录）。

        用法:
            with TraceContext.generation(
                name=f"chat:{model}",
                model=model,
                usage={"prompt_tokens": 5000, "completion_tokens": 2000, "total_tokens": 7000},
                metadata=trace_metadata.gen_meta(provider="deepseek", agent="后端", ...),
            ) as gen:
                ...
        """
        from app.services.langfuse_client import start_observation

        gen_obj = None
        current_trace_id = _trace_id.get()
        current_parent_id = _parent_span_id.get()

        if current_trace_id:
            try:
                gen_obj = start_observation(
                    trace_id=current_trace_id,
                    name=name,
                    as_type="generation",
                    parent_observation_id=current_parent_id or "",
                    model=model,
                    input_data=input_data,
                    output_data=output_data,
                    usage=usage,
                    metadata=metadata or {},
                )
                logger.debug(
                    f"[TraceContext] Created generation: {getattr(gen_obj, 'id', '?')} ({name}) "
                    f"parent={current_parent_id} trace={current_trace_id}"
                )
            except Exception as e:
                logger.warning(f"[TraceContext] Failed to create generation: {e}")

        try:
            yield gen_obj
        finally:
            if gen_obj:
                try:
                    gen_obj.end()
                except Exception as e:
                    logger.warning(f"[TraceContext] Failed to end generation: {e}")
