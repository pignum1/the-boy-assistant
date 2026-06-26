import uuid
from sqlalchemy import select, func

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentChatRequest
from app.services import agent_factory
from app.services.agent_pool import agent_pool

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await agent_factory.create_agent(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Agent '{data.name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Agent.id)))).scalar() or 0
    result = await db.execute(
        select(Agent).offset(skip).limit(limit).order_by(Agent.created_at.desc())
    )
    return {"items": result.scalars().all(), "total": total}


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await agent_factory.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID, data: AgentUpdate, db: AsyncSession = Depends(get_db)
):
    agent = await agent_factory.update_agent(db, agent_id, data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    deleted = await agent_factory.delete_agent(db, agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/pool/status")
async def get_pool_status(status: str = None):
    """获取 Agent Pool 运行时状态"""
    entries = agent_pool.get_status(status_filter=status)
    return {
        "total": agent_pool.total_count,
        "available": agent_pool.get_available_count(),
        "busy": agent_pool.get_busy_count(),
        "agents": entries,
    }


@router.post("/{agent_id}/chat")
async def chat_with_agent(
    agent_id: uuid.UUID,
    request: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
):
    agent = await agent_factory.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = await agent_factory.agent_chat(
            db=db,
            agent=agent,
            message=request.message,
            mock=request.mock,
            team_id=request.team_id,
            session_id=request.session_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
