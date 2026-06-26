"""知识库 API：上传、检索、管理"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.knowledge import KnowledgeSearchRequest
from app.services.rag.knowledge_service import KnowledgeService

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    type: str = Form("global"),
    team_id: str = Form(None),
    agent_id: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """上传文档到知识库（.txt, .md, .py 等）"""
    # Read file
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text")

    if len(text) < 10:
        raise HTTPException(status_code=400, detail="File content too short")

    svc = KnowledgeService(db)
    kb = await svc.upload_document(
        content=text,
        file_name=file.filename,
        kb_type=type,
        team_id=_safe_uuid(team_id),
        agent_id=uuid.UUID(agent_id) if agent_id else None,
    )

    return {
        "id": str(kb.id),
        "name": kb.name,
        "type": kb.type,
        "chunk_count": kb.chunk_count,
        "file_name": kb.file_name,
    }


@router.post("/search")
async def search_knowledge(
    req: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """检索知识库"""
    svc = KnowledgeService(db)
    results = await svc.search(
        query=req.query,
        top_k=req.top_k,
        method=req.method,
        rerank=req.rerank,
        agent_id=uuid.UUID(req.agent_id) if req.agent_id else None,
        team_id=uuid.UUID(req.team_id) if req.team_id else None,
    )

    return {
        "query": req.query,
        "method": req.method,
        "total": len(results),
        "results": [
            {
                "id": r.get("id"),
                "content": r.get("content", "")[:500],
                "score": round(r.get("rrf_score", r.get("rerank_score", r.get("score", 0))), 4),
                "source": r.get("source", ""),
                "source_level": r.get("source_level"),
                "metadata": r.get("metadata"),
            }
            for r in results
        ],
    }


@router.get("")
async def list_knowledge_bases(
    type: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """列出知识库"""
    svc = KnowledgeService(db)
    kbs = await svc.list_knowledge_bases(kb_type=type)
    return [
        {
            "id": str(kb.id),
            "name": kb.name,
            "type": kb.type,
            "chunk_count": kb.chunk_count,
            "file_name": kb.file_name,
            "created_at": kb.created_at.isoformat(),
        }
        for kb in kbs
    ]


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除知识库"""
    svc = KnowledgeService(db)
    deleted = await svc.delete_knowledge_base(kb_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
