"""Observer DTOs"""

from pydantic import BaseModel


class TokenUsageResponse(BaseModel):
    total_calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    by_model: dict = {}


class TraceTreeResponse(BaseModel):
    trace_id: str
    task_id: str
    status: str
    total_spans: int
    root: dict = {}
