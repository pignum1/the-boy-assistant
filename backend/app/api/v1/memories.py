import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.memory import (
    MemoryCreate, MemoryUpdate, MemoryResponse, AgentMemoryView,
    MemoryLevel,
)
from app.services.memory_manager import MemoryManager

router = APIRouter()


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(data: MemoryCreate, db: AsyncSession = Depends(get_db)):
    """手动写入一条记忆（Admin 接口）"""
    mgr = MemoryManager(db)
    memory = await mgr.save_memory(
        level=data.level,
        content=data.content,
        type=data.type,
        team_id=data.team_id,
        agent_id=data.agent_id,
        session_id=data.session_id,
        importance=data.importance,
        created_by=data.created_by,
    )
    return memory


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    level: str = Query(None),
    team_id: uuid.UUID = Query(None),
    agent_id: uuid.UUID = Query(None),
    type: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询记忆列表"""
    mgr = MemoryManager(db)
    memories = await mgr.get_memories(
        level=level,
        team_id=team_id,
        agent_id=agent_id,
        type=type,
        limit=limit,
        order_by_importance=True,
    )
    return memories


@router.get("/agents/{agent_id}/view", response_model=AgentMemoryView)
async def get_agent_memory_view(
    agent_id: uuid.UUID,
    team_id: uuid.UUID = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """获取 Agent 的四层记忆视图"""
    mgr = MemoryManager(db)
    view = await mgr.get_agent_view(agent_id=agent_id, team_id=team_id)
    return view


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取单条记忆"""
    mgr = MemoryManager(db)
    memory = await mgr.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: uuid.UUID, data: MemoryUpdate, db: AsyncSession = Depends(get_db)
):
    """更新记忆"""
    mgr = MemoryManager(db)
    memory = await mgr.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(memory, field, value)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除单条记忆"""
    mgr = MemoryManager(db)
    deleted = await mgr.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")


@router.post("/refresh-importance")
async def refresh_importance(
    team_id: uuid.UUID = Query(None),
    agent_id: uuid.UUID = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """批量重新计算重要性"""
    mgr = MemoryManager(db)
    count = await mgr.refresh_importance(team_id=team_id, agent_id=agent_id)
    return {"updated": count}
