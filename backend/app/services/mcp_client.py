"""MCP Client Service：连接 MCP 服务器并发现工具"""
import logging
from typing import Optional

from app.models.mcp_server import MCPServer

logger = logging.getLogger(__name__)


class MCPClientService:
    """MCP 协议客户端：支持 sse / stdio / http 三种 transport"""

    async def connect_and_list_tools(self, server: MCPServer) -> list[dict]:
        """连接 MCP 服务器并返回工具列表 [{name, description, inputSchema}, ...]"""
        if server.transport == "stdio":
            return await self._list_tools_stdio(server)
        elif server.transport == "sse":
            return await self._list_tools_sse(server)
        elif server.transport == "http":
            return await self._list_tools_http(server)
        else:
            raise ValueError(f"Unsupported transport: {server.transport}")

    async def test_connection(self, server: MCPServer) -> bool:
        """测试能否连接到 MCP 服务器"""
        try:
            # 尝试连接并只做 list_tools（比完整同步轻量）
            tools = await self.connect_and_list_tools(server)
            return True
        except Exception as e:
            logger.warning(f"MCP connection test failed for {server.name}: {e}")
            return False

    # ── stdio transport ──

    async def _list_tools_stdio(self, server: MCPServer) -> list[dict]:
        import os

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise ImportError("mcp package required for stdio transport. Install with: pip install mcp")

        command = server.command
        if not command:
            raise ValueError("command is required for stdio transport")

        args: list[str] = list(server.args or [])
        env: dict[str, str] = {}
        if server.env:
            env = {k: str(v) for k, v in server.env.items()}
        # Merge with current env
        merged_env = os.environ.copy()
        merged_env.update(env)

        params = StdioServerParameters(command=command, args=args, env=merged_env)

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    })
                return tools

    # ── SSE transport ──

    async def _list_tools_sse(self, server: MCPServer) -> list[dict]:
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError:
            raise ImportError("mcp package required for SSE transport. Install with: pip install mcp")

        url = server.url
        if not url:
            raise ValueError("url is required for SSE transport")

        headers = {}
        if server.api_key_ref:
            headers["Authorization"] = f"Bearer {server.api_key_ref}"

        async with sse_client(url, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    })
                return tools

    # ── HTTP (Streamable) transport ──

    async def _list_tools_http(self, server: MCPServer) -> list[dict]:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            raise ImportError("mcp package required for HTTP transport. Install with: pip install mcp")

        url = server.url
        if not url:
            raise ValueError("url is required for HTTP transport")

        headers = {}
        if server.api_key_ref:
            headers["Authorization"] = f"Bearer {server.api_key_ref}"

        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    })
                return tools


# ── 模块级单例 ──

mcp_client = MCPClientService()
