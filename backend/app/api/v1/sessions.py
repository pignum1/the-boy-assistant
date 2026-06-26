"""Sessions API：会话生命周期管理端点

端点概览：
POST   /api/v1/sessions              创建会话（含工作空间初始化）
GET    /api/v1/sessions              列出会话（支持 ?team_id=&status= 过滤）
GET    /api/v1/sessions/{id}         获取会话详情
PUT    /api/v1/sessions/{id}         更新会话
DELETE /api/v1/sessions/{id}         归档会话
GET    /api/v1/sessions/{id}/messages 会话历史消息
GET    /api/v1/sessions/{id}/workspace 工作空间信息
PUT    /api/v1/sessions/{id}/workspace 修改工作空间路径
GET    /api/v1/sessions/{id}/tasks    会话任务列表
POST   /api/v1/sessions/{id}/tasks    创建会话任务
PUT    /api/v1/sessions/{id}/tasks/{task_id} 更新任务
DELETE /api/v1/sessions/{id}/tasks/{task_id} 删除任务
GET    /api/v1/dashboard               总控台数据
"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.session import (
    SessionCreate,
    SessionUpdate,
    WorkspaceUpdate,
)
from app.services.session_service import SessionService

router = APIRouter()


@router.post("", status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建新会话：写入 DB 记录 + 初始化工作空间目录

    返回创建的会话详情（含默认工作空间路径）
    """
    svc = SessionService(db)
    session = await svc.create_session(
        team_id=body.team_id,
        title=body.title,
        workspace_path=body.workspace_path,
        mode=body.mode,
    )
    return svc._session_to_response(session)


@router.get("")
async def list_sessions(
    team_id: str = Query(None, description="按团队 ID 过滤"),
    status: str = Query(None, description="按状态过滤: active | archived"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    db: AsyncSession = Depends(get_db),
):
    """列出会话（按 updated_at 降序排列）

    用作侧边栏会话列表 / 团队历史 Tab 的数据源
    """
    svc = SessionService(db)
    team_uuid = uuid.UUID(team_id) if team_id else None
    sessions = await svc.list_sessions(
        team_id=team_uuid, status=status, limit=limit
    )
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/dashboard")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """总控台数据"""
    from app.models.session import Session as SessionModel
    from app.services.team_manager import TeamManager
    from app.services.agent_pool import agent_pool
    tm = TeamManager(db)
    teams = await tm.list_teams()
    team_list = [{"id":str(t.id),"name":t.name,"icon":t.icon,"collaboration_mode":t.collaboration_mode,"status":t.status,"member_count":len(await tm.get_member_info(t.id))} for t in teams]
    result = await db.execute(select(SessionModel).where(SessionModel.status=="active").order_by(SessionModel.updated_at.desc()).limit(20))
    sessions = list(result.scalars().all())
    session_list = [{"id":str(s.id),"title":s.title,"team_id":str(s.team_id),"team_name":next((t.name for t in teams if t.id==s.team_id),"?"),"status":s.status,"message_count":s.message_count,"task_total":s.task_total,"task_completed":s.task_completed,"updated_at":s.updated_at.isoformat() if s.updated_at else None} for s in sessions]
    return {"teams":team_list,"sessions":session_list,"agent_summary":{"total":agent_pool.total_count,"idle":agent_pool.get_available_count(),"busy":agent_pool.get_busy_count()}}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情（含团队名称）"""
    svc = SessionService(db)
    result = await svc.get_session_with_team(uuid.UUID(session_id))
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新会话：标题 / 状态 / 工作空间路径"""
    svc = SessionService(db)
    update_kwargs = {}
    if body.title is not None:
        update_kwargs["title"] = body.title
    if body.status is not None:
        update_kwargs["status"] = body.status
    if body.workspace_path is not None:
        update_kwargs["workspace_path"] = body.workspace_path

    session = await svc.update_session(uuid.UUID(session_id), **update_kwargs)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return svc._session_to_response(session)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除会话（完全删除，包括对话记录、记忆数据和工作空间）"""
    svc = SessionService(db)
    ok = await svc.delete_session_completely(uuid.UUID(session_id))
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "deleted", "session_id": session_id}


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    db: AsyncSession = Depends(get_db),
):
    """获取会话的历史消息（从 Memory 表 level=context 查询）

    按 created_at 升序排列，前端直接渲染消息列表
    """
    svc = SessionService(db)
    messages = await svc.get_session_messages(
        uuid.UUID(session_id), limit=limit
    )
    return {"messages": messages, "total": len(messages)}


