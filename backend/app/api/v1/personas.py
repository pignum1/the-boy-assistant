import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.persona import Persona
from app.schemas.persona import PersonaCreate, PersonaUpdate, PersonaResponse
from app.services import persona_service

router = APIRouter()


@router.post("", response_model=PersonaResponse, status_code=201)
async def create_persona(data: PersonaCreate, db: AsyncSession = Depends(get_db)):
    try:
        persona = await persona_service.create_persona(db, data)
        return persona
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Persona '{data.name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_personas(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Persona.id)))).scalar() or 0
    result = await db.execute(
        select(Persona).offset(skip).limit(limit).order_by(Persona.created_at.desc())
    )
    return {"items": result.scalars().all(), "total": total}


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(persona_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    persona = await persona_service.get_persona(db, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: uuid.UUID, data: PersonaUpdate, db: AsyncSession = Depends(get_db)
):
    persona = await persona_service.update_persona(db, persona_id, data)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(persona_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    deleted = await persona_service.delete_persona(db, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Persona not found")


@router.post("/seed", response_model=list[PersonaResponse])
async def seed_personas(db: AsyncSession = Depends(get_db)):
    """Seed preset personas (高级架构师, 程序员)"""
    await persona_service.seed_preset_personas(db)
    return await persona_service.list_personas(db)
