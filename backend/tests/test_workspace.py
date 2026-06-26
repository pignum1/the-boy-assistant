"""Workspace Manager 单元测试：WorkspaceManager + SnapshotManager + FileProxy"""

import pytest
import tempfile
import os

from app.services.workspace.manager import WorkspaceManager
from app.services.workspace.snapshot import SnapshotManager
from app.services.workspace.file_proxy import FileProxy


# ── WorkspaceManager 测试 ──────────────────────────────────

class TestWorkspaceManager:
    def setup_method(self):
        self.tmp_base = tempfile.mkdtemp()
        self.wm = WorkspaceManager(base_path=self.tmp_base)

    def test_create_workspace(self):
        ws = self.wm.create_workspace("session-001")
        assert ws.session_id == "session-001"
        assert os.path.isdir(ws.path)

    def test_get_workspace(self):
        self.wm.create_workspace("session-002")
        ws = self.wm.get_workspace("session-002")
        assert ws is not None
        assert ws.session_id == "session-002"

    def test_get_or_create(self):
        ws1 = self.wm.get_or_create("session-003")
        ws2 = self.wm.get_or_create("session-003")
        assert ws1.path == ws2.path

    def test_get_nonexistent(self):
        assert self.wm.get_workspace("nonexistent") is None

    def test_list_workspaces(self):
        self.wm.create_workspace("session-a")
        self.wm.create_workspace("session-b")
        workspaces = self.wm.list_workspaces()
        ids = [ws["session_id"] for ws in workspaces]
        assert "session-a" in ids
        assert "session-b" in ids

    def test_clean_workspace(self):
        self.wm.create_workspace("session-004")
        result = self.wm.clean_workspace("session-004")
        assert result is True
        assert self.wm.get_workspace("session-004") is None

    def test_clean_nonexistent(self):
        result = self.wm.clean_workspace("nonexistent")
        assert result is False

    def test_active_count(self):
        self.wm.create_workspace("s1")
        self.wm.create_workspace("s2")
        assert self.wm.active_count == 2


# ── SnapshotManager 测试 ────────────────────────────────────

class TestSnapshotManager:
    def setup_method(self):
        self.tmp_base = tempfile.mkdtemp()
        self.sm = SnapshotManager(base_path=self.tmp_base)
        self.ws_path = os.path.join(self.tmp_base, "ws-test")
        os.makedirs(self.ws_path, exist_ok=True)

    def test_create_snapshot(self):
        with open(os.path.join(self.ws_path, "test.txt"), "w") as f:
            f.write("hello")

        snap = self.sm.create_snapshot("session-001", self.ws_path)
        assert snap is not None
        assert snap.snapshot_id
        assert os.path.isdir(snap.path)
        # Verify data was copied
        data_path = os.path.join(snap.path, "data")
        assert os.path.exists(os.path.join(data_path, "test.txt"))

    def test_list_snapshots(self):
        self.sm.create_snapshot("session-002", self.ws_path)
        self.sm.create_snapshot("session-002", self.ws_path)
        snapshots = self.sm.list_snapshots("session-002")
        assert len(snapshots) >= 2

    def test_restore_snapshot(self):
        with open(os.path.join(self.ws_path, "data.txt"), "w") as f:
            f.write("original")

        snap = self.sm.create_snapshot("session-003", self.ws_path)

        # Modify the workspace
        with open(os.path.join(self.ws_path, "data.txt"), "w") as f:
            f.write("modified")

        # Restore
        result = self.sm.restore_snapshot("session-003", snap.snapshot_id, self.ws_path)
        assert result is True
        with open(os.path.join(self.ws_path, "data.txt")) as f:
            assert f.read() == "original"

    def test_delete_snapshot(self):
        snap = self.sm.create_snapshot("session-004", self.ws_path)
        result = self.sm.delete_snapshot(snap.snapshot_id)
        assert result is True
        snapshots = self.sm.list_snapshots("session-004")
        assert len(snapshots) == 0

    def test_delete_nonexistent_snapshot(self):
        result = self.sm.delete_snapshot("nonexistent")
        assert result is False


# ── FileProxy 测试 ─────────────────────────────────────────

class TestFileProxy:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.fp = FileProxy()

    @pytest.mark.asyncio
    async def test_write_and_read(self):
        file_path = os.path.join(self.tmp_dir, "test.txt")
        await self.fp.write_file(self.tmp_dir, file_path, "hello world")
        content = await self.fp.read_file(self.tmp_dir, file_path)
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_list_files(self):
        await self.fp.write_file(self.tmp_dir, os.path.join(self.tmp_dir, "a.txt"), "a")
        await self.fp.write_file(self.tmp_dir, os.path.join(self.tmp_dir, "b.txt"), "b")
        files = self.fp.list_files(self.tmp_dir)
        names = [f["name"] for f in files]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_file_exists(self):
        file_path = os.path.join(self.tmp_dir, "exists.txt")
        await self.fp.write_file(self.tmp_dir, file_path, "yes")
        assert self.fp.file_exists(self.tmp_dir, file_path) is True
        assert self.fp.file_exists(self.tmp_dir, os.path.join(self.tmp_dir, "nope.txt")) is False

    def test_path_safety_blocked_traversal(self):
        safe, _ = self.fp._is_path_safe(self.tmp_dir, os.path.join(self.tmp_dir, "safe.txt"))
        assert safe is True

        safe, _ = self.fp._is_path_safe(self.tmp_dir, "/etc/passwd")
        assert safe is False

    def test_path_safety_blocked_patterns(self):
        safe, _ = self.fp._is_path_safe(self.tmp_dir, os.path.join(self.tmp_dir, ".env"))
        assert safe is False

        safe, _ = self.fp._is_path_safe(self.tmp_dir, os.path.join(self.tmp_dir, "credentials.json"))
        assert safe is False

    @pytest.mark.asyncio
    async def test_write_creates_subdirs(self):
        file_path = os.path.join(self.tmp_dir, "sub", "dir", "test.txt")
        await self.fp.write_file(self.tmp_dir, file_path, "deep")
        content = await self.fp.read_file(self.tmp_dir, file_path)
        assert content == "deep"
