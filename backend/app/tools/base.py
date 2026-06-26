from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str = ""
    data: Optional[dict] = None


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict

    @abstractmethod
    async def execute(self, params: dict, session_id: Optional[str] = None) -> ToolResult:
        pass

    def validate_params(self, params: dict) -> tuple[bool, str]:
        """Validate required parameters. Returns (valid, error_message)"""
        required = self.parameters.get("required", [])
        for key in required:
            if key not in params:
                return False, f"Missing required parameter: {key}"
        return True, ""
