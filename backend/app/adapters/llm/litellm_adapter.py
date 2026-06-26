import asyncio
import logging
import time
from typing import AsyncIterator, Optional

import litellm
from litellm import acompletion

from app.adapters.llm.base import BaseLLMAdapter, LLMConfig, LLMResponse
from app.adapters.llm.rate_limiter import TokenBucket

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


class AuthError(Exception):
    pass


class TimeoutError(Exception):
    pass


class ServerError(Exception):
    pass


def _classify_error(e: Exception) -> Exception:
    """Classify LLM API errors into typed exceptions"""
    msg = str(e).lower()
    if "rate" in msg or "429" in msg:
        return RateLimitError(str(e))
    if "auth" in msg or "401" in msg or "403" in msg or "api_key" in msg:
        return AuthError(str(e))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(str(e))
    if "500" in msg or "502" in msg or "503" in msg:
        return ServerError(str(e))
    return e


class LiteLLMAdapter(BaseLLMAdapter):
    def __init__(self, fallback_models: Optional[list[tuple[str, str, str]]] = None):
        """
        Args:
            fallback_models: list of (provider, model, api_key) tuples for fallback chain
        """
        litellm.drop_params = True
        self.fallback_models = fallback_models or []
        self._rate_limiters: dict[str, TokenBucket] = {}

    def _get_limiter(self, model_key: str) -> TokenBucket:
        if model_key not in self._rate_limiters:
            self._rate_limiters[model_key] = TokenBucket()
        return self._rate_limiters[model_key]

    # Provider -> (LiteLLM model prefix, api_base or None)
    PROVIDER_MAP = {
        "openai": ("", None),
        "anthropic": ("anthropic/", None),
        "google": ("gemini/", None),
        "zhipu": ("openai/", "https://open.bigmodel.cn/api/paas/v4"),
        "deepseek": ("openai/", "https://api.deepseek.com"),
    }

    def _build_model_str(self, provider: str, model: str) -> str:
        """Map provider to LiteLLM model string"""
        prefix, _ = self.PROVIDER_MAP.get(provider, (f"{provider}/", None))
        return f"{prefix}{model}"

    def _get_api_base(self, provider: str) -> Optional[str]:
        """Get custom API base URL for provider"""
        _, api_base = self.PROVIDER_MAP.get(provider, (None, None))
        return api_base

    async def _call_with_retry(
        self,
        messages: list[dict],
        config: LLMConfig,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Call with exponential backoff retry"""
        limiter = self._get_limiter(f"{config.provider}/{config.model}")

        for attempt in range(max_retries + 1):
            try:
                await limiter.acquire()
                start = time.time()

                kwargs = dict(
                    model=self._build_model_str(config.provider, config.model),
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    api_key=config.api_key,
                    timeout=config.timeout if config.timeout else 120,
                )
                api_base = self._get_api_base(config.provider)
                if api_base:
                    kwargs["api_base"] = api_base

                # 传递原生 function calling tools
                if config.tools:
                    kwargs["tools"] = config.tools
                    kwargs["tool_choice"] = "auto"

                # 为 Zhipu GLM 模型启用思考模式
                if config.provider == "zhipu":
                    kwargs["thinking"] = {"type": "enabled"}

                response = await acompletion(**kwargs)

                latency = time.time() - start
                usage = {}
                if hasattr(response, "usage") and response.usage:
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                    }

                # 提取思考内容（支持多种模型的思考过程返回）
                message = response.choices[0].message
                content = message.content or ""

                # 提取原生 function calling tool_calls
                tool_calls = []
                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tc in message.tool_calls:
                        try:
                            tool_calls.append({
                                "name": tc.function.name if hasattr(tc, 'function') else tc.get('function', {}).get('name', ''),
                                "arguments": tc.function.arguments if hasattr(tc, 'function') else tc.get('function', {}).get('arguments', '{}'),
                            })
                        except Exception:
                            pass
                    logger.info(f"🔧 Native tool_calls received: {[t['name'] for t in tool_calls]}")

                # 尝试获取思考内容（支持多种模型的不同字段名）
                thinking_content = None

                # 首先检查原始响应中的 _hidden_params 或其他隐藏字段
                if hasattr(response, '_hidden_params'):
                    hidden = response._hidden_params
                    if hidden and isinstance(hidden, dict):
                        logger.debug(f"🔍 Hidden params: {list(hidden.keys())}")

                # 检查 message 对象的原始属性
                if hasattr(message, '__dict__'):
                    msg_dict = message.__dict__
                    logger.debug(f"🔍 Message dict keys: {list(msg_dict.keys())}")
                    # 检查是否有额外的属性
                    for key, val in msg_dict.items():
                        if 'reasoning' in key.lower() or 'thinking' in key.lower() or 'thought' in key.lower():
                            logger.debug(f"🔍 Found potential thinking field: {key} = {val}")

                # 尝试各种可能的字段名
                if hasattr(message, "thinking"):
                    thinking_content = message.thinking
                    logger.debug(f"🧠 Found thinking in message.thinking: {len(str(thinking_content))} chars")
                elif hasattr(message, "reasoning_content"):
                    # Zhipu GLM 系列使用 reasoning_content 字段
                    thinking_content = message.reasoning_content
                    logger.debug(f"🧠 Found thinking in message.reasoning_content: {len(str(thinking_content))} chars")
                elif hasattr(message, "thoughts"):
                    thinking_content = message.thoughts
                    logger.debug(f"🧠 Found thinking in message.thoughts: {len(str(thinking_content))} chars")
                elif hasattr(response, "thinking"):
                    thinking_content = response.thinking
                    logger.debug(f"🧠 Found thinking in response.thinking: {len(str(thinking_content))} chars")
                elif hasattr(response, "reasoning_content"):
                    thinking_content = response.reasoning_content
                    logger.debug(f"🧠 Found thinking in response.reasoning_content: {len(str(thinking_content))} chars")
                # 检查 content 中是否包含 <thinking> 标签（某些模型返回在 content 中）
                elif "<thinking>" in content and "</thinking>" in content:
                    import re
                    match = re.search(r"<thinking>(.*?)</thinking>", content, re.DOTALL)
                    if match:
                        thinking_content = match.group(1).strip()
                        logger.debug(f"🧠 Found thinking in <thinking> tags: {len(thinking_content)} chars")
                        # 从最终内容中移除 thinking 标签
                        content = re.sub(r"<thinking>.*?</thinking>\s*", "", content, flags=re.DOTALL)

                # 打印调试信息：查看 message 对象的所有属性
                if config.provider == "zhipu":
                    if thinking_content:
                        logger.info(f"✅ Zhipu thinking content found ({len(str(thinking_content))} chars): {str(thinking_content)[:200]}...")
                    else:
                        logger.debug(f"🔍 Zhipu message attributes: {[a for a in dir(message) if not a.startswith('_')]}")
                        # 检查各个可能的 thinking 字段
                        for attr in ['thinking', 'reasoning_content', 'thoughts']:
                            if hasattr(message, attr):
                                val = getattr(message, attr)
                                logger.debug(f"🔍 message.{attr} = {val}")
                        logger.debug(f"🔍 Response choices: {len(response.choices) if hasattr(response, 'choices') else 0}")
                        if hasattr(response, 'choices') and response.choices:
                            logger.debug(f"🔍 First choice: {response.choices[0]}")

                # 记录 thinking 内容提取结果
                if thinking_content:
                    logger.info(f"✅ Extracted {len(str(thinking_content))} chars of thinking content for {config.provider}/{config.model}")
                else:
                    logger.info(f"⚠ No thinking content found for {config.provider}/{config.model} (checked: message.thinking, message.reasoning_content, response.thinking, response.reasoning_content, <thinking> tags)")

                return LLMResponse(
                    content=content,
                    thinking=thinking_content,
                    model=response.model or config.model,
                    provider=config.provider,
                    usage=usage,
                    latency=latency,
                    tool_calls=tool_calls,
                )

            except Exception as e:
                classified = _classify_error(e)
                if attempt < max_retries and not isinstance(classified, AuthError):
                    wait = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {wait}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise classified from e

        raise ServerError("Max retries exceeded")

    async def chat(self, messages: list[dict], config: LLMConfig) -> LLMResponse:
        """Non-streaming call with retry and fallback"""
        try:
            response = await self._call_with_retry(messages, config)
            # Observer: 自动记录 token usage
            self._record_usage(response)
            return response
        except Exception as primary_error:
            if not self.fallback_models:
                raise

            logger.warning(f"Primary model failed, trying fallbacks: {primary_error}")
            for provider, model, api_key in self.fallback_models:
                try:
                    fallback_config = LLMConfig(
                        model=model,
                        provider=provider,
                        api_key=api_key,
                        temperature=config.temperature,
                        max_tokens=config.max_tokens,
                    )
                    response = await self._call_with_retry(messages, fallback_config, max_retries=1)
                    self._record_usage(response)
                    return response
                except Exception as fb_error:
                    logger.warning(f"Fallback {provider}/{model} also failed: {fb_error}")
                    continue

            raise primary_error

    async def chat_stream(
        self, messages: list[dict], config: LLMConfig
    ) -> AsyncIterator[str]:
        """Streaming call"""
        kwargs = dict(
            model=self._build_model_str(config.provider, config.model),
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
            stream=True,
            timeout=config.timeout,
        )
        api_base = self._get_api_base(config.provider)
        if api_base:
            kwargs["api_base"] = api_base

        response = await acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def check_health(self, config: LLMConfig) -> bool:
        """Test connectivity"""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                config=LLMConfig(
                    model=config.model,
                    provider=config.provider,
                    api_key=config.api_key,
                    max_tokens=5,
                ),
            )
            return True
        except Exception as e:
            logger.warning(f"Health check failed for {config.provider}/{config.model}: {e}")
            return False

    @staticmethod
    def _record_usage(response: LLMResponse) -> None:
        """Observer: 记录 token 使用到 TokenTracker"""
        try:
            from app.services.observer import token_tracker
            usage = response.usage or {}
            if usage.get("total_tokens", 0) > 0:
                token_tracker.record(
                    trace_id="",
                    span_id="",
                    model=response.model,
                    provider=response.provider,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
        except Exception:
            pass  # Observer 记录失败不影响 LLM 调用
