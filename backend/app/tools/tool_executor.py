import logging
from typing import Optional

from app.tools.base import BaseTool, ToolResult
from app.tools.file_ops import FileOpsTool
from app.tools.terminal import TerminalTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Routes tool calls to the correct tool implementation."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        # Register built-in tools
        self.register(FileOpsTool())
        self.register(TerminalTool())

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_available(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(
        self,
        tool_name: str,
        params: dict,
        session_id: Optional[str] = None,
    ) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        # Validate params
        valid, error = tool.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=error)

        logger.info(f"Executing tool: {tool_name} with params: {list(params.keys())}")
        try:
            result = await tool.execute(params, session_id)
            logger.info(f"Tool {tool_name} completed: success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(success=False, error=str(e))


# Global tool executor
tool_executor = ToolExecutor()
