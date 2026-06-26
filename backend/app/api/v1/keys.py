import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_api_key, decrypt_api_key, mask_api_key
from app.core.config import get_settings
from app.models.model import Model
from app.adapters.llm.base import LLMConfig
from app.adapters.llm.litellm_adapter import LiteLLMAdapter
from app.adapters.llm.mock_adapter import MockLLMAdapter

logger = logging.getLogger(__name__)
router = APIRouter()

# Provider -> env var key mapping
PROVIDER_ENV_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "CLAUDE_API_KEY",
    "google": "GEMINI_API_KEY",
    "zhipu": "GLM_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "meta": "META_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
}


@router.get("/keys/status")
async def get_key_status(db: AsyncSession = Depends(get_db)):
    """Check which providers have API keys configured"""
    settings = get_settings()
    results = []
    for provider, env_key in PROVIDER_ENV_MAP.items():
        key = getattr(settings, env_key.replace("_API_KEY", "") + "_API_KEY", "")
        # Also check database
        result = await db.execute(
            select(Model).where(Model.provider == provider, Model.is_active == True)
        )
        models = list(result.scalars().all())
        results.append({
            "provider": provider,
            "env_configured": bool(key),
            "masked_key": mask_api_key(key) if key else None,
            "models_count": len(models),
        })
    return results


@router.post("/models/{model_id}/test")
async def test_model_connectivity(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Test connectivity for a specific model"""
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Resolve API key: try database ref first, then env
    api_key = ""
    if model.api_key_ref:
        try:
            api_key = decrypt_api_key(model.api_key_ref)
        except Exception:
            logger.warning(f"Failed to decrypt API key for model {model.id}")

    if not api_key:
        env_key = PROVIDER_ENV_MAP.get(model.provider, "")
        if env_key:
            settings = get_settings()
            api_key = getattr(settings, env_key.replace("_API_KEY", "") + "_API_KEY", "")

    if not api_key:
        return {
            "model_id": str(model.id),
            "provider": model.provider,
            "model_name": model.model_name,
            "connected": False,
            "error": "No API key configured",
        }

    config = LLMConfig(
        model=model.model_name,
        provider=model.provider,
        api_key=api_key,
    )

    adapter = LiteLLMAdapter()
    connected = await adapter.check_health(config)

    return {
        "model_id": str(model.id),
        "provider": model.provider,
        "model_name": model.model_name,
        "connected": connected,
    }