@router.get("/{session_id}/workspace")
async def get_workspace_info(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取会话工作空间信息：路径、文件数、大小"""
    svc = SessionService(db)
    info = await svc.get_workspace_info(uuid.UUID(session_id))
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在")
    return info


@router.get("/{session_id}/context")
async def get_context_window(
    session_id: str,
    limit: int = Query(default=200, ge=10, le=500),
    db: AsyncSession = Depends(get_db),
):
    """获取会话的完整上下文窗口信息

    返回 LLM 视角的完整上下文，包括：
    - 会话元信息
    - 所有消息（含完整 reasoning metadata）
    - 系统提示词（从团队 Agent 的 Persona 中获取）
    - 汇总统计（token 用量、记忆注入次数、RAG 块数）
    """
    svc = SessionService(db)
    ctx = await svc.get_context_window(uuid.UUID(session_id), limit=limit)
    if not ctx:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ctx


@router.put("/{session_id}/workspace")
async def update_workspace_path(
    session_id: str,
    body: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """修改会话工作空间路径

    仅当会话状态为 active 且新路径存在或可创建时才允许修改
    """
    import os

    svc = SessionService(db)
    session = await svc.get_session(uuid.UUID(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status != "active":
        raise HTTPException(
            status_code=400, detail="仅活跃状态的会话可修改工作空间"
        )

    # 验证新路径：已存在则必须是目录，否则自动创建
    expanded = os.path.expanduser(body.path)
    if os.path.exists(expanded) and not os.path.isdir(expanded):
        raise HTTPException(
            status_code=400, detail="路径已存在但不是目录"
        )
    os.makedirs(expanded, exist_ok=True)

    session = await svc.update_session(
        uuid.UUID(session_id), workspace_path=body.path
    )
    if not session:
        raise HTTPException(status_code=500, detail="更新失败")

    # 更新 WorkspaceManager 中的工作空间
    from app.services.workspace.manager import workspace_manager

    workspace_manager.clean_workspace(session_id)
    workspace_manager.create_workspace(session_id)

    info = await svc.get_workspace_info(uuid.UUID(session_id))
    return info


@router.get("/{session_id}/workspace/files")
async def list_workspace_files(
    session_id: str,
    path: str = "",
    recursive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """列出会话工作空间中的文件和目录（树形结构）

    传空 path 时返回根目录内容；传子目录路径时返回该目录内容。
    recursive=true 时递归返回所有文件（用于产物抽屉）。
    """
    import os

    svc = SessionService(db)
    info = await svc.get_workspace_info(uuid.UUID(session_id))
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在")

    ws_path = info.get("path", "")
    target = os.path.abspath(os.path.join(ws_path, path)) if path else ws_path

    # 安全
    if not target.startswith(os.path.abspath(ws_path)):
        raise HTTPException(status_code=403, detail="路径越权")

    def _collect(path_base: str) -> list[dict]:
        entries = []
        if not os.path.isdir(path_base):
            return entries
        try:
            for entry in sorted(os.listdir(path_base)):
                if entry == '.git':
                    continue
                full = os.path.join(path_base, entry)
                rel = os.path.relpath(full, ws_path)
                try:
                    stat = os.stat(full)
                    is_dir = os.path.isdir(full)
                    entries.append({
                        "name": entry,
                        "path": rel,
                        "size": stat.st_size if not is_dir else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "is_dir": is_dir,
                        "children": None,
                    })
                    if recursive and is_dir:
                        entries.extend(_collect(full))
                except OSError:
                    pass
        except PermissionError:
            pass
        return entries

    items = _collect(target)

    # 排序：目录在前，文件在后，各自按名称排序
    dirs = [i for i in items if i["is_dir"]]
    fls = [i for i in items if not i["is_dir"]]
    sorted_items = dirs + fls

    return {
        "session_id": session_id,
        "path": ws_path,
        "current_path": path,
        "items": sorted_items,
        "total": len(sorted_items),
    }


@router.post("/{session_id}/workspace/upload")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传文件到会话工作空间"""
    svc = SessionService(db)
    info = await svc.get_workspace_info(uuid.UUID(session_id))
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在")

    target_dir = info.get("path", "")
    if not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    # 安全：只保留文件名，拒绝路径穿越
    safe_name = os.path.basename(file.filename or "unnamed")
    dest = os.path.join(target_dir, safe_name)

    # 不覆盖已有文件，追加数字后缀
    if os.path.exists(dest):
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(os.path.join(target_dir, f"{base}_{counter}{ext}")):
            counter += 1
        safe_name = f"{base}_{counter}{ext}"
        dest = os.path.join(target_dir, safe_name)

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return {
        "session_id": session_id,
        "filename": safe_name,
        "path": dest,
        "size": len(content),
    }


@router.delete("/{session_id}/workspace/files")
async def delete_workspace_file(
    session_id: str,
    path: str = "",
    db: AsyncSession = Depends(get_db),
):
    """删除工作空间中的文件或目录"""
    import shutil

    svc = SessionService(db)
    info = await svc.get_workspace_info(uuid.UUID(session_id))
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在")

    ws_path = info.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="请指定要删除的文件路径")

    # 安全：确保路径在工作空间内
    target = os.path.abspath(os.path.join(ws_path, path))
    if not target.startswith(os.path.abspath(ws_path)):
        raise HTTPException(status_code=403, detail="路径越权")

    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return {"success": True, "message": f"已删除: {path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/{session_id}/workspace/files/{filename:path}")
