"""Fallback Chain：模型调用失败时自动切换到备用模型"""

import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from app.adapters.llm.base import LLMConfig, LLMResponse
from app.adapters.llm.litellm_adapter import LiteLLMAdapter
from app.services.agent_factory import resolve_api_key

logger = logging.getLogger(__name__)


class CircuitState:
    """熔断器状态：记录模型失败次数，达到阈值后暂时停用"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 300.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = {}      # model_id -> failure count
        self._open_until: dict[str, float] = {}   # model_id -> timestamp

    def record_failure(self, model_id: str) -> None:
        self._failures[model_id] = self._failures.get(model_id, 0) + 1
        if self._failures[model_id] >= self.failure_threshold:
            self._open_until[model_id] = time.time() + self.recovery_timeout
            logger.warning(f"Circuit OPEN for model {model_id}, recovery at {self._open_until[model_id]}")

    def record_success(self, model_id: str) -> None:
        self._failures.pop(model_id, None)
        self._open_until.pop(model_id, None)

    def is_available(self, model_id: str) -> bool:
        if model_id not in self._open_until:
            return True
        if time.time() >= self._open_until[model_id]:
            # Recovery: half-open state
            self._open_until.pop(model_id, None)
            self._failures.pop(model_id, None)
            logger.info(f"Circuit RECOVERED for model {model_id}")
            return True
        return False


class FallbackChain:
    """模型降级链：主模型失败 → 自动尝试备用模型"""

    # 类级别共享熔断器（可选改用实例级别 _circuit 隔离 session）
    _shared_circuit = CircuitState()

    def __init__(self, db: AsyncSession, shared_circuit: bool = True):
        self.db = db
        self._circuit = self._shared_circuit if shared_circuit else CircuitState()



    async def get_fallback_models(
        self,
        primary_model: Model,
        exclude_ids: Optional[set[str]] = None,
    ) -> list[Model]:
        """获取备用模型列表（同 provider 优先，再跨 provider）"""
        exclude_ids = exclude_ids or set()

        # 同 provider 的其他活跃模型
        result = await self.db.execute(
            select(Model)
            .where(Model.is_active == True)
            .where(Model.id != primary_model.id)
            .order_by(Model.context_window.desc())
        )
        all_models = list(result.scalars().all())

        # 分组：同 provider 优先
        same_provider = [m for m in all_models if m.provider == primary_model.provider]
        cross_provider = [m for m in all_models if m.provider != primary_model.provider]

        candidates = same_provider + cross_provider

        # 过滤掉熔断的模型和已排除的
        available = [
            m for m in candidates
            if str(m.id) not in exclude_ids and self._circuit.is_available(str(m.id))
        ]

        return available

    async def call_with_fallback(
        self,
        messages: list[dict],
        primary_model: Model,
        api_key: str,
        max_fallbacks: int = 2,
        config_override: Optional[dict] = None,
    ) -> tuple[LLMResponse, dict]:
        """调用主模型，失败则按降级链尝试备用模型

        Returns:
            (response, routing_info)
        """
        routing_info = {
            "primary_model": primary_model.model_name,
            "primary_provider": primary_model.provider,
            "fallback_used": False,
            "attempts": [],
        }

        adapter = LiteLLMAdapter()
        primary_id = str(primary_model.id)

        # 尝试主模型
        attempt_info = {"model": primary_model.model_name, "provider": primary_model.provider}
        try:
            config = self._build_config(primary_model, api_key, config_override)
            response = await adapter.chat(messages=messages, config=config)
            self._circuit.record_success(primary_id)
            attempt_info["status"] = "success"
            routing_info["attempts"].append(attempt_info)
            return response, routing_info
        except Exception as e:
            self._circuit.record_failure(primary_id)
            attempt_info["status"] = "failed"
            attempt_info["error"] = str(e)[:200]
            routing_info["attempts"].append(attempt_info)
            logger.warning(f"Primary model {primary_model.model_name} failed: {e}")

        # 尝试备用模型
        fallbacks = await self.get_fallback_models(primary_model, exclude_ids={primary_id})
        tried = 0

        for fb_model in fallbacks:
            if tried >= max_fallbacks:
                break

            fb_id = str(fb_model.id)
            if not self._circuit.is_available(fb_id):
                continue

            attempt_info = {"model": fb_model.model_name, "provider": fb_model.provider}

            try:
                fb_api_key = await resolve_api_key(self.db, fb_model)
                config = self._build_config(fb_model, fb_api_key, config_override)
                response = await adapter.chat(messages=messages, config=config)
                self._circuit.record_success(fb_id)
                attempt_info["status"] = "success"
                routing_info["attempts"].append(attempt_info)
                routing_info["fallback_used"] = True
                routing_info["fallback_model"] = fb_model.model_name
                routing_info["fallback_provider"] = fb_model.provider
                logger.info(f"Fallback to {fb_model.model_name} succeeded")
                return response, routing_info
            except Exception as e:
                self._circuit.record_failure(fb_id)
                attempt_info["status"] = "failed"
                attempt_info["error"] = str(e)[:200]
                routing_info["attempts"].append(attempt_info)
                logger.warning(f"Fallback model {fb_model.model_name} also failed: {e}")
                tried += 1

        # 全部失败
        raise RuntimeError(
            f"All models failed. Attempts: {[a['model'] for a in routing_info['attempts']]}"
        )

    def _build_config(
        self,
        model: Model,
        api_key: str,
        override: Optional[dict] = None,
    ) -> LLMConfig:
        config = LLMConfig(
            model=model.model_name,
            provider=model.provider,
            api_key=api_key,
        )
        if override:
            for k, v in override.items():
                if hasattr(config, k):
                    setattr(config, k, v)
        return config
