"""Prompt Builder：统一组装 system + memory + RAG + skill + taskstate"""

from typing import Optional


class PromptBuilder:
    """统一的 Prompt 构建器：按层级组装上下文"""

    def __init__(self):
        self._sections: list[tuple[int, str, str]] = []  # (priority, title, content)

    def add_persona(self, system_prompt: str) -> "PromptBuilder":
        """添加角色系统提示（最高优先级）"""
        if system_prompt:
            self._sections.append((10, "角色定义", system_prompt))
        return self

    def add_memory(self, memory_parts: list[str]) -> "PromptBuilder":
        """添加记忆上下文"""
        if memory_parts:
            content = "\n".join(memory_parts)
            self._sections.append((30, "相关记忆", content + "\n\n请参考以上记忆来回答用户的问题。"))
        return self

    def add_rag(self, rag_parts: list[str]) -> "PromptBuilder":
        """添加 RAG 检索结果"""
        if rag_parts:
            content = "\n".join(rag_parts)
            self._sections.append((40, "知识库检索结果", content + "\n\n请参考以上知识库内容来辅助回答。"))
        return self

    def add_skill(self, skill_prompt: str) -> "PromptBuilder":
        """添加 Skill 执行指令"""
        if skill_prompt:
            self._sections.append((20, "技能指令", skill_prompt))
        return self

    def add_task_state(self, task_description: str, step: Optional[str] = None) -> "PromptBuilder":
        """添加任务状态（SOP 执行进度）"""
        if task_description:
            content = f"当前任务: {task_description}"
            if step:
                content += f"\n当前步骤: {step}"
            self._sections.append((50, "任务状态", content))
        return self

    def add_custom(self, title: str, content: str, priority: int = 60) -> "PromptBuilder":
        """添加自定义段落"""
        if content:
            self._sections.append((priority, title, content))
        return self

    def build(self) -> str:
        """按优先级排序并组装完整 system prompt"""
        if not self._sections:
            return "你是一个有用的 AI 助手。"

        # 按 priority 排序（数字越小越靠前）
        sorted_sections = sorted(self._sections, key=lambda x: x[0])

        parts = []
        for _, title, content in sorted_sections:
            # 角色定义不加标题前缀
            if title == "角色定义":
                parts.append(content)
            else:
                parts.append(f"\n## {title}\n{content}")

        return "\n".join(parts)

    def reset(self) -> "PromptBuilder":
        """清空所有段落"""
        self._sections.clear()
        return self


def build_full_messages(
    system_prompt: str,
    user_message: str,
    memory_parts: Optional[list[str]] = None,
    rag_parts: Optional[list[str]] = None,
    skill_prompt: Optional[str] = None,
    task_description: Optional[str] = None,
    task_step: Optional[str] = None,
    history: Optional[list[dict]] = None,
) -> list[dict]:
    """一次性构建完整的消息列表

    Returns:
        组装后的 messages 列表
    """
    builder = PromptBuilder()
    builder.add_persona(system_prompt)
    builder.add_skill(skill_prompt or "")
    builder.add_memory(memory_parts or [])
    builder.add_rag(rag_parts or [])
    builder.add_task_state(task_description or "", task_step)

    full_system = builder.build()

    messages = [{"role": "system", "content": full_system}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_message})

    return messages