async def get_file_content(
    session_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """获取工作空间中某个文件的内容（用于预览）

    支持文本文件：md, txt, py, ts, js, json, yaml, html, css, sql 等
    图片文件返回下载 URL
    """
    import mimetypes

    svc = SessionService(db)
    info = await svc.get_workspace_info(uuid.UUID(session_id))
    if not info:
        raise HTTPException(status_code=404, detail="会话不存在")

    base_path = info.get("path", "")
    # 安全：拒绝路径穿越
    safe_name = os.path.normpath(filename)
    if safe_name.startswith("..") or os.path.isabs(safe_name):
        raise HTTPException(status_code=400, detail="非法路径")
    file_path = os.path.join(base_path, safe_name)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 检查文件大小，拒绝过大的文件
    file_size = os.path.getsize(file_path)
    if file_size > 5 * 1024 * 1024:  # 5MB 限制
        raise HTTPException(status_code=400, detail="文件过大，不支持预览")

    mime_type, _ = mimetypes.guess_type(file_path)
    is_text = mime_type and (
        mime_type.startswith("text/") or
        mime_type in ("application/json", "application/javascript", "application/xml")
    )
    if not is_text:
        # 通过扩展名补充判断
        ext = os.path.splitext(safe_name)[1].lower()
        text_exts = {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".jsx", ".json",
                     ".yaml", ".yml", ".html", ".css", ".sql", ".sh", ".env",
                     ".xml", ".csv", ".ini", ".cfg", ".toml", ".rs", ".go"}
        is_text = ext in text_exts

    if is_text:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    content = f.read()
            except Exception:
                raise HTTPException(status_code=400, detail="无法读取文件编码")
        return {
            "session_id": session_id,
            "filename": safe_name,
            "size": file_size,
            "content": content,
            "mime_type": mime_type or "text/plain",
            "local_path": file_path,  # 添加本地绝对路径
        }
    else:
        # 非文本文件返回下载信息
        return {
            "session_id": session_id,
            "filename": safe_name,
            "size": file_size,
            "content": None,
            "mime_type": mime_type or "application/octet-stream",
            "download": True,
            "local_path": file_path,  # 添加本地绝对路径
        }


# ── 讨论模式聊天（REST fallback）──

from pydantic import BaseModel


class SessionChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("/{session_id}/chat")
async def session_chat(
    session_id: str,
    body: SessionChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """向会话发送消息（REST 同步方式，返回完整事件流）

    适用于不需要 WebSocket 的简单客户端。
    实时场景推荐使用 WebSocket: ws://.../ws/sessions/{session_id}
    """
    from app.services.discussion_engine import DiscussionEngine, DiscussionEvent
    from app.models.session import Session as SessionModel

    session = await db.get(SessionModel, uuid.UUID(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status != "active":
        raise HTTPException(status_code=400, detail="会话已归档，无法发送消息")

    engine = DiscussionEngine(db)
    events = []
    final_message = None

    async for event in engine.process_message(
        session_id=uuid.UUID(session_id),
        user_message=body.message,
        team_id=session.team_id,
        history=body.history,
    ):
        serialized = {
            "type": event.type.value,
            "source": event.source,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }
        events.append(serialized)
        if event.type.value == "agent_message":
            final_message = event.payload

    return {
        "session_id": session_id,
        "events": events,
        "message": final_message,
    }


@router.get("/workspace/dirs")
async def list_directories(path: str = ""):
    """浏览系统目录树，用于选择工作空间路径。

    传空字符串时列出系统根目录；传目录路径时列出该目录的子目录。
    支持绝对路径（如 /Users/xxx/projects）和相对路径。
    """
    import os

    # 安全：解析路径，防止路径穿越
    if path and not path.startswith('/'):
        # 相对路径，相对于 HOME
        requested = os.path.abspath(os.path.join(os.path.expanduser('~'), path))
    elif path:
        requested = os.path.abspath(path)
    else:
        # 默认从 HOME 开始
        requested = os.path.expanduser('~')

    # 基本安全检查：不要列出根目录之外的敏感路径
    if not os.path.exists(requested):
        return {"current_path": path, "parent_path": os.path.dirname(path) if path else None, "directories": [], "error": "路径不存在"}

    if not os.path.isdir(requested):
        return {"current_path": path, "parent_path": os.path.dirname(path) if path else None, "directories": [], "error": "不是目录"}

    dirs = []
    try:
        for entry in sorted(os.listdir(requested)):
            full = os.path.join(requested, entry)
            if os.path.isdir(full):
                dirs.append({
                    "name": entry,
                    "path": full,
                    "is_empty": _is_dir_empty(full),
                })
    except PermissionError:
        pass

    parent = os.path.dirname(requested)
    # 不允许浏览到根目录以上
    if requested == '/' or parent == requested:
        parent_path = None
    else:
        parent_path = parent

    return {
        "current_path": requested,
        "parent_path": parent_path,
        "directories": dirs,
    }


# ── Session Tasks ──
from app.services.session_task_service import SessionTaskService

@router.get("/{session_id}/tasks")
async def list_session_tasks(session_id: str, db: AsyncSession = Depends(get_db)):
    """获取会话任务列表"""
    svc = SessionTaskService(db)
    tasks = await svc.list_tasks(uuid.UUID(session_id))
    return {"tasks": [svc.task_to_dict(t) for t in tasks]}


@router.post("/{session_id}/tasks")
async def create_session_task(session_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """创建会话任务"""
    svc = SessionTaskService(db)
    task = await svc.create_task(
        session_id=uuid.UUID(session_id),
        title=body.get("title", ""),
        description=body.get("description"),
        priority=body.get("priority", "medium"),
        depends_on=body.get("depends_on"),
    )
    return svc.task_to_dict(task)


@router.put("/{session_id}/tasks/{task_id}")
async def update_session_task(session_id: str, task_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    """更新任务"""
    svc = SessionTaskService(db)
    task = await svc.update_task(
        task_id=uuid.UUID(task_id),
        title=body.get("title"),
        description=body.get("description"),
        status=body.get("status"),
        priority=body.get("priority"),
        assigned_agent_id=uuid.UUID(body["assigned_agent_id"]) if body.get("assigned_agent_id") else None,
        assigned_agent_name=body.get("assigned_agent_name"),
    )
    if not task:
        raise HTTPException(404, "任务不存在")
    return svc.task_to_dict(task)


@router.delete("/{session_id}/tasks/{task_id}", status_code=204)
async def delete_session_task(session_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    """删除任务"""
    svc = SessionTaskService(db)
    deleted = await svc.delete_task(uuid.UUID(task_id))
    if not deleted:
        raise HTTPException(404, "任务不存在")


def _is_dir_empty(path: str) -> bool:
    try:
        return len(os.listdir(path)) == 0
    except PermissionError:
        return False  # 无法读取的目录视为非空
