"""速率限制中间件

基于滑动窗口的简易速率限制（内存模式，生产环境建议换 Redis）。
- REST API：按 IP + 路径前缀限制
- 未配置限制时跳过
"""

import logging
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 默认：每 IP 每分钟 60 次请求
_DEFAULT_RPM = 120
# 窗口大小（秒）
_WINDOW = 60

# 跳过的路径
_SKIP_PREFIXES = ("/api/v1/health", "/docs", "/openapi.json", "/redoc", "/ws/")


class SlidingWindowRateLimiter:
    """简易滑动窗口速率限制器（内存实现）。"""

    def __init__(self, max_requests: int = _DEFAULT_RPM, window_seconds: int = _WINDOW):
        self.max_requests = max_requests
        self.window = window_seconds
        # key → list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _clean(self, key: str, now: float) -> None:
        """移出窗口外的旧时间戳。key 无剩余时间戳时直接删除。"""
        cutoff = now - self.window
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if not self._requests[key]:
            del self._requests[key]

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        self._clean(key, now)
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        self._clean(key, time.time())
        return max(0, self.max_requests - len(self._requests[key]))


# 全局实例
_limiter = SlidingWindowRateLimiter()

# 每 IP 的最大请求体大小（字节）
_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB


class RateLimitMiddleware(BaseHTTPMiddleware):
    """请求速率限制 + 请求体大小限制。"""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        for prefix in _SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # ── 请求体大小检查 ──
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                cl = int(content_length)
                if cl > _MAX_BODY_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Request body too large ({cl} bytes). Max: {_MAX_BODY_SIZE} bytes",
                    )
            except ValueError:
                pass

        # ── 速率限制 ──
        client_ip = (
            request.client.host if request.client
            else request.headers.get("x-forwarded-for", "unknown")
        )
        # 按 IP + 路径前缀分组（如 /api/v1/agents、/api/v1/sessions）
        route_prefix = "/" + path.split("/")[1:4][0] if len(path.split("/")) >= 4 else path
        limit_key = f"{client_ip}:{route_prefix}"

        settings = get_settings()
        rpm = getattr(settings, "RATE_LIMIT_RPM", _DEFAULT_RPM)

        # 调整窗口上限
        if _limiter.max_requests != rpm:
            _limiter.max_requests = rpm

        if not _limiter.is_allowed(limit_key):
            remaining = _limiter.remaining(limit_key)
            logger.warning("Rate limit exceeded for %s (%s)", limit_key, route_prefix)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {_WINDOW}s. Remaining: {remaining}",
                headers={"Retry-After": str(_WINDOW)},
            )

        return await call_next(request)
