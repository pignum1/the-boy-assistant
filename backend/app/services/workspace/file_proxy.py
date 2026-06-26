"""File Proxy：工作空间文件操作代理

职责：
1. 限制文件操作在指定工作空间内（路径安全）
2. 读写操作加锁（防并发写入冲突）
3. 操作日志记录
"""

import asyncio
import logging
import os
from typing import Optional

import aiofiles

logger = logging.getLogger(__name__)

# 安全：阻止访问的路径模式
BLOCKED_PATTERNS = [".env", ".git", ".ssh", ".aws", "credentials", "secret"]


class FileProxy:
    """工作空间文件操作代理"""

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}  # file_path → Lock

    def _get_lock(self, path: str) -> asyncio.Lock:
        """获取文件级锁"""
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        return self._locks[path]

    def _is_path_safe(self, workspace_path: str, file_path: str) -> tuple[bool, str]:
        """检查路径是否安全（在工作空间内且无危险模式）"""
        resolved = os.path.abspath(file_path)
        workspace = os.path.abspath(workspace_path)

        # 必须在工作空间内
        if not resolved.startswith(workspace):
            return False, f"Path outside workspace: {file_path}"

        # 检查危险模式
        basename = os.path.basename(resolved).lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in basename:
                return False, f"Blocked pattern: {pattern}"

        return True, ""

    async def read_file(self, workspace_path: str, file_path: str) -> str:
        """读取文件（限制在工作空间内）"""
        safe, msg = self._is_path_safe(workspace_path, file_path)
        if not safe:
            raise PermissionError(msg)

        lock = self._get_lock(file_path)
        async with lock:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = await f.read()

        logger.debug(f"FileProxy read: {os.path.relpath(file_path, workspace_path)}")
        return content

    async def write_file(self, workspace_path: str, file_path: str, content: str) -> int:
        """写入文件（限制在工作空间内）"""
        safe, msg = self._is_path_safe(workspace_path, file_path)
        if not safe:
            raise PermissionError(msg)

        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        lock = self._get_lock(file_path)
        async with lock:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)

        logger.debug(f"FileProxy write: {os.path.relpath(file_path, workspace_path)} ({len(content)} chars)")
        return len(content)

    def list_files(self, workspace_path: str, subdir: str = "") -> list[dict]:
        """列出工作空间内的文件"""
        target = os.path.join(workspace_path, subdir) if subdir else workspace_path
        safe, msg = self._is_path_safe(workspace_path, target)
        if not safe:
            raise PermissionError(msg)

        if not os.path.exists(target):
            return []

        result = []
        for entry in sorted(os.listdir(target)):
            full = os.path.join(target, entry)
            result.append({
                "name": entry,
                "is_dir": os.path.isdir(full),
                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
            })
        return result

    def file_exists(self, workspace_path: str, file_path: str) -> bool:
        """检查文件是否存在"""
        safe, _ = self._is_path_safe(workspace_path, file_path)
        if not safe:
            return False
        return os.path.exists(file_path)
