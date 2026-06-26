import time
from typing import AsyncIterator

from app.adapters.llm.base import BaseLLMAdapter, LLMConfig, LLMResponse


class MockLLMAdapter(BaseLLMAdapter):
    """Mock adapter for development. No real API calls."""

    async def chat(self, messages: list[dict], config: LLMConfig) -> LLMResponse:
        user_msg = messages[-1]["content"] if messages else ""
        return LLMResponse(
            content=f"[Mock] 你说了: {user_msg}\n当前模型: {config.model}",
            model=config.model,
            provider="mock",
            usage={"prompt_tokens": len(user_msg), "completion_tokens": 30},
            latency=0.1,
        )

    async def chat_stream(
        self, messages: list[dict], config: LLMConfig
    ) -> AsyncIterator[str]:
        user_msg = messages[-1]["content"] if messages else ""
        response = f"[Mock] 你说了: {user_msg}\n当前模型: {config.model}"
        for char in response:
            yield char
            # Simulate streaming delay
            time.sleep(0.02)

    async def check_health(self, config: LLMConfig) -> bool:
        return True
