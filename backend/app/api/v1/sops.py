"""SOPs API：SOP CRUD + YAML 导入"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sop_service import SOPService
from app.schemas.sop import SOPCreate, SOPUpdate

router = APIRouter()


@router.post("")
async def create_sop(
    req: SOPCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = SOPService(db)
    sop = await svc.create_sop(
        team_id=req.team_id,
        name=req.name,
        nodes=req.nodes,
        edges=req.edges,
        description=req.description,
        format=req.format,
        version=req.version,
        is_template=req.is_template,
    )
    return _sop_response(sop)


@router.get("")
async def list_sops(
    team_id: uuid.UUID = None,
    db: AsyncSession = Depends(get_db),
):
    svc = SOPService(db)
    sops = await svc.list_sops(team_id)
    return [_sop_response(s) for s in sops]


@router.get("/{sop_id}")
async def get_sop(sop_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = SOPService(db)
    sop = await svc.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return _sop_response(sop)


@router.put("/{sop_id}")
async def update_sop(
    sop_id: uuid.UUID,
    req: SOPUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = SOPService(db)
    sop = await svc.update_sop(sop_id, **req.model_dump(exclude_unset=True))
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return _sop_response(sop)


@router.delete("/{sop_id}", status_code=204)
async def delete_sop(sop_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = SOPService(db)
    deleted = await svc.delete_sop(sop_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="SOP not found")


@router.post("/import")
async def import_sop(
    team_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import SOP from YAML file"""
    content = await file.read()
    try:
        yaml_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    svc = SOPService(db)
    try:
        sop = await svc.import_from_yaml(uuid.UUID(team_id), yaml_str)
    except (ValueError, Exception) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _sop_response(sop)


@router.get("/{sop_id}/export")
async def export_sop(sop_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Export SOP as YAML"""
    svc = SOPService(db)
    sop = await svc.get_sop(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    yaml_str = svc.export_to_yaml(sop)
    return {"yaml": yaml_str}


def _sop_response(sop) -> dict:
    return {
        "id": str(sop.id),
        "team_id": str(sop.team_id),
        "name": sop.name,
        "description": sop.description,
        "nodes": sop.nodes,
        "edges": sop.edges,
        "format": sop.format,
        "version": sop.version,
        "is_template": sop.is_template,
        "created_at": sop.created_at.isoformat(),
        "updated_at": sop.updated_at.isoformat(),
    }
