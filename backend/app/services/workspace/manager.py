"""Workspace Manager：工作空间生命周期管理

职责：
1. 创建/获取/清理工作空间目录
2. 集成 SnapshotManager 和 FileProxy
3. 工作空间状态追踪
4. 工作空间路径默认从配置读取，SessionService 可在创建时覆盖
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from app.core.config import get_settings
from app.services.workspace.snapshot import SnapshotManager
from app.services.workspace.file_proxy import FileProxy

logger = logging.getLogger(__name__)


class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class Workspace:
    """工作空间实例"""
    session_id: str
    path: str
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkspaceManager:
    """工作空间管理器"""

    def __init__(self, base_path: str = None):
        settings = get_settings()
        resolved = os.path.expanduser(base_path or settings.WORKSPACE_BASE_PATH)
        self._base_path = resolved
        self._workspaces: dict[str, Workspace] = {}
        self._snapshot_mgr = SnapshotManager(resolved)
        self._file_proxy = FileProxy()

    @property
    def snapshot_manager(self) -> SnapshotManager:
        return self._snapshot_mgr

    @property
    def file_proxy(self) -> FileProxy:
        return self._file_proxy

    def create_workspace(self, session_id: str, custom_path: str = None) -> Workspace:
        """创建工作空间目录

        custom_path: 用户自定义路径，为 None 时使用默认 base_path + session_id
        """
        ws_path = custom_path or os.path.join(self._base_path, session_id)
        ws_path = os.path.expanduser(ws_path)
        # 安全检查：custom_path 必须在 base_path 内（或为默认路径）
        ws_real = os.path.realpath(ws_path)
        base_real = os.path.realpath(self._base_path)
        if not ws_real.startswith(base_real + os.sep) and ws_real != base_real:
            raise ValueError(f"Workspace path {ws_path} is outside base path {self._base_path}")
        os.makedirs(ws_path, exist_ok=True)

        ws = Workspace(session_id=session_id, path=ws_path)
        self._workspaces[session_id] = ws
        logger.info(f"Workspace created: {ws_path}")
        return ws

    def get_workspace(self, session_id: str) -> Optional[Workspace]:
        """获取工作空间"""
        return self._workspaces.get(session_id)

    def get_or_create(self, session_id: str) -> Workspace:
        """获取或创建工作空间"""
        ws = self.get_workspace(session_id)
        if ws:
            ws.last_accessed = datetime.now(timezone.utc).isoformat()
            return ws
        return self.create_workspace(session_id)

    def clean_workspace(self, session_id: str) -> bool:
        """清理工作空间（删除目录）"""
        ws = self._workspaces.get(session_id)
        if not ws:
            return False

        try:
            if os.path.exists(ws.path):
                shutil.rmtree(ws.path)
            ws.status = WorkspaceStatus.DELETED
            del self._workspaces[session_id]
            logger.info(f"Workspace cleaned: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clean workspace {session_id}: {e}")
            return False

    def list_workspaces(self, status: Optional[str] = None) -> list[dict]:
        """列出所有工作空间"""
        result = []
        for ws in self._workspaces.values():
            if status and ws.status.value != status:
                continue
            result.append({
                "session_id": ws.session_id,
                "path": ws.path,
                "status": ws.status.value,
                "created_at": ws.created_at,
                "last_accessed": ws.last_accessed,
            })
        return result

    @property
    def active_count(self) -> int:
        return sum(1 for ws in self._workspaces.values() if ws.status == WorkspaceStatus.ACTIVE)


# Global workspace manager
workspace_manager = WorkspaceManager()
