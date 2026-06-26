"""Skill Executor — 从文件系统加载 Skill → 注入 Prompt → 执行 LLM → 验证输出"""

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill import Skill
from app.services.skill_registry import parse_skill_md, parse_config_yaml

logger = logging.getLogger(__name__)

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"


class SkillExecutionError(Exception):
    pass


class SkillExecutor:
    """Skill 执行器 — 从文件系统读取 SKILL.md 并执行"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _read_skill_files(self, skill: Skill) -> dict:
        """从文件系统读取 skill 的 SKILL.md + config.yaml"""
        skill_dir = SKILLS_ROOT / skill.path.replace("skills/", "", 1)
        result = {"skill_md": "", "config_yaml": None}

        md_path = skill_dir / "SKILL.md"
        if md_path.exists():
            result["skill_md"] = md_path.read_text(encoding="utf-8")

        config_path = skill_dir / "config.yaml"
        if config_path.exists():
            result["config_yaml"] = config_path.read_text(encoding="utf-8")

        return result

    async def load_skill(self, skill_id: uuid.UUID) -> dict:
        """加载并解析 Skill"""
        skill = await self.db.get(Skill, skill_id)
        if not skill:
            raise SkillExecutionError(f"Skill {skill_id} not found")

        files = self._read_skill_files(skill)
        parsed_md = parse_skill_md(files["skill_md"]) if files["skill_md"] else {}
        config = parse_config_yaml(files["config_yaml"]) if files["config_yaml"] else {}

        fm = parsed_md.get("frontmatter", {})

        return {
            "id": str(skill.id),
            "name": skill.name,
            "version": skill.version,
            "description": skill.description or "",
            "instructions": parsed_md.get("instructions", ""),
            "output_format": parsed_md.get("output_format", ""),
            "parameters": config.get("parameters", []),
            "trigger": config.get("trigger", {}),
        }

    def build_skill_prompt(
        self,
        skill: dict,
        user_input: str,
        context: Optional[str] = None,
    ) -> str:
        """构建 Skill 执行的 Prompt"""
        parts = []

        parts.append(f"# 技能: {skill['name']}")
        if skill["description"]:
            parts.append(f"描述: {skill['description']}")
        parts.append("")

        if skill["instructions"]:
            parts.append("## 执行指令")
            parts.append(skill["instructions"])
            parts.append("")

        if skill["parameters"]:
            parts.append("## 输入参数")
            for param in skill["parameters"]:
                name = param.get("name", "")
                desc = param.get("description", "")
                required = "必填" if param.get("required", False) else "选填"
                parts.append(f"- **{name}** ({required}): {desc}")
            parts.append("")

        if skill["output_format"]:
            parts.append("## 输出格式要求")
            parts.append(skill["output_format"])
            parts.append("")

        if context:
            parts.append("## 参考资料")
            parts.append(context)
            parts.append("")

        parts.append("## 用户输入")
        parts.append(user_input)

        return "\n".join(parts)

    def validate_output(self, skill: dict, output: str) -> tuple[bool, Optional[str]]:
        """验证 Skill 输出"""
        output_format = skill.get("output_format", "")
        if not output_format:
            return True, None

        if "json" in output_format.lower():
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', output, re.DOTALL)
            if json_match:
                try:
                    json.loads(json_match.group(1).strip())
                except json.JSONDecodeError as e:
                    return False, f"JSON 格式错误: {e}"
            elif "{" in output and "}" in output:
                try:
                    json.loads(output)
                except json.JSONDecodeError:
                    pass

        required_sections = re.findall(r'##+\s*(.+)', output_format)
        for section in required_sections:
            if section.strip().lower() not in output.lower():
                logger.info(f"Skill output missing section: {section}")

        return True, None

    async def execute_skill(
        self,
        skill_id: uuid.UUID,
        user_input: str,
        context: Optional[str] = None,
        mock: bool = False,
    ) -> dict:
        """执行 Skill"""
        from app.adapters.llm.base import LLMConfig
        from app.adapters.llm.litellm_adapter import LiteLLMAdapter
        from app.adapters.llm.mock_adapter import MockLLMAdapter

        skill = await self.load_skill(skill_id)
        logger.info(f"Executing skill: {skill['name']} v{skill['version']}")

        skill_prompt = self.build_skill_prompt(skill, user_input, context)

        messages = [
            {
                "role": "system",
                "content": (
                    f"你是一个专业的 AI 助手，正在执行技能「{skill['name']}」。\n"
                    "请严格按照技能的执行指令和输出格式要求来完成任务。"
                ),
            },
            {"role": "user", "content": skill_prompt},
        ]

        if mock:
            adapter = MockLLMAdapter()
            config = LLMConfig(model="mock", provider="mock", api_key="mock")
        else:
            adapter = LiteLLMAdapter()
            from app.core.config import get_settings
            settings = get_settings()
            config = LLMConfig(
                model="deepseek-chat",
                provider="deepseek",
                api_key=settings.DEEPSEEK_API_KEY,
                temperature=0.3,
            )

        response = await adapter.chat(messages=messages, config=config)
        is_valid, validation_error = self.validate_output(skill, response.content)

        return {
            "skill_name": skill["name"],
            "skill_version": skill["version"],
            "output": response.content,
            "is_valid": is_valid,
            "validation_error": validation_error,
            "model": response.model,
            "provider": response.provider,
            "usage": response.usage,
            "latency": response.latency,
        }

    async def match_skill(self, user_input: str) -> Optional[dict]:
        """根据用户输入匹配最合适的 Skill"""
        result = await self.db.execute(
            select(Skill).order_by(Skill.created_at)
        )
        skills = list(result.scalars().all())

        best_match = None
        best_score = 0
        input_lower = user_input.lower()

        for skill in skills:
            files = self._read_skill_files(skill)
            config = parse_config_yaml(files["config_yaml"]) if files["config_yaml"] else {}
            trigger = config.get("trigger", {})
            keywords = trigger.get("keywords", [])

            score = sum(1 for kw in keywords if kw.lower() in input_lower)

            if score > best_score:
                best_score = score
                best_match = skill

        if best_match and best_score > 0:
            best_files = self._read_skill_files(best_match)
            best_config = parse_config_yaml(best_files["config_yaml"]) if best_files["config_yaml"] else {}
            best_keywords = best_config.get("trigger", {}).get("keywords", [])
            return {
                "skill_id": str(best_match.id),
                "skill_name": best_match.name,
                "match_score": best_score,
                "matched_keywords": [
                    kw for kw in best_keywords if kw.lower() in input_lower
                ],
            }

        return None
