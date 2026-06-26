"""Agent Factory：Agent 组装工具（Prompt 构建 + API Key 解析）

CRUD 已移至 agent_service.py，对话执行已移至 agent_chat.py。
本文件保留：build_system_prompt, build_tool_descriptions, resolve_api_key
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from app.models.persona import Persona
from app.models.tool import Tool

logger = logging.getLogger(__name__)


def build_tool_descriptions(tools: list[Tool]) -> str:
    """生成工具描述（OpenAI function calling 格式）"""
    if not tools:
        return ""
    descriptions = []
    for tool in tools:
        desc = f"- **{tool.name}**: {tool.description or 'No description'}"
        if tool.param_schema:
            params = tool.param_schema.get("properties", {})
            required = tool.param_schema.get("required", [])
            param_str = ", ".join(
                f"{k}{'(required)' if k in required else '(optional)'}"
                for k in params
            )
            desc += f"\n  Parameters: {param_str}"
        descriptions.append(desc)
    return "\n".join(descriptions)


async def build_system_prompt(
    db: AsyncSession,
    persona: Persona,
    tools: list[Tool],
    user_message: str = "",
) -> str:
    """构建完整 system prompt：使用 prompt_template 变量替换 + 工具声明

    优先使用 prompt_template，替换所有变量；fallback 到 system_prompt（向后兼容）
    """
    template = (persona.prompt_template or "").strip()

    if template:
        # ── 解析技能（注入完整指令，使 skill 真正引导产出结构）──
        skill_text = "(未配置)"
        if persona.skill_ids:
            from app.models.skill import Skill
            from app.services.skill_registry import parse_skill_md, SKILLS_ROOT

            skill_blocks = []
            for sid in persona.skill_ids:
                try:
                    skill = await db.get(Skill, uuid.UUID(sid))
                    if not skill:
                        continue
                    # 读取完整 SKILL.md 指令（文件系统是 source of truth）
                    instructions = ""
                    try:
                        md_path = SKILLS_ROOT / skill.path.replace("skills/", "", 1) / "SKILL.md"
                        if md_path.exists():
                            parsed = parse_skill_md(md_path.read_text(encoding="utf-8"))
                            instructions = (parsed.get("instructions") or "").strip()
                    except Exception:
                        pass
                    if instructions:
                        skill_blocks.append(
                            f"### 技能：{skill.name}\n{skill.description or ''}\n\n"
                            f"**你必须严格遵循以下技能的输出结构与工作守则来完成任务：**\n\n{instructions}"
                        )
                    else:
                        skill_blocks.append(f"- {skill.name}: {skill.description or ''}")
                except Exception:
                    pass
            if skill_blocks:
                skill_text = (
                    "你已装备以下技能。执行任务时**必须主动应用**对应技能的输出结构，"
                    "确保产出完整、专业、可直接交付的文档/方案，而非笼统摘要：\n\n"
                    + "\n\n".join(skill_blocks)
                )

        # ── 解析 MCP 服务器名称 ──
        server_text = "(未配置)"
        if persona.mcp_server_ids:
            from app.models.mcp_server import MCPServer

            server_names = []
            for sid in persona.mcp_server_ids:
                try:
                    server = await db.get(MCPServer, uuid.UUID(sid))
                    if server:
                        server_names.append(f"- {server.name} ({server.transport})")
                except Exception:
                    pass
            if server_names:
                server_text = "\n".join(server_names)

        # ── 变量替换 ──
        prompt = template
        prompt = prompt.replace("{role}", persona.role or "")
        prompt = prompt.replace("{expertise}", persona.expertise or "")
        prompt = prompt.replace("{constraints}", persona.constraints or "")
        prompt = prompt.replace("{output_format}", persona.output_format or "")
        prompt = prompt.replace("{skills}", skill_text)
        prompt = prompt.replace("{mcp_servers}", server_text)
        prompt = prompt.replace("{task}", user_message or "{用户任务}")
    else:
        # 向后兼容：没有 prompt_template 时使用 system_prompt
        prompt = persona.system_prompt or ""

    # ── 附加工具声明 ──
    tool_desc = build_tool_descriptions(tools)
    if tool_desc:
        prompt += (
            f"\n\n## 可用工具\n\n"
            f"你有以下工具可用。**必须通过工具调用来执行实际操作**，不能虚构结果：\n"
            f"{tool_desc}\n\n"
            f"**❗️ 工具调用规则（必须严格遵守）**：\n"
            f"1. 如果你需要读写文件、列出目录等操作，**必须**使用 TOOL_CALL 指令\n"
            f"2. **严禁虚构**：没有调用工具时，绝对不能说\"文件已创建\"、\"文件已读取\"等\n"
            f"3. 工具调用格式（放在回复最后，单独一行）：\n"
            f"   TOOL_CALL: {{\"name\": \"file-ops\", \"params\": {{\"operation\": \"write\", \"path\": \"文件名\", \"content\": \"内容\"}}}}\n"
            f"4. 工具执行结果会在下一轮对话中告诉你，然后你再回复用户\n"
            f"5. 始终用自然语言回复用户，使用 Markdown 格式。回复要简洁、结构化"
        )

    return prompt


async def resolve_api_key(db: AsyncSession, model: Model) -> str:
    """解析模型 API Key：优先加密存储 → 环境变量"""
    from app.core.security import decrypt_api_key
    from app.core.config import get_settings

    if model.api_key_ref:
        try:
            return decrypt_api_key(model.api_key_ref)
        except Exception:
            pass

    settings = get_settings()
    env_map = {
        "openai": settings.OPENAI_API_KEY,
        "anthropic": settings.CLAUDE_API_KEY,
        "google": settings.GEMINI_API_KEY,
        "zhipu": settings.GLM_API_KEY,
        "deepseek": settings.DEEPSEEK_API_KEY,
    }
    return env_map.get(model.provider, "")


# ── 向后兼容：重新导出 agent_chat ───────────────────────
from app.services.agent_chat import agent_chat  # noqa: E402

# ── 向后兼容：重新导出 CRUD 函数 ─────────────────────────
from app.services.agent_service import (  # noqa: E402, F401
    create_agent,
    get_agent,
    list_agents,
    update_agent,
    delete_agent,
)
