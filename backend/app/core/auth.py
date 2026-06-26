"""API Key 认证中间件

- REST API：验证 X-API-Key header
- WebSocket：验证 token 查询参数
- 未配置 API_KEY 时跳过认证（开发模式）
"""

import logging
from typing import Callable

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.websockets import WebSocket, WebSocketClose

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 不需要认证的路径前缀
_SKIP_AUTH_PREFIXES: tuple[str, ...] = (
    "/api/v1/health",
    "/api/v1/router/provider/",  # 获取 LLM provider 列表
    "/docs",
    "/openapi.json",
    "/redoc",
)

# 需要认证但 token 在查询参数中的路径前缀
_WS_PREFIXES: tuple[str, ...] = ("/ws/",)

_AUTH_HEADER = "x-api-key"
_WS_TOKEN_PARAM = "token"


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """验证 API Key 的中间件。

    规则：
    1. 未配置 API_KEY → 跳过所有验证（开发模式）
    2. REST API：从 X-API-Key header 获取
    3. WebSocket：从 ?token= 查询参数获取
    4. 健康检查 /docs 等路径跳过
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # 开发模式 — 跳过认证
        settings = get_settings()
        if not settings.API_KEY:
            return await call_next(request)

        path = request.url.path

        # 跳过的路径
        for prefix in _SKIP_AUTH_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # WebSocket 升级请求 (HTTP 层面处理)
        if path.startswith(_WS_PREFIXES):
            token = request.query_params.get(_WS_TOKEN_PARAM) or request.headers.get(_AUTH_HEADER)
        else:
            token = request.headers.get(_AUTH_HEADER)

        if not token or token != settings.API_KEY:
            logger.warning(
                "Auth failed for %s from %s (valid=%s)",
                path, request.client.host if request.client else "?",
                token is not None,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)


async def verify_ws_auth(websocket: WebSocket, api_key: str | None = None) -> bool:
    """在 WebSocket accept 后手动验证认证。

    WebSocket 通过 HTTP 中间件的 query param 验证（见 dispatch 中的 _WS_PREFIXES 处理）。
    此函数用于 accept 后再次确认，或用于直接在 ws 端点内调用。

    Returns:
        True 如果认证通过或未配置 API_KEY
    """
    settings = get_settings()
    if not settings.API_KEY:
        return True

    # WebSocket 的 token 在查询参数中（URL 形式 ws://host/ws/...?token=xxx）
    token_from_params = websocket.query_params.get(_WS_TOKEN_PARAM)
    token_from_headers = websocket.headers.get(_AUTH_HEADER)

    token = token_from_params or token_from_headers
    if not token or token != settings.API_KEY:
        logger.warning(
            "WS auth failed for %s from %s",
            websocket.url.path,
            websocket.client.host if websocket.client else "?",
        )
        return False

    return True
