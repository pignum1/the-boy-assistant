"""Snapshot Manager：工作空间快照创建/恢复/列表

基础版：使用 shutil.copytree 创建备份目录
后续 Phase 7 (Harness) 会在 Validation 失败时调用 restore_snapshot 回滚
"""

import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """快照记录"""
    snapshot_id: str
    session_id: str
    path: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    size_bytes: int = 0


class SnapshotManager:
    """工作空间快照管理器"""

    def __init__(self, base_path: str):
        self._base_path = base_path
        self._snapshots_dir = os.path.join(base_path, ".snapshots")
        self._snapshots: dict[str, Snapshot] = {}  # snapshot_id → Snapshot

    def create_snapshot(self, session_id: str, workspace_path: str) -> Snapshot:
        """创建工作空间快照"""
        if not os.path.exists(workspace_path):
            raise ValueError(f"Workspace not found: {workspace_path}")

        snapshot_id = str(uuid.uuid4())[:8]
        snapshot_path = os.path.join(self._snapshots_dir, session_id, snapshot_id)
        os.makedirs(snapshot_path, exist_ok=True)

        # 复制工作空间内容
        shutil.copytree(workspace_path, os.path.join(snapshot_path, "data"), dirs_exist_ok=True)

        # 计算大小
        size = sum(
            os.path.getsize(os.path.join(dirpath, f))
            for dirpath, _, filenames in os.walk(os.path.join(snapshot_path, "data"))
            for f in filenames
        )

        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            session_id=session_id,
            path=snapshot_path,
            size_bytes=size,
        )
        self._snapshots[snapshot_id] = snapshot

        logger.info(f"Snapshot created: {snapshot_id} for session={session_id} size={size}B")
        return snapshot

    def restore_snapshot(self, session_id: str, snapshot_id: str, workspace_path: str) -> bool:
        """恢复工作空间到指定快照"""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            logger.error(f"Snapshot not found: {snapshot_id}")
            return False

        snapshot_data_path = os.path.join(snapshot.path, "data")
        if not os.path.exists(snapshot_data_path):
            logger.error(f"Snapshot data not found: {snapshot_data_path}")
            return False

        try:
            # 清空当前工作空间
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)

            # 从快照恢复
            shutil.copytree(snapshot_data_path, workspace_path)

            logger.info(f"Snapshot restored: {snapshot_id} → {workspace_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}")
            return False

    def list_snapshots(self, session_id: str) -> list[dict]:
        """列出工作空间的所有快照"""
        result = []
        for snap in self._snapshots.values():
            if snap.session_id == session_id:
                result.append({
                    "snapshot_id": snap.snapshot_id,
                    "created_at": snap.created_at,
                    "size_bytes": snap.size_bytes,
                })
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除快照"""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return False

        try:
            if os.path.exists(snapshot.path):
                shutil.rmtree(snapshot.path)
            del self._snapshots[snapshot_id]
            logger.info(f"Snapshot deleted: {snapshot_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False
