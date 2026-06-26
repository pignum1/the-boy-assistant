import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.model import ModelCreate, ModelResponse, ModelUpdate
from app.models.model import Model
from sqlalchemy import select, func
from app.services.model_router import ModelRouter

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Provider default base URL ──

PROVIDER_DEFAULT_BASE_URL: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "meta": "https://api.llama-api.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
}


class FetchProviderModelsRequest(BaseModel):
    provider: str
    api_key: str
    base_url: str | None = None


def _model_to_response(model, agent_count: int = 0) -> dict:
    return {
        "id": model.id,
        "name": model.display_name or model.model_name,
        "provider": model.provider,
        "model_name": model.model_name,
        "context_window": model.context_window,
        "capabilities": model.capabilities,
        "status": "online" if model.is_active else "offline",
        "api_key_masked": _mask_key(model.api_key_ref) if model.api_key_ref else None,
        "agent_count": agent_count,
        "rpm_limit": model.rpm_limit,
        "tpm_limit": model.tpm_limit,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


@router.get("")
async def list_models(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Model.id)))).scalar() or 0
    result = await db.execute(
        select(Model).offset(skip).limit(limit).order_by(Model.created_at.desc())
    )
    return {"items": result.scalars().all(), "total": total}


@router.post("", response_model=ModelResponse, status_code=201)
async def create_model(data: ModelCreate, db: AsyncSession = Depends(get_db)):
    from app.models.model import Model
    from sqlalchemy.exc import IntegrityError

    model = Model(
        provider=data.provider,
        model_name=data.model_name,
        display_name=data.display_name,
        capabilities=data.capabilities,
        context_window=data.context_window,
        rpm_limit=data.rpm_limit,
        tpm_limit=data.tpm_limit,
        api_key_ref=data.api_key_ref,
    )
    db.add(model)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Model '{data.provider}/{data.model_name}' already exists",
        )
    await db.refresh(model)
    return _model_to_response(model)


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.models.model import Model
    from app.models.agent import Agent
    from sqlalchemy import select

    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    agent_result = await db.execute(
        select(Agent).where(Agent.default_model_id == model.id)
    )
    agent_count = len(list(agent_result.scalars().all()))
    return _model_to_response(model, agent_count)


@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.models.model import Model
    from sqlalchemy.exc import IntegrityError

    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        await db.delete(model)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: model is currently in use by one or more agents",
        )


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(model_id: uuid.UUID, data: ModelUpdate, db: AsyncSession = Depends(get_db)):
    from app.models.model import Model

    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(model, key, value)
    await db.commit()
    await db.refresh(model)
    return _model_to_response(model)


class _BulkUpdateProviderKeyRequest(BaseModel):
    provider: str
    api_key_ref: str


@router.put("/provider/key", status_code=200)
async def update_provider_key(req: _BulkUpdateProviderKeyRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update as sql_update
    from app.models.model import Model

    await db.execute(
        sql_update(Model)
        .where(Model.provider == req.provider)
        .values(api_key_ref=req.api_key_ref)
    )
    await db.commit()
    return {"provider": req.provider, "updated": True}


@router.get("/provider/{provider}/key")
async def get_provider_key(provider: str, db: AsyncSession = Depends(get_db)):
    """获取指定 provider 的实际 API Key 值（用于管理页面展示）"""
    from app.models.model import Model
    from sqlalchemy import select as sel

    result = await db.execute(
        sel(Model).where(Model.provider == provider, Model.api_key_ref.isnot(None)).limit(1)
    )
    model = result.scalar_one_or_none()
    if not model or not model.api_key_ref:
        raise HTTPException(status_code=404, detail="No key configured for this provider")
    return {"provider": provider, "api_key_masked": _mask_key(model.api_key_ref)}


@router.post("/fetch-provider-models")
async def fetch_provider_models(req: FetchProviderModelsRequest):
    """从供应商 API 获取可用模型列表"""
    base_url = req.base_url or PROVIDER_DEFAULT_BASE_URL.get(req.provider)
    if not base_url:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{req.provider}'. Please provide base_url.",
        )

    # Determine endpoint and auth header per provider type
    if req.provider == "google":
        url = f"{base_url}/models?key={req.api_key}"
        headers: dict[str, str] = {}
    elif req.provider == "anthropic":
        url = f"{base_url}/models"
        headers = {"x-api-key": req.api_key, "anthropic-version": "2023-06-01"}
    else:
        # OpenAI-compatible API
        url = f"{base_url}/models"
        headers = {"Authorization": f"Bearer {req.api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 401 or resp.status_code == 403:
                raise HTTPException(status_code=401, detail="Invalid API key or unauthorized")
            if resp.status_code != 200:
                logger.warning(f"Provider {req.provider} returned {resp.status_code}: {resp.text[:200]}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Provider API returned {resp.status_code}",
                )
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Provider API timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail=f"Cannot connect to {base_url}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Parse model list — handle different response formats
    raw_models: list[dict] = []
    if isinstance(data, dict):
        # OpenAI format: {"object":"list", "data":[...]}
        raw_models = data.get("data", [])
        # Anthropic format: {"data": [{"id": "...", ...}]}
        if not raw_models and "models" in data:
            raw_models = data["models"]
        # Google format: {"models": [{"name": "...", ...}]}
    elif isinstance(data, list):
        raw_models = data

    models = []
    for m in raw_models:
        model_id = m.get("id") or m.get("name") or m.get("model") or ""
        if not model_id:
            continue
        display = m.get("display_name") or m.get("name") or model_id
        models.append({"id": model_id, "display_name": display})

    return {
        "provider": req.provider,
        "base_url": base_url,
        "models": models,
        "count": len(models),
    }


def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
