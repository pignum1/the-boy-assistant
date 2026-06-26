import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.tool import ToolCreate, ToolUpdate, ToolResponse
from app.services import tool_registry

router = APIRouter()


@router.post("", response_model=ToolResponse, status_code=201)
async def create_tool(data: ToolCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await tool_registry.register_tool(db, data)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Tool '{data.name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[ToolResponse])
async def list_tools(db: AsyncSession = Depends(get_db)):
    return await tool_registry.list_tools(db)


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    tool = await tool_registry.get_tool(db, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID, data: ToolUpdate, db: AsyncSession = Depends(get_db)
):
    tool = await tool_registry.update_tool(db, tool_id, data)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    deleted = await tool_registry.delete_tool(db, tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")


@router.post("/seed", response_model=list[ToolResponse])
async def seed_tools(db: AsyncSession = Depends(get_db)):
    """Seed preset tools (file-ops, terminal)"""
    await tool_registry.seed_preset_tools(db)
    return await tool_registry.list_tools(db)
