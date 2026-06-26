"""M5: Context Pipeline — build trimmed context for each worker.

PRINCIPLE: CONTEXT ISOLATION

What's INCLUDED in a worker's context:
  - Original requirements (immutable anchor)
  - Previous artifacts this task DEPENDS ON (not all artifacts)
  - Current task description + acceptance criteria
  - Supervisor guidance
  - Peer messages (from M8)

What's EXCLUDED:
  - Other workers' reasoning chains
  - Irrelevant conversation history
  - Non-dependent artifacts
  - HITL interaction history

This prevents context bloat and cross-contamination between workers.
"""

import logging
from typing import Any

from .types import WorkerContext

logger = logging.getLogger(__name__)


class ContextPipeline:
    """Build trimmed worker contexts from CollabState.

    Each worker receives ONLY the information needed for their task.
    """

    def build_context(
        self,
        requirement_anchor: str,
        task: dict[str, Any],
        all_artifacts: dict[str, str],
        supervisor_guidance: str = "",
        constraints: list[str] | None = None,
        peer_messages: list[dict] | None = None,
        # ── Route B 新增参数 ──
        delegation_goal: str = "",
        org_role_context: str = "",
        retry_feedback: str = "",
    ) -> WorkerContext:
        """Build a single worker's trimmed context.

        Args:
            requirement_anchor: The confirmed, immutable requirements.
            task: Current task dict (from task_dag or delegation).
            all_artifacts: All completed artifacts keyed by task_id.
            supervisor_guidance: Execution guidance from Supervisor.
            constraints: Technical constraints.
            peer_messages: Messages from other agents (M8).
            delegation_goal: Supervisor-assigned goal (Route B).
            org_role_context: Role identity string (Route B).
            retry_feedback: Review feedback for retry (Route B).

        Returns:
            WorkerContext with only the necessary information.
        """
        depends_on = task.get("depends_on", [])

        # Only include artifacts this task actually depends on
        previous = {
            dep_id: all_artifacts[dep_id]
            for dep_id in depends_on
            if dep_id in all_artifacts
        }

        return WorkerContext(
            requirement_anchor=requirement_anchor,
            previous_artifacts=previous,
            current_task=task,
            supervisor_guidance=supervisor_guidance,
            constraints=constraints or [],
            agent_messages=peer_messages or [],
            delegation_goal=delegation_goal,
            org_role_context=org_role_context,
            retry_feedback=retry_feedback,
        )

    def format_context(self, ctx: WorkerContext, workspace_path: str = "") -> str:
        """Format WorkerContext into a prompt string for the worker LLM.

        This becomes the user_message for agent_chat().
        """
        parts = []

        # 0. Org role context (Route B — who am I?)
        if ctx.get("org_role_context"):
            parts.append("## 你的角色\n" + ctx["org_role_context"])

        # 1. Requirement anchor (always first — the north star)
        parts.append("## 需求 (不可偏离)\n" + ctx["requirement_anchor"])

        # 2. Previous artifacts this task depends on
        if ctx["previous_artifacts"]:
            parts.append("\n## 前置产物 (依赖)")
            for dep_id, artifact in ctx["previous_artifacts"].items():
                # Truncate long artifacts to avoid context bloat
                truncated = artifact[:3000] + "..." if len(artifact) > 3000 else artifact
                parts.append(f"\n### {dep_id}\n{truncated}")

        # 3. Current task with precise description
        task = ctx["current_task"]
        parts.append(f"\n## 当前任务: {task.get('title', '')}")
        parts.append(task.get("description", ""))
        if task.get("expected_output"):
            parts.append(f"\n产出规格: {task['expected_output']}")

        # 3b. Delegation goal (Route B — supervisor's assigned goal)
        if ctx.get("delegation_goal"):
            parts.append(f"\n## 主管分配的目标\n{ctx['delegation_goal']}")

        # 4. Workspace path + strict project-structure / file-path rules
        if workspace_path:
            parts.append(f"\n## 工作空间（项目根目录）\n当前路径: {workspace_path}")
            parts.append(
                "你的代码会**直接写入这个项目根目录**，按真实工程结构组织，"
                "不要建个人文件夹（禁止 `后端工程师-agent/` 这类目录）。"
            )
            parts.append(
                "## ⚠️ 代码输出格式（不遵守将被丢弃）\n\n"
                "**每个文件必须用一个代码块输出，代码块第一行必须标注语言和相对路径。**\n\n"
                "✅ 正确格式：\n"
                "```\n"
                "```python backend/app/main.py\n"
                "(文件内容)\n"
                "```\n"
                "```\n\n"
                "❌ 错误格式（没有路径 → 输出被丢弃）：\n"
                "```\n"
                "```python\n"
                "(文件内容)\n"
                "```\n"
                "```\n\n"
                "项目目录约定：\n"
                "- 后端文件 → `backend/`（`backend/app/main.py`、`backend/app/models/`、"
                "`backend/app/services/`、`backend/app/api/v1/`、`backend/requirements.txt`）\n"
                "- 前端文件 → `frontend/`（`frontend/src/App.tsx`、`frontend/package.json`）\n"
                "- 测试文件 → `tests/`\n"
                "- 部署配置 → `deploy/`\n"
                "- 文档/架构图 → `docs/`（Mermaid 图表用 ```mermaid docs/architecture.md 格式）\n\n"
                "**语义化文件名**：`todo_service.py` ✅ / `code_1.py` ❌ / `snippet_1.txt` ❌\n"
                "**相对路径**：file-ops 工具的 path 参数必须使用相对路径。"
            )

        # 5. Supervisor guidance
        if ctx["supervisor_guidance"]:
            parts.append(f"\n## Supervisor 指导\n{ctx['supervisor_guidance']}")

        # 6. Constraints
        if ctx["constraints"]:
            parts.append("\n## 约束")
            for c in ctx["constraints"]:
                parts.append(f"- {c}")

        # 6b. Retry feedback (Route B — review feedback for retry)
        if ctx.get("retry_feedback"):
            parts.append(f"\n## ⚠️ 审核反馈（请针对性修改）\n{ctx['retry_feedback']}")

        # 7. Peer messages (M8)
        if ctx["agent_messages"]:
            parts.append("\n## 来自其他 Agent 的消息")
            for msg in ctx["agent_messages"]:
                msg_type = msg.get("type", "share")
                from_agent = msg.get("from", "?")
                content = msg.get("content", "")
                prefix = {"challenge": "⚡", "share": "📢", "question": "❓", "response": "💬"}.get(msg_type, "📌")
                parts.append(f"{prefix} [{msg_type}] {from_agent}: {content}")

        # 8. Output instruction
        parts.append("\n## 输出要求")
        parts.append("请直接输出完整的代码实现。你可以使用 file-ops 工具写入工作区文件。")

        return "\n".join(parts)

    def format_files_summary(self, files: list[dict]) -> str:
        """Format file changes for display."""
        if not files:
            return ""
        summary = f"\n## 文件变更 ({len(files)} files)\n"
        for f in files:
            status = "+ new" if f.get("status") == "created" else "~ mod"
            meta = f.get("meta", "")
            summary += f"- `{f['name']}` {status} {meta}\n"
        return summary

    def estimate_tokens(self, ctx: WorkerContext) -> int:
        """Rough token count estimate (chars / 4)."""
        formatted = self.format_context(ctx)
        return len(formatted) // 4


# ── Module-level singleton ──

context_pipeline = ContextPipeline()
