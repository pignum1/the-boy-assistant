"""Observer FastAPI 中间件：为 HTTP 请求自动注入 trace_id"""

import logging
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class TraceMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求自动创建 trace_id 并注入到请求状态"""

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
