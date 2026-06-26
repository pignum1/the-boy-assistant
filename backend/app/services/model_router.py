"""Model Router：按任务复杂度自动选择最合适的模型"""

import logging
import uuid
from enum import Enum
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model

logger = logging.getLogger(__name__)


def _mask_key(key: str) -> str:
    """Mask API key ref for safe display"""
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


class TaskComplexity(str, Enum):
    SIMPLE = "simple"      # 简单问答、翻译、格式转换
    STANDARD = "standard"  # 常规对话、分析、总结
    COMPLEX = "complex"    # 代码生成、架构设计、多步推理


# 复杂度分类关键词
COMPLEXITY_KEYWORDS = {
    TaskComplexity.SIMPLE: [
        "翻译", "translate", "格式化", "format", "简述", "briefly",
        "定义", "define", "列举", "list", "是什么", "what is",
        "你好", "hello", "谢谢", "thanks", "再见",
    ],
    TaskComplexity.COMPLEX: [
        "架构", "architecture", "设计", "design", "重构", "refactor",
        "实现", "implement", "优化", "optimize", "调试", "debug",
        "代码", "code", "算法", "algorithm", "分析", "analyze",
        "比较", "compare", "评估", "evaluate", "方案", "solution",
        "多步", "step by step", "推理", "reasoning",
        "编写", "write", "生成", "generate", "创建", "create",
    ],
}


