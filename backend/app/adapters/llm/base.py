from abc import ABC, abstractmethod
from typing import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    model: str
    provider: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 16384
    timeout: int = 120  # seconds (DeepSeek can take 90s+)
    tools: list[dict] = field(default_factory=list)  # OpenAI function calling format


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict = field(default_factory=dict)
    latency: float = 0.0
    thinking: str = None  # 模型的思考内容（如 Claude extended thinking）
    tool_calls: list[dict] = field(default_factory=list)  # [{name, arguments: {}}]


class BaseLLMAdapter(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], config: LLMConfig) -> LLMResponse:
        """Non-streaming call"""
        pass

    @abstractmethod
    async def chat_stream(self, messages: list[dict], config: LLMConfig) -> AsyncIterator[str]:
        """Streaming call, yields chunks"""
        pass

    @abstractmethod
    async def check_health(self, config: LLMConfig) -> bool:
        """Test API connectivity"""
        pass
