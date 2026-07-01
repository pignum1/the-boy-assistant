"""LangFuse 可观测性客户端 — 全局单例 (SDK v4.x)

用法:
    from app.services.langfuse_client import get_langfuse_client

    client = get_langfuse_client()
    if client:
        tid = client.create_trace_id()
        obs = client.start_observation(
            trace_context={"trace_id": tid},
            name="my-span",
            as_type="span",
        )
        ...

配置（.env）:
    LANGFUSE_HOST=http://localhost:3000
    LANGFUSE_PUBLIC_KEY=pk-...
    LANGFUSE_SECRET_KEY=sk-...

不配置时返回 None，调用方检查 None 跳过追踪。
"""
from functools import lru_cache
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 惰性导入 langfuse，未安装时优雅降级
_Langfuse = None


def _get_langfuse_class():
    """惰性加载 Langfuse 类，未安装时返回 None。"""
    global _Langfuse
    if _Langfuse is None:
        try:
            from langfuse import Langfuse as _LF
            _Langfuse = _LF
        except ImportError:
            logger.warning(
                "langfuse package not installed. "
                "Install with: pip install langfuse"
            )
            _Langfuse = False  # sentinel: tried but failed
    return _Langfuse if _Langfuse is not False else None


@lru_cache(maxsize=1)
def get_langfuse_client():
    """获取 LangFuse 客户端单例。未配置或未安装时返回 None。"""
    settings = get_settings()

    if not settings.LANGFUSE_HOST:
        return None

    LF = _get_langfuse_class()
    if LF is None:
        return None

    logger.info(f"LangFuse connected: {settings.LANGFUSE_HOST}")
    return LF(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
    )


# ── Helpers for LangFuse v4.x SDK ──

def create_trace_id():
    """Create a new trace ID (returns str)."""
    client = get_langfuse_client()
    if client:
        return client.create_trace_id()
    return ""


def start_observation(
    trace_id: str,
    name: str,
    as_type: str = "span",
    parent_observation_id: str = "",
    input_data=None,
    output_data=None,
    metadata: Optional[dict] = None,
    model: str = "",
    usage: Optional[dict] = None,
):
    """Start a LangFuse observation (trace root, span, or generation).

    Args:
        trace_id: trace ID (from create_trace_id())
        name: observation name
        as_type: "span" or "generation"
        parent_observation_id: parent observation ID for nesting
        input_data: input data
        output_data: output data
        metadata: custom metadata dict
        model: model name (for generations)
        usage: usage dict {"input": tokens, "output": tokens}
    """
    client = get_langfuse_client()
    if not client or not trace_id:
        return None

    trace_context = {"trace_id": trace_id}
    if parent_observation_id:
        trace_context["parent_observation_id"] = parent_observation_id

    kwargs = {
        "trace_context": trace_context,
        "name": name,
        "as_type": as_type,
    }
    if input_data is not None:
        kwargs["input"] = input_data
    if output_data is not None:
        kwargs["output"] = output_data
    if metadata:
        kwargs["metadata"] = metadata
    if model:
        kwargs["model"] = model
    if usage:
        kwargs["usage_details"] = usage

    try:
        return client.start_observation(**kwargs)
    except Exception as e:
        logger.warning(f"LangFuse start_observation failed: {e}")
        return None


def start_as_current_observation(
    name: str,
    as_type: str = "span",
    input_data=None,
    output_data=None,
    metadata: Optional[dict] = None,
    model: str = "",
    usage: Optional[dict] = None,
):
    """Start a trace observation as the current context (for propagate_attributes)."""
    client = get_langfuse_client()
    if not client:
        return None

    kwargs = {"name": name, "as_type": as_type}
    if input_data is not None:
        kwargs["input"] = input_data
    if output_data is not None:
        kwargs["output"] = output_data
    if metadata:
        kwargs["metadata"] = metadata
    if model:
        kwargs["model"] = model
    if usage:
        kwargs["usage_details"] = usage

    try:
        return client.start_as_current_observation(**kwargs)
    except Exception as e:
        logger.warning(f"LangFuse start_as_current_observation failed: {e}")
        return None


def propagate_attributes(session_id: str = "", user_id: str = "", metadata: Optional[dict] = None):
    """Propagate trace-level attributes (session_id, user_id) to all child spans."""
    client = get_langfuse_client()
    if not client:
        from contextlib import nullcontext
        return nullcontext()

    try:
        from langfuse._client.propagation import propagate_attributes as _pa
        kwargs = {}
        if session_id:
            kwargs["session_id"] = session_id
        if user_id:
            kwargs["user_id"] = user_id
        if metadata:
            kwargs["metadata"] = metadata
        return _pa(**kwargs)
    except Exception as e:
        logger.warning(f"LangFuse propagate_attributes failed: {e}")
        from contextlib import nullcontext
        return nullcontext()


def create_score(
    trace_id: str,
    name: str,
    value: float,
    observation_id: str = "",
    comment: str = "",
    data_type: str = "NUMERIC",
):
    """Create a score for a trace."""
    client = get_langfuse_client()
    if not client or not trace_id:
        return

    kwargs = {
        "trace_id": trace_id,
        "name": name,
        "value": value,
        "comment": comment,
        "data_type": data_type,
    }
    if observation_id:
        kwargs["observation_id"] = observation_id

    try:
        client.create_score(**kwargs)
    except Exception as e:
        logger.warning(f"LangFuse create_score failed: {e}")
