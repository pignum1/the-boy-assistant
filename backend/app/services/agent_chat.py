"""Agent Chat：Agent 对话执行（Prompt 组装 → LLM 调用 → 工具执行 → 记忆存储）"""

import json
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.model import Model
from app.models.persona import Persona
from app.models.tool import Tool
from app.adapters.llm.base import LLMConfig
from app.adapters.llm.litellm_adapter import LiteLLMAdapter
from app.adapters.llm.mock_adapter import MockLLMAdapter
from app.tools.tool_executor import tool_executor
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)


async def agent_chat(
    db: AsyncSession,
    agent: Agent,
    message: str,
    history: Optional[list[dict]] = None,
    mock: bool = False,
    team_id: Optional[str] = None,
    session_id: Optional[str] = None,
    use_router: bool = True,
    use_fallback: bool = True,
    return_reasoning: bool = False,
    save_memory: bool = True,
) -> dict:
    """执行 Agent 对话：组装 Prompt → 模型路由 → LLM 调用 → 工具执行 → 记忆存储

    return_reasoning=True 时，返回额外字段 reasoning，包含：
    - model_routing: 复杂度评估 + 路由决策 + 路由原因
    - tool_calls: 工具调用详情（工具名、参数、结果、耗时）
    - context_used: 上下文使用统计（记忆数、RAG chunk 数、token 总量）
    """
    from app.services.context_manager import ContextManager
    from app.services.memory_manager import MemoryManager
    from app.services.model_router import ModelRouter
    from app.services.fallback_chain import FallbackChain
    from app.services.agent_factory import build_system_prompt, resolve_api_key

    # 加载关联数据
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

    # 注入上下文（记忆 + RAG）
    context_mgr = ContextManager(db)
    messages, ctx_stats = await context_mgr.build_prompt_context(
        agent=agent,
        system_prompt=system_prompt,
        user_message=message,
        history=history,
        team_id=team_id,
    )

    # 模型路由
    routing_info = {}
    selected_model = default_model

    if use_router:
        router = ModelRouter(db)
        complexity = await router.classify_complexity(message)
        routing_info["complexity"] = complexity.value

        if not mock:
            selected_model = await router.select_model(complexity, agent.default_model_id)
        routing_info["routed_model"] = selected_model.model_name
    else:
        routing_info["complexity"] = "standard"
        routing_info["routed_model"] = default_model.model_name

    # 构建原生 function calling tools 格式
    native_tools = []
    if tools:
        for tool in tools:
            params = tool.param_schema or {}
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    params = {"type": "object", "properties": {}}
            native_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": params,
                }
            })

    # 调用 LLM（支持降级链）
    tool_results = []

    if mock:
        adapter = MockLLMAdapter()
        api_key = "mock"
        config = LLMConfig(
            model=selected_model.model_name,
            provider=selected_model.provider,
            api_key=api_key,
            tools=native_tools,
        )
        response = await adapter.chat(messages=messages, config=config)
        routing_info["fallback_used"] = False
    elif use_fallback:
        fb_chain = FallbackChain(db)
        api_key = await resolve_api_key(db, selected_model)
        config = LLMConfig(
            model=selected_model.model_name,
            provider=selected_model.provider,
            api_key=api_key,
            tools=native_tools,
        )
        response, fb_info = await fb_chain.call_with_fallback(
            messages=messages,
            primary_model=selected_model,
            api_key=api_key,
        )
        routing_info.update(fb_info)
    else:
        adapter = LiteLLMAdapter()
        api_key = await resolve_api_key(db, selected_model)
        config = LLMConfig(
            model=selected_model.model_name,
            provider=selected_model.provider,
            api_key=api_key,
            tools=native_tools,
        )
        response = await adapter.chat(messages=messages, config=config)
        routing_info["fallback_used"] = False

    # ── LangFuse: structured generation metadata ──
    usage = response.usage or {}
    gen_meta = trace_metadata.gen_meta(
        provider=response.provider or "",
        model=response.model or "",
        agent=agent.name or "",
        exec_mode="single_pass",
        latency_s=response.latency or 0.0,
    )
    with TraceContext.generation(
        name=f"chat:{response.model or 'unknown'}",
        model=response.model or "",
        input_data={"messages": [m.get("content", "")[:500] for m in messages[-3:]]},
        output_data=response.content[:500] if response.content else "",
        usage={
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        metadata=gen_meta,
    ):
        pass  # generation auto-ended on context exit

    # 检查工具调用
    content = response.content
    thinking_content = response.thinking  # 使用模型的原生思考内容

    # 清理内容中的 TOOL_CALL 文本（防止泄露到前端）
    content = _strip_tool_call_text(content)

    # 检测 Agent 提出的问题
    questions = _extract_questions(content)

    # 优先使用原生 tool_calls，fallback 到文本 TOOL_CALL
    native_tool_calls = response.tool_calls
    text_tool_match = _extract_tool_call(content)

    if native_tool_calls:
        logger.info(f"🔧 Native tool_calls: {[t['name'] for t in native_tool_calls]}")
    elif text_tool_match:
        logger.info(f"🔧 Text TOOL_CALL: {text_tool_match['name']}")
    else:
        logger.info(f"📝 No tool call (first 300 chars): {content[:300]}")

    # 构建 tool call 列表
    tool_call_list = []
    if native_tool_calls:
        for tc in native_tool_calls:
            try:
                args = tc["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                tool_call_list.append({"name": tc["name"], "params": args})
            except Exception as e:
                logger.warning(f"Failed to parse native tool_call: {e}")
    elif text_tool_match:
        tool_call_list.append(text_tool_match)

    for tool_call_match in tool_call_list:
        tool_name = tool_call_match["name"]
        tool_params = tool_call_match["params"]

        logger.info(f"🔧 Executing tool: {tool_name}")
        try:
            tool_result = await tool_executor.execute(tool_name, tool_params, session_id=session_id)
            tool_results.append({
                "tool": tool_name,
                "params": {k: str(v)[:100] for k, v in tool_params.items()},
                "success": tool_result.success,
                "output": tool_result.output[:3000] if tool_result.output else "",
                "error": tool_result.error,
            })
            logger.info(f"🔧 Tool {tool_name}: success={tool_result.success}")

            # 反馈给 LLM
            if native_tool_calls:
                messages.append({"role": "assistant", "content": content or "", "tool_calls": [
                    {"id": f"call_{ti}", "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["params"]) if isinstance(tc["params"], dict) else tc["params"]}}
                    for ti, tc in enumerate(tool_call_list)
                ]})
                messages.append({"role": "tool", "tool_call_id": "call_0", "content": json.dumps({
                    "success": tool_result.success, "output": tool_result.output[:3000] if tool_result.output else "", "error": tool_result.error,
                }, ensure_ascii=False)})
            else:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"工具执行结果:\n{json.dumps(tool_results[-1], ensure_ascii=False)}\n\n请用1-2句话概述执行结果。"})

            config_no_tools = LLMConfig(
                model=config.model, provider=config.provider, api_key=config.api_key,
                temperature=config.temperature, max_tokens=config.max_tokens,
            )
            if mock:
                response2 = await adapter.chat(messages=messages, config=config_no_tools)
            elif use_fallback:
                response2, _ = await fb_chain.call_with_fallback(
                    messages=messages, primary_model=selected_model, api_key=api_key,
                )
            else:
                response2 = await adapter.chat(messages=messages, config=config_no_tools)

            content = response2.content or f"✅ 工具执行完成：{tool_name}"

            # ── LangFuse: structured tool follow-up generation ──
            usage2 = response2.usage or {}
            tfu_meta = trace_metadata.gen_meta(
                provider=response2.provider or "",
                model=response2.model or config.model or "",
                agent=agent.name or "",
                exec_mode="tool_followup",
                latency_s=response2.latency or 0.0,
            )
            tfu_meta["tool_name"] = tool_name
            with TraceContext.generation(
                name=f"tool:{tool_name}",
                model=response2.model or config.model or "",
                input_data={"messages": [m.get("content", "")[:300] for m in messages[-2:]]},
                output_data=content[:500],
                usage={
                    "prompt_tokens": usage2.get("prompt_tokens", 0),
                    "completion_tokens": usage2.get("completion_tokens", 0),
                    "total_tokens": usage2.get("total_tokens", 0),
                },
                metadata=tfu_meta,
            ):
                pass

            # 清理可能残留的 TOOL_CALL 文本
            import re as _re_clean
            content = _re_clean.sub(
                r'TOOL_CALL:\s*\{[^}]*?"name"\s*:\s*"[^"]*"[^}]*?"params"\s*:\s*\{[^}]*?\}\s*\}\s*\}?',
                '', content, flags=_re_clean.DOTALL,
            ).strip()
            if not content:
                content = f"✅ 工具执行完成：{tool_name}"
            response.usage.update(response2.usage)
        except Exception as tool_err:
            logger.error(f"🔧 Tool execution failed: {tool_err}")
            content = f"工具执行失败: {str(tool_err)}"

    # 保存对话记忆（主管调度等内部调用可跳过）
    if save_memory:
        memory_mgr = MemoryManager(db)
        await memory_mgr.save_dialog_memory(
            agent_id=agent.id,
            team_id=uuid.UUID(team_id) if team_id else None,
            user_message=message,
            assistant_message=content,
            session_id=session_id,
        )

    result = {
        "content": content,
        "model": response.model,
        "provider": response.provider,
        "latency": response.latency,
        "usage": response.usage,
        "tool_results": tool_results,
        "context_stats": ctx_stats,
        "routing": routing_info,
        "questions": questions,  # Agent 提出的问题列表
    }

    # 按需暴露推理细节（DiscussionEngine 使用）
    if return_reasoning:

        # 构建决策描述
        decision_desc = []
        if tool_results:
            decision_desc.append(f"调用了 {len(tool_results)} 个工具")
        if ctx_stats.get("memories_injected", 0) > 0:
            decision_desc.append(f"参考了 {ctx_stats['memories_injected']} 条历史对话")
        if routing_info.get("fallback_used"):
            decision_desc.append(f"使用了降级模型: {routing_info.get('fallback_reason', '')}")
        if thinking_content:
            decision_desc.append("输出了思考过程")
            logger.info(f"✅ Thinking content ({len(str(thinking_content))} chars) will be included in reasoning for {agent.name}")
        else:
            logger.info(f"⚠ No thinking content for {agent.name} with model {selected_model.model_name}")

        result["reasoning"] = {
            "model_routing": {
                "complexity": routing_info.get("complexity", "standard"),
                "selected_model": routing_info.get("routed_model", "unknown"),
                "provider": selected_model.provider,
                "fallback_used": routing_info.get("fallback_used", False),
                "fallback_reason": routing_info.get("fallback_reason", None),
            },
            "tool_calls": [
                {
                    "tool": tr["tool"],
                    "params": tr["params"],
                    "success": tr["success"],
                    "output": tr.get("output") or "",
                    "error": tr.get("error"),
                }
                for tr in tool_results
            ],
            "context_used": {
                "memories_injected": ctx_stats.get("memories_injected", 0),
                "rag_chunks": ctx_stats.get("rag_chunks", 0),
                "total_tokens": (
                    (response.usage.get("total_tokens", 0) if isinstance(response.usage, dict) else response.usage)
                ),
            },
            "prompt_length": len(system_prompt) + len(message),
            "input_content": f"# 系统提示\n{system_prompt[:1000]}{'...' if len(system_prompt) > 1000 else ''}\n\n# 用户消息\n{message}",
            "decision_summary": " · ".join(decision_desc) if decision_desc else "直接回复",
            "thinking_steps": thinking_content,  # 添加思考步骤
        }

    return result


def _extract_tool_call(content: str) -> Optional[dict]:
    """从 LLM 回复中提取工具调用 JSON

    支持两种格式：
    1. TOOL_CALL: {"name": "...", "params": {...}}
    2. ```json\n{"tool_call": {"name": "...", "params": {...}}}\n```
    3. {"tool_call": {"name": "...", "params": {...}}}
    """
    import re
    try:
        # Format 1: TOOL_CALL: {"name": "...", "params": {...}}
        tool_call_match = re.search(r'TOOL_CALL:\s*(\{.*?"name"\s*:\s*".*?".*?"params"\s*:\s*\{.*?\}\s*\})', content, re.DOTALL)
        if tool_call_match:
            json_str = tool_call_match.group(1)
            parsed = json.loads(json_str)
            if "name" in parsed and "params" in parsed:
                return parsed

        # Format 2: ```json code block
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            json_str = content[start:end].strip()
            parsed = json.loads(json_str)
            if "tool_call" in parsed:
                return parsed["tool_call"]
            if "name" in parsed and "params" in parsed:
                return parsed

        # Format 3: Inline {"tool_call": ...}
        if '{"tool_call"' in content:
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
            parsed = json.loads(json_str)
            if "tool_call" in parsed:
                return parsed["tool_call"]
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def _extract_questions(content: str) -> list[dict]:
    """从 LLM 回复中提取 Agent 提出的问题

    检测以下格式的问题：
    1. 【问题】或 [问题] 标记的问题
    2. 以 ? 结尾的问句
    3. 需要确认/澄清的内容
    """
    import re
    questions = []

    # 检测显式问题标记
    question_pattern = r'【问题】[：:]\s*(.*?)(?=\n|$)|\[问题\][：:]\s*(.*?)(?=\n|$)'
    for match in re.finditer(question_pattern, content):
        question_text = match.group(1).strip()
        if question_text:
            questions.append({
                "text": question_text,
                "type": "clarification",
            })

    # 检测问句（以 ? 结尾且包含特定关键词）
    if not questions:
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if '?' in line and any(keyword in line for keyword in ['确认', '请问', '是否', '需要', '希望', '能否', '可以']):
                questions.append({
                    "text": line.rstrip('?') + '?',
                    "type": "confirmation",
                })

    return questions


def _strip_tool_call_text(content: str) -> str:
    """从 LLM 回复内容中移除 TOOL_CALL 文本，防止泄露到前端。
    支持单行和多行（嵌套括号、长文件内容）格式。"""
    if not content:
        return ""
    import re
    cleaned = content
    # Remove TOOL_CALL: {"name": "...", "params": {...}} including multi-line with nested braces
    cleaned = re.sub(
        r'TOOL_CALL:\s*\{[^}]*?"name"\s*:\s*"[^"]*"[^}]*?"params"\s*:\s*\{[^}]*\}',
        '', cleaned, flags=re.DOTALL,
    )
    # Also handle multi-line params (content field may span multiple lines within the same TOOL_CALL)
    cleaned = re.sub(
        r'TOOL_CALL:\s*\{.*?"name"\s*:\s*"file-ops".*?"params"\s*:\s*\{.*?\}\s*\}',
        '', cleaned, flags=re.DOTALL,
    )
    # Remove leading narrative about tool calls
    cleaned = re.sub(r'已成功写入[^。]*(?:。)?', '', cleaned)
    cleaned = re.sub(r'正在继续写入[^。]*(?:。)?', '', cleaned)
    cleaned = re.sub(r'(?:。|\n)\s*TOOL_CALL[^\n]*', '', cleaned)
    return cleaned.strip() if cleaned.strip() else content


async def agent_chat_stream(
    db: AsyncSession,
    agent: Agent,
    message: str,
    *,
    team_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> "AsyncIterator[str]":
    """流式 Agent 对话：逐 token 返回，供引擎实时推送到前端。

    简化版 agent_chat：跳过工具执行（流式不支持工具调用），
    仅做 prompt 组装 → 模型路由 → 流式 LLM 调用。
    """
    from app.services.agent_factory import build_system_prompt, resolve_api_key
    from app.services.model_router import ModelRouter
    from app.services.fallback_chain import FallbackChain
    from app.services.context_manager import ContextManager

    # 加载关联数据
    persona = await db.get(Persona, agent.persona_id)
    default_model = await db.get(Model, agent.default_model_id)
    if not persona or not default_model:
        raise ValueError("Agent's persona or model not found")

    # 构建 system prompt
    system_prompt = await build_system_prompt(db, persona, [], message)

    # 注入上下文
    ctx_mgr = ContextManager(db)
    messages, _ = await ctx_mgr.build_prompt_context(
        agent=agent, system_prompt=system_prompt,
        user_message=message, team_id=team_id,
    )

    # 模型路由
    router = ModelRouter(db)
    complexity = await router.classify_complexity(message)
    selected_model = await router.select_model(complexity, agent.default_model_id)

    # 流式 LLM 调用
    api_key = await resolve_api_key(db, selected_model)
    config = LLMConfig(
        model=selected_model.model_name,
        provider=selected_model.provider,
        api_key=api_key,
    )
    adapter = LiteLLMAdapter()

    async for token in adapter.chat_stream(messages=messages, config=config):
        yield token
