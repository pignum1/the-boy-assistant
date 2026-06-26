"""Skill API — 安装、列表、详情、删除、执行、匹配"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.skill import (
    SkillInstallRequest, SkillInstallResponse,
    SkillResponse, SkillListResponse,
)
from app.services.skill_registry import SkillRegistry
from app.services.skill_executor import SkillExecutor

router = APIRouter()


class SkillExecuteRequest(BaseModel):
    input: str
    context: Optional[str] = None
    mock: bool = False


# ── Install ──

@router.post("/install", response_model=SkillInstallResponse, status_code=201)
async def install_skill(
    method: str = Form(default="git"),
    git_url: Optional[str] = Form(default=None),
    name: Optional[str] = Form(default=None),
    branch: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    """安装 Skill — 支持 git clone 和 zip 上传两种方式"""
    svc = SkillRegistry(db)

    if method == "git":
        if not git_url:
            raise HTTPException(status_code=400, detail="git_url is required for git install")
        try:
            skill = await svc.install_from_git(git_url, name=name, branch=branch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif method == "upload":
        if not file:
            raise HTTPException(status_code=400, detail="file is required for upload install")
        if not file.filename or not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Only .zip files accepted")
        content = await file.read()
        try:
            skill = await svc.install_from_upload(content, file.filename)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    else:
        raise HTTPException(status_code=400, detail=f"Unknown install method: {method}")

    return SkillInstallResponse(
        id=str(skill.id),
        name=skill.name,
        description=skill.description,
        version=skill.version,
        path=skill.path,
        source=skill.source,
        git_url=skill.git_url,
    )


# ── Reload ──

@router.post("/reload")
async def reload_skills(db: AsyncSession = Depends(get_db)):
    """重新扫描 skills/ 目录，同步到 DB"""
    svc = SkillRegistry(db)
    result = await svc.scan_skills_dir()
    return result


# ── List ──

@router.get("")
async def list_skills(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """列出 Skill（分页）"""
    svc = SkillRegistry(db)
    skills, total = await svc.list_skills(skip=skip, limit=limit)
    return {
        "items": [
            SkillListResponse(
                id=str(s.id),
                name=s.name,
                description=s.description,
                version=s.version,
                path=s.path,
                source=s.source,
                git_url=s.git_url,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in skills
        ],
        "total": total,
    }


# ── Detail ──

@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取 Skill 详情（含 SKILL.md 内容）"""
    svc = SkillRegistry(db)
    skill_data = await svc.get_skill_with_content(skill_id)
    if not skill_data:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse(**skill_data)


# ── File Tree ──

@router.get("/{skill_id}/files")
async def get_skill_files(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取 Skill 目录的完整文件树（含文件内容）"""
    svc = SkillRegistry(db)
    tree = await svc.get_skill_file_tree(skill_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Skill not found")
    return tree


# ── Delete ──

@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除 Skill（目录 + DB 记录）"""
    svc = SkillRegistry(db)
    deleted = await svc.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")


# ── Execute ──

@router.post("/{skill_id}/execute")
async def execute_skill(
    skill_id: uuid.UUID,
    req: SkillExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """执行 Skill"""
    executor = SkillExecutor(db)
    try:
        result = await executor.execute_skill(
            skill_id=skill_id,
            user_input=req.input,
            context=req.context,
            mock=req.mock,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


# ── Match ──

@router.post("/match")
async def match_skill(
    req: SkillExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """根据输入匹配最合适的 Skill"""
    executor = SkillExecutor(db)
    match = await executor.match_skill(req.input)
    if not match:
        return {"matched": False}
    return {"matched": True, **match}