class ModelRouter:
    """模型路由器：根据任务复杂度选择最合适的模型"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def classify_complexity(
        self,
        message: str,
        history: Optional[list[dict]] = None,
    ) -> TaskComplexity:
        """分类任务复杂度（基于关键词匹配 + 历史长度）"""
        msg_lower = message.lower()

        simple_score = sum(1 for kw in COMPLEXITY_KEYWORDS[TaskComplexity.SIMPLE] if kw in msg_lower)
        complex_score = sum(1 for kw in COMPLEXITY_KEYWORDS[TaskComplexity.COMPLEX] if kw in msg_lower)

        # 历史长度影响：长对话提升复杂度
        history_factor = 0
        if history:
            history_factor = min(len(history) // 4, 2)

        # 消息长度影响：超长消息提升复杂度
        length_factor = 1 if len(message) > 200 else 0

        total_complex = complex_score + history_factor + length_factor
        total_simple = simple_score

        if total_complex >= 2:
            return TaskComplexity.COMPLEX
        elif total_simple >= 1 and total_complex == 0:
            return TaskComplexity.SIMPLE
        else:
            return TaskComplexity.STANDARD

    async def select_model(
        self,
        complexity: TaskComplexity,
        default_model_id: uuid.UUID,
    ) -> Model:
        """根据复杂度选择模型

        策略：
        - SIMPLE: 优先选轻量模型（如 deepseek-chat）
        - STANDARD: 使用 Agent 默认模型
        - COMPLEX: 优先选强力模型（如 deepseek-reasoner）
        """
        # 加载默认模型
        default_model = await self.db.get(Model, default_model_id)
        if not default_model:
            raise ValueError(f"Model {default_model_id} not found")

        # 尝试找对应复杂度的模型
        target_capability = {
            TaskComplexity.SIMPLE: "lightweight",
            TaskComplexity.STANDARD: None,  # 使用默认
            TaskComplexity.COMPLEX: "reasoning",
        }

        capability = target_capability[complexity]
        if capability is None:
            return default_model

        # 查找具有目标能力的活跃模型
        result = await self.db.execute(
            select(Model)
            .where(Model.is_active == True)
            .where(Model.provider == default_model.provider)
            .order_by(Model.context_window.desc())
        )
        models = list(result.scalars().all())

        for m in models:
            if m.capabilities and capability in m.capabilities:
                logger.info(f"ModelRouter: {complexity.value} -> {m.model_name} ({capability})")
                return m

        # Fallback: 复杂任务选上下文窗口最大的，简单任务选最小的
        if complexity == TaskComplexity.COMPLEX and models:
            best = max(models, key=lambda m: m.context_window)
            if best.id != default_model_id:
                logger.info(f"ModelRouter: {complexity.value} -> {best.model_name} (largest context)")
                return best

        if complexity == TaskComplexity.SIMPLE and models:
            smallest = min(models, key=lambda m: m.context_window)
            if smallest.id != default_model_id:
                logger.info(f"ModelRouter: {complexity.value} -> {smallest.model_name} (smallest context)")
                return smallest

        logger.info(f"ModelRouter: {complexity.value} -> {default_model.model_name} (default)")
        return default_model

    async def list_models(self) -> list[dict]:
        """列出所有活跃模型，带 agent_count 统计"""
        from app.models.agent import Agent

        result = await self.db.execute(
            select(Model).where(Model.is_active == True).order_by(Model.provider, Model.model_name)
        )
        models = list(result.scalars().all())

        # 统计每个 model 关联的 agent 数量
        output = []
        for m in models:
            agent_result = await self.db.execute(
                select(Agent).where(Agent.default_model_id == m.id)
            )
            agent_count = len(list(agent_result.scalars().all()))

            output.append({
                "id": m.id,
                "name": m.display_name or m.model_name,
                "provider": m.provider,
                "model_name": m.model_name,
                "context_window": m.context_window,
                "capabilities": m.capabilities,
                "status": "online" if m.is_active else "offline",
                "api_key_masked": _mask_key(m.api_key_ref) if m.api_key_ref else None,
                "agent_count": agent_count,
                "rpm_limit": m.rpm_limit,
                "tpm_limit": m.tpm_limit,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            })
        return output

    async def route_and_call(
        self,
        message: str,
        default_model_id: uuid.UUID,
        messages: list[dict],
        config_override: Optional[dict] = None,
        mock: bool = False,
    ) -> dict:
        """完整的路由+调用流程

        Returns:
            {"complexity": str, "model": Model, "response": LLMResponse}
        """
        from app.adapters.llm.base import LLMConfig
        from app.adapters.llm.litellm_adapter import LiteLLMAdapter
        from app.adapters.llm.mock_adapter import MockLLMAdapter
        from app.core.security import decrypt_api_key
        from app.core.config import get_settings

        async def _resolve_api_key(db, model):
            """内联 API Key 解析（避免跨域依赖 agent_factory）"""
            if model.api_key_ref:
                try:
                    return decrypt_api_key(model.api_key_ref)
                except Exception:
                    pass
            settings = get_settings()
            env_map = {
                "openai": settings.OPENAI_API_KEY,
                "anthropic": settings.CLAUDE_API_KEY,
                "google": settings.GEMINI_API_KEY,
                "zhipu": settings.GLM_API_KEY,
                "deepseek": settings.DEEPSEEK_API_KEY,
            }
            return env_map.get(model.provider, "")

        # 1. 分类复杂度
        complexity = await self.classify_complexity(message)
        logger.info(f"Task complexity classified as: {complexity.value}")

        # 2. 选择模型
        model = await self.select_model(complexity, default_model_id)

        # 3. 构建配置
        if mock:
            adapter = MockLLMAdapter()
            api_key = "mock"
        else:
            adapter = LiteLLMAdapter()
            api_key = await _resolve_api_key(self.db, model)

        config = LLMConfig(
            model=model.model_name,
            provider=model.provider,
            api_key=api_key,
        )
        if config_override:
            for k, v in config_override.items():
                if hasattr(config, k):
                    setattr(config, k, v)

        # 4. 调用 LLM
        response = await adapter.chat(messages=messages, config=config)

        return {
            "complexity": complexity.value,
            "model": model,
            "response": response,
        }


# ── Seed Data ──────────────────────────────────────────────

PRESET_MODELS = [
    # ── OpenAI ──
    {
        "provider": "openai",
        "model_name": "gpt-4.1",
        "display_name": "GPT-4.1",
        "capabilities": ["reasoning", "complex", "code", "analysis"],
        "context_window": 1000000,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "display_name": "GPT-4.1 Mini",
        "capabilities": ["lightweight", "chat", "code"],
        "context_window": 1000000,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4.1-nano",
        "display_name": "GPT-4.1 Nano",
        "capabilities": ["lightweight", "chat"],
        "context_window": 1000000,
    },
    {
        "provider": "openai",
        "model_name": "o4-mini",
        "display_name": "o4 Mini (推理)",
        "capabilities": ["reasoning", "complex", "code"],
        "context_window": 200000,
    },
    # ── Anthropic ──
    {
        "provider": "anthropic",
        "model_name": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "capabilities": ["reasoning", "complex", "code", "analysis"],
        "context_window": 200000,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4-6",
        "display_name": "Claude Sonnet 4.6",
        "capabilities": ["chat", "code", "analysis"],
        "context_window": 200000,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "capabilities": ["lightweight", "chat"],
        "context_window": 200000,
    },
    # ── Google ──
    {
        "provider": "google",
        "model_name": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "capabilities": ["reasoning", "complex", "code", "analysis"],
        "context_window": 1000000,
    },
    {
        "provider": "google",
        "model_name": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "capabilities": ["lightweight", "chat", "code"],
        "context_window": 1000000,
    },
    # ── DeepSeek ──
    {
        "provider": "deepseek",
        "model_name": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "capabilities": ["chat", "code", "analysis"],
        "context_window": 128000,
    },
    {
        "provider": "deepseek",
        "model_name": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "capabilities": ["lightweight", "chat", "code"],
        "context_window": 128000,
    },
    # ── Meta ──
    {
        "provider": "meta",
        "model_name": "llama-4-maverick",
        "display_name": "Llama 4 Maverick",
        "capabilities": ["chat", "code", "analysis"],
        "context_window": 128000,
    },
    {
        "provider": "meta",
        "model_name": "llama-4-scout",
        "display_name": "Llama 4 Scout",
        "capabilities": ["lightweight", "chat"],
        "context_window": 128000,
    },
    # ── 智谱 ──
    {
        "provider": "zhipu",
        "model_name": "glm-5.1",
        "display_name": "GLM-5.1",
        "capabilities": ["reasoning", "complex", "code", "analysis"],
        "context_window": 128000,
    },
    {
        "provider": "zhipu",
        "model_name": "glm-5.1-flash",
        "display_name": "GLM-5.1 Flash",
        "capabilities": ["lightweight", "chat", "code"],
        "context_window": 128000,
    },
    # ── Mistral ──
    {
        "provider": "mistral",
        "model_name": "mistral-large-2",
        "display_name": "Mistral Large 2",
        "capabilities": ["chat", "code", "analysis"],
        "context_window": 128000,
    },
    # ── xAI ──
    {
        "provider": "xai",
        "model_name": "grok-3",
        "display_name": "Grok-3",
        "capabilities": ["reasoning", "complex", "code", "analysis"],
        "context_window": 128000,
    },
]


async def seed_preset_models(db) -> None:
    """Seed preset models with capabilities for routing"""
    for preset in PRESET_MODELS:
        result = await db.execute(
            select(Model).where(
                Model.provider == preset["provider"],
                Model.model_name == preset["model_name"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            model = Model(**preset)
            db.add(model)
        else:
            # Update capabilities if model exists
            if not existing.capabilities:
                existing.capabilities = preset.get("capabilities")
    await db.commit()
