#!/usr/bin/env python3
"""The Boy Assistant - Development CLI"""

import asyncio
import json
import click

from app.adapters.llm.base import LLMConfig
from app.adapters.llm.litellm_adapter import LiteLLMAdapter
from app.adapters.llm.mock_adapter import MockLLMAdapter
from app.core.config import get_settings
from app.core.database import async_session
from app.services.agent_factory import agent_chat

# Provider -> env key mapping
PROVIDER_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "CLAUDE_API_KEY",
    "google": "GEMINI_API_KEY",
    "zhipu": "GLM_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

PROVIDER_DEFAULT_MODEL = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "google": "gemini-2.0-flash",
    "zhipu": "glm-4-flash",
    "deepseek": "deepseek-chat",
}

# In-memory session store for multi-turn conversations
_sessions: dict[str, list[dict]] = {}


def _resolve_api_key(provider: str) -> str:
    settings = get_settings()
    env_key = PROVIDER_KEY_MAP.get(provider)
    if not env_key:
        return ""
    return getattr(settings, env_key, "")


def _color(text: str, color: str) -> str:
    """Simple ANSI color"""
    colors = {
        "green": "\033[92m", "blue": "\033[94m", "yellow": "\033[93m",
        "red": "\033[91m", "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"


@click.group()
def cli():
    """The Boy Assistant 开发 CLI"""
    pass


# ── Week 1 commands ──────────────────────────────────────

@cli.command()
@click.argument("message")
@click.option("--model", default=None, help="模型名称")
@click.option("--provider", default="deepseek", help="Provider")
@click.option("--mock", is_flag=True, help="使用 Mock 模式")
@click.option("--stream", is_flag=True, help="流式输出")
def chat(message: str, model: str, provider: str, mock: bool, stream: bool):
    """直接发送消息给 LLM（无 Agent 上下文）"""
    if model is None:
        model = PROVIDER_DEFAULT_MODEL.get(provider, "gpt-4o")

    adapter = MockLLMAdapter() if mock else LiteLLMAdapter()
    api_key = "mock" if mock else _resolve_api_key(provider)
    config = LLMConfig(model=model, provider=provider, api_key=api_key)

    async def run():
        if stream:
            async for chunk in adapter.chat_stream(
                messages=[{"role": "user", "content": message}], config=config
            ):
                click.echo(chunk, nl=False)
            click.echo()
        else:
            response = await adapter.chat(
                messages=[{"role": "user", "content": message}], config=config
            )
            click.echo(f"\n[{response.provider}/{response.model}]")
            click.echo(response.content)
            click.echo(f"\n⏱ {response.latency:.2f}s | Tokens: {response.usage}")

    asyncio.run(run())


@cli.command()
@click.option("--provider", default="deepseek", help="Provider")
@click.option("--model", default=None, help="模型名称")
@click.option("--mock", is_flag=True, help="使用 Mock 模式")
def test(provider: str, model: str, mock: bool):
    """测试 API 连通性"""
    if model is None:
        model = PROVIDER_DEFAULT_MODEL.get(provider, "gpt-4o")

    adapter = MockLLMAdapter() if mock else LiteLLMAdapter()
    api_key = "mock" if mock else _resolve_api_key(provider)
    config = LLMConfig(model=model, provider=provider, api_key=api_key)

    async def run():
        click.echo(f"Testing {provider}/{model}...")
        if mock:
            click.echo("✅ Mock mode - always healthy")
            return
        healthy = await adapter.check_health(config)
        if healthy:
            click.echo(f"✅ {provider}/{model} connected")
        else:
            click.echo(f"❌ {provider}/{model} connection failed")

    asyncio.run(run())


# ── Week 2 commands ──────────────────────────────────────

@cli.command()
@click.argument("agent_name")
@click.argument("message")
@click.option("--stream", is_flag=True, help="流式输出")
@click.option("--verbose", is_flag=True, help="显示 Token 和耗时")
@click.option("--session", "session_id", default=None, help="会话 ID（多轮对话）")
@click.option("--team", "team_id", default=None, help="团队 ID")
@click.option("--mock", is_flag=True, help="Mock 模式")
def agent(agent_name: str, message: str, stream: bool, verbose: bool, session_id: str, team_id: str, mock: bool):
    """与 Agent 对话：agent <name> <message>"""
    async def run():
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.agent import Agent
            result = await db.execute(select(Agent).where(Agent.name == agent_name))
            agent_obj = result.scalar_one_or_none()

            if not agent_obj:
                click.echo(_color(f"Agent '{agent_name}' not found", "red"))
                return

            click.echo(_color(f"[{agent_name}]", "bold") + " thinking...")

            # Load history
            sid = session_id or "default"
            key = f"{agent_name}:{sid}"
            history = _sessions.get(key, [])

            result = await agent_chat(
                db=db,
                agent=agent_obj,
                message=message,
                history=history,
                mock=mock,
                team_id=team_id,
                session_id=sid,
            )

            # Display routing info if verbose
            if verbose:
                routing = result.get("routing", {})
                if routing:
                    complexity = routing.get("complexity", "?")
                    routed = routing.get("routed_model", "?")
                    fallback = " (fallback)" if routing.get("fallback_used") else ""
                    click.echo(_color(
                        f"🔀 模型路由: {complexity} → {routed}{fallback}",
                        "yellow"
                    ))

                ctx_stats = result.get("context_stats", {})
                mem = ctx_stats.get("memory", {})
                if mem:
                    click.echo(_color(
                        f"🧠 注入上下文：L1({mem.get('L1', 0)}条) "
                        f"L2({mem.get('L2', 0)}条) "
                        f"L3({mem.get('L3', 0)}条) "
                        f"L4({mem.get('L4', 0)}条) "
                        f"总计 Token:{mem.get('total_tokens', 0)}",
                        "cyan"
                    ))

            # Display tool calls
            for tr in result.get("tool_results", []):
                click.echo(_color(f"[tool] {tr['tool']}({json.dumps(tr['params'], ensure_ascii=False)})", "yellow"))
                if tr["success"]:
                    output = tr["output"][:500]
                    click.echo(f"  {output}")
                else:
                    click.echo(_color(f"  ERROR: {tr['error']}", "red"))

            click.echo()
            click.echo(_color(f"[{agent_name}]", "bold") + " " + result["content"])

            if verbose:
                click.echo()
                click.echo(_color(
                    f"⏱ {result['latency']:.2f}s | "
                    f"{result['provider']}/{result['model']} | "
                    f"Tokens: {result['usage']}",
                    "cyan"
                ))

            # Save history
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": result["content"]})
            _sessions[key] = history

    asyncio.run(run())


@cli.command("agent-list")
def agent_list():
    """列出所有 Agent 及状态"""
    async def run():
        async with async_session() as db:
            from app.services.agent_factory import list_agents
            agents = await list_agents(db)
            if not agents:
                click.echo("No agents found.")
                return
            for a in agents:
                sc = {"idle": "green", "busy": "yellow", "error": "red"}.get(a.status, "")
                click.echo(f"  {_color(a.status, sc)}  {a.name}  ({a.id})")
    asyncio.run(run())


@cli.command("tool-test")
@click.argument("tool_name")
@click.argument("params_json")
def tool_test(tool_name: str, params_json: str):
    """测试工具调用：tool-test <name> '<json params>'"""
    from app.tools.tool_executor import tool_executor

    async def run():
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            click.echo(_color("Invalid JSON", "red"))
            return

        click.echo(f"Executing {tool_name}...")
        result = await tool_executor.execute(tool_name, params)
        if result.success:
            click.echo(_color("Success", "green"))
            click.echo(result.output)
        else:
            click.echo(_color("Failed", "red"))
            click.echo(result.error)

    asyncio.run(run())


# ── Week 3 commands ──────────────────────────────────────

@cli.command("memory")
@click.argument("agent_name")
@click.option("--team", "team_id", default=None, help="团队 ID")
def memory_view(agent_name: str, team_id: str):
    """查看 Agent 的四层记忆视图：memory <agent_name> --team <team_id>"""
    async def run():
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.agent import Agent
            from app.services.memory_manager import MemoryManager

            result = await db.execute(select(Agent).where(Agent.name == agent_name))
            agent_obj = result.scalar_one_or_none()
            if not agent_obj:
                click.echo(_color(f"Agent '{agent_name}' not found", "red"))
                return

            mgr = MemoryManager(db)
            import uuid
            team_uuid = uuid.UUID(team_id) if team_id else None
            view = await mgr.get_agent_view(agent_obj.id, team_uuid)

            click.echo()
            team_label = f"（团队：{team_id}）" if team_id else ""
            click.echo(_color(f"📚 {agent_name} 的记忆视图{team_label}", "bold"))
            click.echo()

            layers = [
                ("L1 System", view["L1_system"], "green"),
                ("L2 Team", view["L2_team"], "blue"),
                ("L3 Agent Global", view["L3_agent_global"], "yellow"),
                ("L4 Context", view["L4_context"], "cyan"),
            ]

            type_icons = {
                "decision": "🔵",
                "standard": "⚪",
                "context": "🟡",
                "conclusion": "🟣",
                "warning": "🔴",
            }

            for i, (label, memories, color) in enumerate(layers):
                prefix = "├──" if i < 3 else "└──"
                click.echo(f"{prefix} {_color(f'{label} ({len(memories)})', color)}")

                for j, m in enumerate(memories[:10]):
                    icon = type_icons.get(m.type, "⚪")
                    is_last = (j == len(memories[:10]) - 1)
                    sub_prefix = "│   └──" if not is_last and i < 3 else "    └──"
                    content_preview = m.content[:80].replace("\n", " ")
                    click.echo(f"{sub_prefix} {icon} {m.type}: {content_preview}")

                if len(memories) > 10:
                    click.echo(f"    ... 还有 {len(memories) - 10} 条")

            total = sum(len(m) for _, m, _ in layers)
            click.echo()
            click.echo(f"总计 {total} 条记忆")

    asyncio.run(run())


# ── Week 5 commands ──────────────────────────────────────

@cli.command("skill-exec")
@click.argument("skill_name")
@click.argument("user_input")
@click.option("--mock", is_flag=True, help="Mock 模式")
def skill_exec(skill_name: str, user_input: str, mock: bool):
    """执行 Skill：skill-exec <name> '<input>'"""
    async def run():
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.skill import Skill
            from app.services.skill_executor import SkillExecutor

            result = await db.execute(select(Skill).where(Skill.name == skill_name))
            skill = result.scalar_one_or_none()
            if not skill:
                click.echo(_color(f"Skill '{skill_name}' not found", "red"))
                return

            executor = SkillExecutor(db)
            click.echo(_color(f"Executing skill: {skill.name} v{skill.version}", "bold"))

            result = await executor.execute_skill(
                skill_id=skill.id,
                user_input=user_input,
                mock=mock,
            )

            click.echo()
            status_icon = "✅" if result["is_valid"] else "⚠️"
            click.echo(_color(f"[{result['skill_name']}]", "bold") + " " + status_icon)
            click.echo(result["output"][:2000])

            click.echo()
            click.echo(_color(
                f"⏱ {result.get('latency', 0):.2f}s | "
                f"{result.get('provider', '?')}/{result.get('model', '?')} | "
                f"Valid: {result['is_valid']} | "
                f"Tokens: {result.get('usage', {})}",
                "cyan"
            ))

            if result.get("validation_error"):
                click.echo(_color(f"⚠ Validation: {result['validation_error']}", "yellow"))

    asyncio.run(run())


@cli.command("skill-match")
@click.argument("user_input")
def skill_match(user_input: str):
    """匹配最合适的 Skill：skill-match '<input>'"""
    async def run():
        async with async_session() as db:
            from app.services.skill_executor import SkillExecutor

            executor = SkillExecutor(db)
            match = await executor.match_skill(user_input)

            if not match:
                click.echo("No matching skill found.")
                return

            click.echo(_color(f"Matched: {match['skill_name']}", "green"))
            click.echo(f"  Score: {match['match_score']}")
            click.echo(f"  Keywords: {match['matched_keywords']}")

    asyncio.run(run())


@cli.command("route-test")
@click.argument("message")
def route_test(message: str):
    """测试模型路由：route-test '<message>'"""
    async def run():
        async with async_session() as db:
            from app.services.model_router import ModelRouter
            from app.models.model import Model
            from sqlalchemy import select

            router = ModelRouter(db)
            complexity = await router.classify_complexity(message)

            # Get first model as default
            result = await db.execute(select(Model).limit(1))
            default_model = result.scalar_one_or_none()

            click.echo(_color(f"复杂度: {complexity.value}", "bold"))

            if default_model:
                selected = await router.select_model(complexity, default_model.id)
                click.echo(f"  默认模型: {default_model.model_name} ({default_model.provider})")
                click.echo(f"  选择模型: {selected.model_name} ({selected.provider})")

                if str(selected.id) != str(default_model.id):
                    click.echo(_color("  → 路由切换!", "yellow"))
                else:
                    click.echo("  → 使用默认模型")

    asyncio.run(run())


@cli.command("condition-test")
@click.argument("expression")
@click.option("--var", "variables", multiple=True, help="上下文变量 key=value")
def condition_test(expression: str, variables: tuple):
    """测试条件路由：condition-test 'score > 5' --var score=8"""
    from app.services.condition_router import ConditionRouter

    router = ConditionRouter()
    context = {}
    for v in variables:
        if "=" in v:
            k, val = v.split("=", 1)
            # Try to parse as number
            try:
                val = float(val) if "." in val else int(val)
            except ValueError:
                pass
            context[k] = val

    result = router.evaluate(expression, context)
    click.echo(f"Expression: {expression}")
    click.echo(f"Context: {context}")
    click.echo(_color(f"Result: {result}", "green" if result else "red"))


if __name__ == "__main__":
    cli()
