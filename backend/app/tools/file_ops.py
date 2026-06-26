import asyncio
import os
import uuid
import aiofiles
from typing import Optional

from app.tools.base import BaseTool, ToolResult
from app.services.workspace.manager import workspace_manager
from app.core.config import get_settings

# Blocked file patterns for security
BLOCKED_PATTERNS = [".env", ".git", ".ssh", ".aws", "credentials", "secret", "private_key"]
BLOCKED_EXTENSIONS = [".pem", ".key", ".p12"]


class FileOpsTool(BaseTool):
    name = "file-ops"
    description = """文件读写操作（会话工作空间内）：
- read: 读取文件内容
- write: 写入文件内容（自动创建目录）
- list_dir: 列出目录内容
- file_info: 获取文件信息

注意：所有文件操作都在会话的工作空间内，路径是相对于工作空间根目录的。
例如：path="docs/readme.md" 会操作工作空间内的 docs/readme.md 文件。
"""
    parameters = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": ["read", "write", "list_dir", "file_info"], "description": "操作类型"},
            "path": {"type": "string", "description": "文件路径（相对于工作空间根目录）"},
            "content": {"type": "string", "description": "写入内容（write 操作需要）"},
        },
        "required": ["operation", "path"],
    }

    def _is_path_safe(self, path: str) -> tuple[bool, str]:
        """Check if path is safe to access"""
        resolved = os.path.abspath(path)
        basename = os.path.basename(resolved).lower()

        for pattern in BLOCKED_PATTERNS:
            if pattern in basename:
                return False, f"Access denied: path contains blocked pattern '{pattern}'"
        for ext in BLOCKED_EXTENSIONS:
            if resolved.lower().endswith(ext):
                return False, f"Access denied: blocked file extension '{ext}'"
        return True, ""

    async def execute(self, params: dict, session_id: Optional[str] = None) -> ToolResult:
        operation = params.get("operation")
        path = params.get("path", "")

        # 如果没有提供 session_id，拒绝操作（安全考虑）
        if not session_id:
            return ToolResult(success=False, error="需要 session_id 才能进行文件操作")

        # 解析工作空间根路径：优先内存 → 数据库 Session 记录 → 默认路径
        ws = workspace_manager.get_workspace(session_id)
        ws_path = ws.path if ws else None

        if not ws_path:
            # 尝试从数据库恢复工作空间路径
            import uuid as _uuid
            from app.core.database import async_session
            from app.models.session import Session as SessionModel
            try:
                async with async_session() as db:
                    session = await db.get(SessionModel, _uuid.UUID(session_id))
                    if session and session.workspace_path:
                        ws_path = os.path.expanduser(session.workspace_path)
                    else:
                        ws_path = os.path.join(
                            os.path.expanduser(get_settings().WORKSPACE_BASE_PATH),
                            session_id
                        )
            except Exception:
                ws_path = os.path.join(
                    os.path.expanduser(get_settings().WORKSPACE_BASE_PATH),
                    session_id
                )
            # 确保目录存在并注册到 workspace_manager（线程池避免阻塞）
            await asyncio.to_thread(os.makedirs, ws_path, exist_ok=True)
            workspace_manager.create_workspace(session_id, custom_path=ws_path)

        # 解析路径：如果 LLM 传了绝对路径且在工作空间内，自动转为相对路径
        if os.path.isabs(path) and path.startswith(ws_path):
            path = os.path.relpath(path, ws_path)
        elif os.path.isabs(path):
            return ToolResult(
                success=False,
                error=f"请使用相对路径。工作空间根路径为: {ws_path}，你传入的路径 {path} 不在工作空间内。"
            )

        # 防止路径遍历和符号链接绕过攻击
        if ".." in path:
            return ToolResult(success=False, error="路径包含非法字符 '..'，仅允许访问工作空间内的文件")

        ws_real = os.path.realpath(ws_path)
        abs_path = os.path.realpath(os.path.join(ws_real, path))
        if not abs_path.startswith(ws_real + os.sep) and abs_path != ws_real:
            return ToolResult(success=False, error=f"路径超出工作空间范围: {path}")

        workspace_path = abs_path

        safe, msg = self._is_path_safe(workspace_path)
        if not safe:
            return ToolResult(success=False, error=msg)

        try:
            if operation == "read":
                return await self._read(workspace_path)
            elif operation == "write":
                content = params.get("content", "")
                return await self._write(workspace_path, content)
            elif operation == "list_dir":
                return await self._list_dir(workspace_path)
            elif operation == "file_info":
                return await self._file_info(workspace_path)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Path not found: {path}")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _read(self, path: str) -> ToolResult:
        async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as f:
            content = await f.read()
        return ToolResult(success=True, output=content)

    async def _write(self, path: str, content: str) -> ToolResult:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        return ToolResult(success=True, output=f"Written {len(content)} chars to {path}")

    async def _list_dir(self, path: str) -> ToolResult:
        # 在线程池中执行同步 I/O，避免阻塞事件循环
        def _sync():
            entries = sorted(os.listdir(path))
            lines = []
            for entry in entries:
                full = os.path.join(path, entry)
                prefix = "📁" if os.path.isdir(full) else "📄"
                lines.append(f"{prefix} {entry}")
            output = "\n".join(lines) if lines else "(empty directory)"
            return output, entries
        output, entries = await asyncio.to_thread(_sync)
        return ToolResult(success=True, output=output, data={"entries": entries})

    async def _file_info(self, path: str) -> ToolResult:
        def _sync():
            stat = os.stat(path)
            return {
                "name": os.path.basename(path),
                "size": stat.st_size,
                "is_dir": os.path.isdir(path),
                "modified": stat.st_mtime,
            }
        info = await asyncio.to_thread(_sync)
        output = f"Name: {info['name']}\nSize: {info['size']} bytes\nDir: {info['is_dir']}"
        return ToolResult(success=True, output=output, data=info)
