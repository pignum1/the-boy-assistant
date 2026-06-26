"""Workspace Manager 包

重新导出核心类
"""

from app.services.workspace.manager import WorkspaceManager
from app.services.workspace.snapshot import SnapshotManager
from app.services.workspace.file_proxy import FileProxy

__all__ = ["WorkspaceManager", "SnapshotManager", "FileProxy"]
