"""Agent Chat Stream：流式 Agent 对话，边思考边推送"""
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Optional, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.model import Model
from app.models.persona import Persona
from app.models.tool import Tool
from app.adapters.llm.base import LLMConfig
from app.adapters.llm.litellm_adapter import LiteLLMAdapter

logger = logging.getLogger(__name__)


class StreamEvent(TypedDict):
    """流式事件"""
    type: str  # "thinking_token" | "content_token" | "tool_call" | "done"
    token: str  # token content
    agent_name: str  # agent name


async def agent_chat_stream(
    db: AsyncSession,
    agent: Agent,
    message: str,
    history: Optional[list[dict]] = None,
    team_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AsyncGenerator[StreamEvent, None]:
    """流式 Agent 对话：边调用 LLM 边 yield token 事件

    返回结构:
    - {"type": "thinking_token", "token": "...", "agent_name": "xxx"}  # 思考过程token
    - {"type": "content_token", "token": "...", "agent_name": "xxx"}   # 回复内容token
    - {"type": "tool_call", "tool": "name", "params": {...}, "agent_name": "xxx"}  # 工具调用
    - {"type": "done", "content": "full_content", "thinking": "...", "latency": 1.2}  # 完成
    """
    from app.services.context_manager import ContextManager
    from app.services.agent_factory import build_system_prompt, resolve_api_key

    persona = await db.get(Persona, agent.persona_id)
    default_model = await db.get(Model, agent.default_model_id)
    if not persona or not default_model:
        raise ValueError("Agent's persona or model not found")

    # 加载工具
    tools = []
    if agent.tools:
        for tid in agent.tools:
            tool = await db.get(Tool, uuid.UUID(tid))
            if tool:
                tools.append(tool)

    # 构建 system prompt
    system_prompt = await build_system_prompt(db, persona, tools, message)

    # 注入上下文
    context_mgr = ContextManager(db)
    messages, ctx_stats = await context_mgr.build_prompt_context(
        agent=agent,
        system_prompt=system_prompt,
        user_message=message,
        history=history,
        team_id=team_id,
    )

    api_key = await resolve_api_key(db, default_model)
    config = LLMConfig(
        model=default_model.model_name,
        provider=default_model.provider,
        api_key=api_key,
    )
    adapter = LiteLLMAdapter()

    t0 = time.time()
    full_content = ""
    full_thinking = ""
    current_section = "content"  # "thinking" or "content"

    try:
        kwargs = dict(
            model=adapter._build_model_str(config.provider, config.model),
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
            stream=True,
            timeout=120,
        )
        api_base = adapter._get_api_base(config.provider)
        if api_base:
            kwargs["api_base"] = api_base

        # zhipu thinking mode
        if config.provider == "zhipu":
            kwargs["thinking"] = {"type": "enabled"}

        from litellm import acompletion
        response = await acompletion(**kwargs)

        async for chunk in response:
            delta = chunk.choices[0].delta

            # 检查 thinking/reasoning content
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                thinking_token = delta.reasoning_content
                if isinstance(thinking_token, str):
                    full_thinking += thinking_token
                    yield {"type": "thinking_token", "token": thinking_token, "agent_name": agent.name}

            elif hasattr(delta, 'thinking') and delta.thinking:
                thinking_token = delta.thinking
                if isinstance(thinking_token, str):
                    full_thinking += thinking_token
                    yield {"type": "thinking_token", "token": thinking_token, "agent_name": agent.name}

            # 检查 normal content
            elif delta.content:
                token = delta.content
                if isinstance(token, str):
                    full_content += token
                    # 不要流式显示 tool call JSON，用 "正在处理..." 替代
                    if full_content.lstrip().startswith('{"tool_call"') or full_content.lstrip().startswith('```json'):
                        pass  # 跳过 tool call JSON 的流式显示
                    else:
                        yield {"type": "content_token", "token": token, "agent_name": agent.name}

        # 检测并执行工具调用
        tool_results = []
        tool_call = _extract_tool_call(full_content)
        if tool_call:
            from app.tools.tool_executor import tool_executor
            logger.info(f"Tool call detected: {tool_call['name']}")
            # 通知前端正在执行工具（替换掉之前stream的JSON）
            yield {
                "type": "tool_call",
                "tool": tool_call["name"],
                "params": {k: (str(v)[:100] if isinstance(v, str) else v) for k, v in tool_call.get("params", {}).items()},
                "agent_name": agent.name,
            }
            tr = await tool_executor.execute(tool_call["name"], tool_call["params"], session_id=session_id)
            tool_results.append({
                "tool": tool_call["name"],
                "success": tr.success,
                "output": tr.output[:500] if tr.output else "",
                "error": tr.error,
            })
            logger.info(f"Tool {tool_call['name']}: success={tr.success}")

            # 工具结果反馈给 LLM 生成最终摘要
            messages.append({"role": "assistant", "content": full_content})
            messages.append({
                "role": "user",
                "content": f"工具执行结果:\n{json.dumps(tool_results[-1], ensure_ascii=False, indent=2)}\n\n请简要概述执行结果（50字内）。",
            })
            response2 = await adapter._call_with_retry(messages, config)
            full_content = response2.content or f"✅ 工具执行完成：{tool_call['name']}"
            full_thinking = full_thinking or (response2.thinking or "")

        latency = time.time() - t0

        # 保存对话记忆
        from app.services.memory_manager import MemoryManager
        memory_mgr = MemoryManager(db)
        await memory_mgr.save_dialog_memory(
            agent_id=agent.id,
            team_id=uuid.UUID(team_id) if team_id else None,
            user_message=message,
            assistant_message=full_content,
            session_id=session_id,
        )

        yield {
            "type": "done",
            "content": full_content,
            "thinking": full_thinking,
            "latency": round(latency, 2),
            "model": default_model.model_name,
            "tool_results": tool_results,
        }

    except Exception as e:
        logger.error(f"agent_chat_stream failed for {agent.name}: {e}")
        yield {"type": "done", "content": full_content or "", "thinking": full_thinking or "", "latency": 0, "error": str(e)}


def _extract_tool_call(content: str) -> Optional[dict]:
    """从 LLM 回复中提取工具调用 JSON"""
    import json
    try:
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            json_str = content[start:end].strip()
        elif '{"tool_call"' in content:
            start = content.index('{"tool_call"')
            depth = 0
            end = start
            for i, c in enumerate(content[start:], start):
                if c == "{": depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            json_str = content[start:end]
        else:
            return None
        parsed = json.loads(json_str)
        if "tool_call" in parsed:
            return parsed["tool_call"]
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return None
