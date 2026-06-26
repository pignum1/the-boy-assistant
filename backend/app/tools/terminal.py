import asyncio
import os
import shlex
import uuid
from typing import Optional

from app.tools.base import BaseTool, ToolResult

# 危险命令黑名单（禁止执行）
_BLOCKED_COMMANDS: frozenset[str] = frozenset({
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf .",
    "sudo rm", "chmod 777", "chmod -R 777",
    "mkfs.", "dd if=", ":(){ :|:& };:",
    "> /dev/sda", "mv / /dev/null",
})


def _is_command_safe(command: str) -> tuple[bool, str]:
    """检查命令是否安全可执行。返回 (safe, reason)。"""
    stripped = command.strip()
    if not stripped:
        return False, "Empty command"

    # 检查黑名单
    for blocked in _BLOCKED_COMMANDS:
        if blocked in stripped:
            return False, f"Blocked dangerous pattern: {blocked}"

    # 禁止 shell 重定向和管道到敏感位置
    dangerous_redirects = ["> /etc", ">> /etc", "> /root", ">> /root", "> ~/", "| sh", "| bash"]
    for dr in dangerous_redirects:
        if dr in stripped:
            return False, f"Blocked dangerous redirect: {dr}"

    return True, ""


class TerminalSession:
    """A stateful terminal session tied to a session_id."""

    def __init__(self, session_id: str, workdir: Optional[str] = None):
        self.session_id = session_id
        self.workdir = workdir or "/tmp"

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        safe, reason = _is_command_safe(command)
        if not safe:
            return ToolResult(success=False, error=reason)

        try:
            # 使用 create_subprocess_exec（非 shell）避免命令注入
            # 对简单命令使用 shlex 安全解析
            try:
                args = shlex.split(command)
            except ValueError as e:
                return ToolResult(success=False, error=f"Invalid command syntax: {e}")

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")

            # 处理 cd 命令（通过 os.chdir 安全处理）
            if len(args) >= 2 and args[0] == "cd":
                target = os.path.expanduser(args[1])
                new_dir = os.path.realpath(os.path.join(self.workdir, target))
                if os.path.isdir(new_dir):
                    self.workdir = new_dir
                    output = f"Changed directory to {new_dir}"
                else:
                    return ToolResult(success=False, error=f"Not a directory: {target}")

            result = output
            if error:
                result += f"\n[stderr] {error}" if result else f"[stderr] {error}"

            return ToolResult(
                success=proc.returncode == 0,
                output=result,
                error=error if proc.returncode != 0 else "",
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()  # 避免僵尸进程
            except Exception:
                pass
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Command not found: {args[0] if args else command}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TerminalSessionManager:
    """Manages terminal sessions lifecycle."""

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}

    def create(self, session_id: Optional[str] = None, workdir: Optional[str] = None) -> TerminalSession:
        sid = session_id or str(uuid.uuid4())
        session = TerminalSession(sid, workdir)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: Optional[str] = None, workdir: Optional[str] = None) -> TerminalSession:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create(session_id, workdir)

    def destroy(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# Global session manager
terminal_manager = TerminalSessionManager()


class TerminalTool(BaseTool):
    name = "terminal"
    description = "终端命令执行：在 bash 环境中运行命令，支持工作目录持久化"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["command"],
    }

    async def execute(self, params: dict, session_id: Optional[str] = None) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)

        if not command:
            return ToolResult(success=False, error="Empty command")

        session = terminal_manager.get_or_create(session_id)
        return await session.execute(command, timeout)
