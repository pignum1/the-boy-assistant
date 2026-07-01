"""M0: Intent Router — classify user message and decide routing.

Gateway to the collaboration system:
- single_agent: simple Q&A, simple coding tasks → direct agent_chat, skip M1-M7
- multi_agent: complex tasks requiring multi-role collaboration → enter M1-M7 pipeline

Strategy: Rules first (zero LLM, ~85% coverage) + LLM fallback (ambiguous).

Routing priority:
  1. Explicit multi-agent signals (@all, already in flow)
  2. Explicit single-agent signals (greetings, short Q&A)
  3. Task complexity detection (simple function vs. full system)
  4. LLM fallback for ambiguous cases
"""

import logging
import os
import re
from typing import Any

from .types import CollabState

logger = logging.getLogger(__name__)


# ── Routing decision types ──

ROUTING_SINGLE = "single_agent"
ROUTING_MULTI = "multi_agent"


# ── Keyword lists for fast-path classification ──

# Simple Q&A / conversation → single agent (no LLM needed)
SINGLE_AGENT_KEYWORDS = frozenset({
    "你好", "hello", "hi", "嗨", "hey",
    "什么意思", "解释下", "解释一下", "什么是", "什么是",
    "怎么样", "如何", "怎么", "能不能", "为什么",
    "帮我看看", "分析下", "看看这个",
    "谢谢", "thanks", "好的", "ok", "嗯",
    "总结下", "总结一下", "概括下",
})

# Multi-agent trigger keywords — ONLY truly complex tasks
# These always require multi-role collaboration (PM + Architect + Dev + Tester)
MULTI_AGENT_KEYWORDS = frozenset({
    "帮我开发", "帮我实现", "帮我设计",
    "开发一个", "开发个",
    "实现一个", "实现个", "设计一个",
    "创建项目", "新项目", "搭建",
    "重构", "refactor",
    "完整的功能", "完整功能",
    "前端和后端", "前后端",
    "全栈", "fullstack", "full stack",
})

# Simple coding task patterns — single function/algorithm/class
# Matches "写一个X函数", "写个X算法", "用X语言写Y"
SIMPLE_CODING_PATTERNS = [
    re.compile(r"写[一个]?.*(?:函数|算法|方法|类|模块|脚本|程序|工具)$"),
    re.compile(r"写[一个]?.*(?:斐波那契|排序|查找|搜索|哈希|队列|栈|链表|二叉树)"),
    re.compile(r"帮我写[一个]?.*(?:函数|算法|方法|类|模块|脚本|程序|工具)$"),
    re.compile(r"用\s*\w+\s*写"),
    re.compile(r"写[一个]?helloworld", re.IGNORECASE),
    re.compile(r"写[一个]?.*冒泡"),
    re.compile(r"写[一个]?.*快速排序"),
    re.compile(r"写[一个]?.*二分"),
    re.compile(r"写[一个]?.*(?:hello|hi)\s*world", re.IGNORECASE),
]

# Complexity indicators — if present, likely needs multi-agent
COMPLEXITY_INDICATORS = frozenset({
    # System-level
    "系统", "项目", "平台", "服务", "架构", "微服务", "分布式",
    # Multi-component
    "前后端", "全栈", "前端和后端", "client和server", "客户端和服务端",
    # Multi-role
    "产品", "设计", "测试", "部署", "运维", "数据库设计", "api设计",
    # Scale
    "完整", "全套", "从零", "end-to-end", "全流程",
})

# Simple task indicators — if present, likely single-agent
SIMPLE_TASK_INDICATORS = frozenset({
    "函数", "算法", "方法", "代码片段", "一行代码", "正则",
    "公式", "示例", "例子", "demo", "snippet",
})


def _is_simple_coding_task(message: str) -> bool:
    """Detect if the message is a simple coding task suitable for single agent.

    Criteria:
    - Short message (< 60 chars)
    - Mentions single function/algorithm/class
    - No complexity indicators (system, project, multi-role)
    """
    msg = message.strip().lower()

    # Check complexity indicators first — if present, NOT simple
    for indicator in COMPLEXITY_INDICATORS:
        if indicator in msg:
            return False

    # Check simple coding patterns
    for pattern in SIMPLE_CODING_PATTERNS:
        if pattern.search(msg):
            return True

    # Heuristic: "帮我写一个X" where X has explicit simple indicators
    # NOTE: Do NOT assume short messages are always simple — let LLM analyze.
    # Only mark as simple when there's explicit evidence (algorithm, function, snippet, etc.)
    if len(msg) < 60 and ("写一个" in msg or "写个" in msg or "帮我写" in msg):
        # If it mentions a simple task indicator, it's simple
        for indicator in SIMPLE_TASK_INDICATORS:
            if indicator in msg:
                return True
        # Otherwise → let LLM analyze (don't assume simple based on length alone)
        return False

    return False


def _classify_by_rules(message: str, status: str, mentioned_agents: list[str] | None) -> str | None:
    """Fast-path classification using keyword rules.

    Returns:
        "single_agent" | "multi_agent" | None (needs LLM)
    """
    msg = message.strip().lower()

    # 1. Already in multi-agent flow → continue
    if status not in ("init", "completed", "", "idle"):
        return ROUTING_MULTI

    # 2. @mention specific agent → single agent
    if mentioned_agents and len(mentioned_agents) > 0:
        # @all is multi-agent
        if "__all__" in mentioned_agents:
            return ROUTING_MULTI
        return ROUTING_SINGLE

    # 3. Multi-agent trigger keywords (strict — only complex tasks)
    for kw in MULTI_AGENT_KEYWORDS:
        if kw in msg:
            # But check if it's actually a simple task despite the keyword
            if _is_simple_coding_task(msg):
                logger.info(f"M0: '{kw}' matched multi_agent keyword, but simple task detected → single_agent")
                return ROUTING_SINGLE
            return ROUTING_MULTI

    # 4. Single-agent keywords (simple Q&A)
    for kw in SINGLE_AGENT_KEYWORDS:
        if kw in msg:
            return ROUTING_SINGLE

    # 5. "帮我写" / "写一个" / "写个" — check complexity
    has_write_keyword = "帮我写" in msg or "写一个" in msg or "写个" in msg
    if has_write_keyword:
        if _is_simple_coding_task(msg):
            return ROUTING_SINGLE
        # Not clearly simple → let LLM analyze (complexity + domain)
        return "needs_analysis"

    # 6. Heuristic: short message (<20 chars) with no technical terms → likely simple
    if len(msg) < 20 and not any(c in msg for c in ("写", "开发", "实现", "部署", "创建")):
        return ROUTING_SINGLE

    # 7. Cannot determine → needs LLM analysis
    return "needs_analysis"


async def _analyze_task_by_llm(
    message: str,
    team_agents: list[dict],
) -> dict:
    """轻量 LLM 分析任务：复杂度 + 领域 + 建议 Agent。

    替代旧的 _classify_by_llm 和 _is_simple_coding_task，
    一次 LLM 调用同时输出 routing、complexity、domain、suggested agent。

    Returns:
        {
            "routing": "single_agent" | "multi_agent",
            "complexity": "simple" | "medium" | "complex",
            "domain": "frontend" | "backend" | "devops" | "testing" | "design" | "general",
            "required_capabilities": ["react", "python", ...],
            "best_agent_name": "agent_name" or None
        }
    """
    try:
        from app.core.database import async_session
        from app.services.agent_chat import agent_chat
        from app.models.agent import Agent
        from sqlalchemy import select

        # Build agent list with capabilities for prompt
        agent_lines = []
        for a in team_agents:
            name = a.get("name", "?")
            caps = a.get("capabilities") or []
            role = a.get("role") or ""
            cap_str = ", ".join(caps) if caps else "(无标签)"
            agent_lines.append(f"- {name} [{role}]: {cap_str}")
        agent_list_str = "\n".join(agent_lines) if agent_lines else "(无可用 Agent)"

        prompt = f"""分析这条用户消息的任务特征和所需能力。

用户消息: "{message}"

可选 Agent:
{agent_list_str}

请输出 JSON（不要输出其他内容）:
{{
  "routing": "single" 或 "multi",
  "complexity": "simple" 或 "medium" 或 "complex",
  "domain": "frontend" 或 "backend" 或 "devops" 或 "testing" 或 "design" 或 "general",
  "required_capabilities": ["能力1", "能力2"],
  "best_agent_name": "最匹配的agent名字 或 null"
}}

判断标准:
- routing: 单个函数/简单问答=single, 需要多角色协作/系统级任务=multi
- complexity: 单个函数/简单查询=simple, 单模块功能=medium, 多模块/系统级=complex
- domain: 根据涉及的技术栈判断领域
- required_capabilities: 任务需要的具体技术能力
- best_agent_name: 从可选 Agent 中选出能力最匹配的"""

        async with async_session() as db:
            from app.models.model import Model as ModelModel
            import uuid as _uuid

            # ── 选择用于 LLM 分析的 Agent ──
            # 优先从 team_agents 中选择（确保使用有效模型），
            # 避免选到数据库中 test provider 的 Agent 导致 LLM 调用失败
            agent = None

            # 策略 1: 使用 team_agents 中第一个 agent
            if team_agents:
                first_id = team_agents[0].get("agent_id")
                if first_id:
                    try:
                        stmt = select(Agent).where(Agent.id == _uuid.UUID(first_id))
                        result = await db.execute(stmt)
                        agent = result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        pass

            # 策略 2: 找任意一个使用非 test provider 模型的 Agent
            if not agent:
                stmt = (
                    select(Agent)
                    .join(ModelModel, Agent.default_model_id == ModelModel.id)
                    .where(ModelModel.provider != "test")
                    .limit(1)
                )
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()

            if not agent:
                return _default_analysis()

            llm_result = await agent_chat(
                db=db, agent=agent, message=prompt,
                save_memory=False, return_reasoning=False,
            )
            content = llm_result.get("content", "").strip()

            return _parse_llm_analysis(content)

    except Exception as e:
        logger.warning(f"M0 LLM task analysis failed: {e}, using defaults")
        return _default_analysis()


def _default_analysis() -> dict:
    """LLM 分析失败时的默认返回。"""
    return {
        "routing": ROUTING_SINGLE,
        "complexity": "medium",
        "domain": "general",
        "required_capabilities": [],
        "best_agent_name": None,
    }


def _parse_llm_analysis(content: str) -> dict:
    """解析 LLM 返回的 JSON 分析结果。"""
    import json

    try:
        # Try direct JSON parse
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try extracting from markdown code block
        if "```json" in content:
            try:
                start = content.index("```json") + 7
                end = content.index("```", start)
                data = json.loads(content[start:end].strip())
            except (ValueError, json.JSONDecodeError):
                return _default_analysis()
        elif "{" in content:
            try:
                start = content.index("{")
                end = content.rindex("}") + 1
                data = json.loads(content[start:end])
            except (ValueError, json.JSONDecodeError):
                return _default_analysis()
        else:
            return _default_analysis()

    # Validate and normalize
    routing = data.get("routing", "single").lower()
    if "multi" in routing:
        routing = ROUTING_MULTI
    else:
        routing = ROUTING_SINGLE

    complexity = data.get("complexity", "medium").lower()
    if complexity not in ("simple", "medium", "complex"):
        complexity = "medium"

    domain = data.get("domain", "general").lower()
    if domain not in ("frontend", "backend", "devops", "testing", "design", "data", "general"):
        domain = "general"

    required_capabilities = data.get("required_capabilities", [])
    if not isinstance(required_capabilities, list):
        required_capabilities = []

    best_agent_name = data.get("best_agent_name")
    if best_agent_name and not isinstance(best_agent_name, str):
        best_agent_name = None

    return {
        "routing": routing,
        "complexity": complexity,
        "domain": domain,
        "required_capabilities": required_capabilities,
        "best_agent_name": best_agent_name,
    }


async def classify_and_route(state: CollabState) -> dict[str, Any]:
    """Main M0 entry point: classify message and return routing decision.

    Flow:
    1. Fast rules for clear cases (greetings → single, @all → multi, etc.)
    2. LLM analysis for ambiguous cases → outputs complexity + domain + best_agent
    3. Route to single_agent (with smart agent selection) or multi_agent pipeline

    Returns state updates dict:
    - If single_agent: includes full execution result (status="completed")
    - If multi_agent: includes routing_decision="multi_agent"
    """
    messages = state.get("messages", [])
    if not messages:
        return {"status": "completed", "routing_decision": ROUTING_SINGLE}

    last_msg = messages[-1]
    user_message = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
    status = state.get("status", "init")
    team_agents = state.get("team_agents", [])

    # Extract @mentions from message
    mentioned = []
    for agent in team_agents:
        name = agent.get("name", "")
        if name and f"@{name}" in user_message:
            mentioned.append(agent.get("agent_id", ""))

    # Step 1: Rule-based classification
    decision = _classify_by_rules(user_message, status, mentioned)

    # Step 2: LLM analysis for ambiguous cases
    analysis = None
    if decision == "needs_analysis":
        analysis = await _analyze_task_by_llm(user_message, team_agents)
        decision = analysis["routing"]
        logger.info(
            f"M0 LLM analysis: complexity={analysis['complexity']}, "
            f"domain={analysis['domain']}, "
            f"best_agent={analysis.get('best_agent_name')}, "
            f"routing={decision}"
        )

    logger.info(f"M0 routing: '{user_message[:50]}...' → {decision}")

    # Step 3: Execute based on decision
    if decision == ROUTING_SINGLE:
        return await _execute_single_agent(
            state, user_message, mentioned, team_agents, analysis,
        )

    # Get agent name for display
    m0_agent = team_agents[0].get("name", "Agent") if team_agents else "Agent"
    return {
        "status": "analyzing",
        "routing_decision": ROUTING_MULTI,
        "_agent_name": m0_agent,
    }


# ── Capability-based agent selection for single_agent mode ──

# Domain → role name keywords (用于 LLM 未返回 best_agent 时的兜底匹配)
DOMAIN_ROLE_KEYWORDS: dict[str, list[str]] = {
    "frontend": ["前端", "frontend", "front-end", "react", "vue", "web"],
    "backend": ["后端", "backend", "back-end", "服务端", "server", "api"],
    "devops": ["运维", "devops", "部署", "deploy", "docker", "k8s", "kubernetes"],
    "testing": ["测试", "test", "qa", "质量"],
    "design": ["设计", "design", "ui", "ux", "界面"],
    "data": ["数据", "data", "数据库", "database", "db"],
}


def _select_agent_by_capabilities(
    team_agents: list[dict],
    required_capabilities: list[str],
    domain: str,
    message: str = "",
) -> str | None:
    """基于 capabilities 标签匹配最合适的 Agent。

    匹配策略（按优先级）:
    1. capabilities 精确匹配: agent 的 capabilities 覆盖所有 required_capabilities
    2. 部分匹配: 按 required_capabilities 交集数量排序
    3. 领域兜底: 按 domain 匹配 agent 的 role_name
    4. 关键词启发式: 从消息中提取技术关键词匹配 agent 能力标签
    5. 兜底: 第一个 agent
    """
    if not team_agents:
        return None

    required_lower = {c.lower() for c in required_capabilities}
    domain_lower = domain.lower() if domain else ""

    # 计算每个 Agent 的匹配分数
    scored: list[tuple[int, bool, str]] = []  # (score, domain_match, agent_id)
    for a in team_agents:
        agent_caps = {c.lower() for c in (a.get("capabilities") or [])}
        agent_id = a.get("agent_id")
        role_name = (a.get("role") or "").lower()

        # 计算能力匹配分数
        cap_score = len(required_lower & agent_caps) if required_lower else 0

        # 检查领域是否匹配 role_name
        domain_match = False
        if domain_lower:
            domain_kws = DOMAIN_ROLE_KEYWORDS.get(domain_lower, [domain_lower])
            domain_match = any(kw in role_name for kw in domain_kws)

        scored.append((cap_score, domain_match, agent_id))

    # 排序: 能力分数降序 → 领域匹配优先
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    best = scored[0]
    if best[0] > 0 or best[1]:
        return best[2]

    # ── 关键词启发式兜底 ──
    # 当 LLM 分析失败（无 capabilities + domain=general）时，从消息文本直接提取
    # 技术关键词，匹配 agent 的能力标签
    if message:
        msg_lower = message.lower()
        # 技术关键词 → 能力标签映射
        TECH_KEYWORD_TO_CAP: dict[str, list[str]] = {
            "react": ["react", "frontend", "typescript", "javascript"],
            "vue": ["vue", "frontend", "javascript"],
            "angular": ["angular", "frontend", "typescript"],
            "组件": ["react", "vue", "frontend"],
            "页面": ["react", "vue", "frontend", "html", "css"],
            "前端": ["frontend", "react", "vue"],
            "css": ["css", "frontend"],
            "html": ["html", "frontend"],
            "python": ["python", "fastapi", "backend"],
            "fastapi": ["python", "fastapi", "api_design", "backend"],
            "django": ["python", "django", "backend"],
            "flask": ["python", "flask", "backend"],
            "api": ["api_design", "backend", "fastapi"],
            "接口": ["api_design", "backend"],
            "数据库": ["postgresql", "database_design", "backend"],
            "sql": ["postgresql", "sqlalchemy", "backend"],
            "docker": ["docker", "devops", "k8s"],
            "部署": ["docker", "k8s", "devops", "ci_cd"],
            "测试": ["testing", "pytest"],
            "单元测试": ["testing", "pytest"],
            "设计": ["ui_design", "figma", "design"],
            "ui": ["ui_design", "css", "design", "frontend"],
        }
        # 从消息中提取匹配的技术能力
        message_caps: set[str] = set()
        for kw, caps in TECH_KEYWORD_TO_CAP.items():
            if kw in msg_lower:
                message_caps.update(caps)

        if message_caps:
            # 用提取的能力标签重新计算匹配分数
            heuristic_scored: list[tuple[int, str]] = []
            for a in team_agents:
                agent_caps = {c.lower() for c in (a.get("capabilities") or [])}
                agent_id = a.get("agent_id")
                heuristic_score = len(message_caps & agent_caps)
                heuristic_scored.append((heuristic_score, agent_id))

            heuristic_scored.sort(key=lambda x: x[0], reverse=True)
            if heuristic_scored[0][0] > 0:
                logger.info(
                    f"M0 keyword heuristic: matched caps={message_caps & {c.lower() for c in (team_agents[0].get('capabilities') or [])}}"
                )
                return heuristic_scored[0][1]

    # 兜底: 第一个 agent
    return team_agents[0].get("agent_id")


def _select_agent_by_name(
    team_agents: list[dict],
    agent_name: str,
) -> str | None:
    """根据 agent name 查找对应的 agent_id."""
    if not agent_name:
        return None
    name_lower = agent_name.strip().lower()
    for a in team_agents:
        if (a.get("name") or "").lower() == name_lower:
            return a.get("agent_id")
    return None


# 用于判断是否需要提取代码块并写入 workspace 的关键词
_CODING_INTENT_KEYWORDS = frozenset({
    "写", "代码", "函数", "算法", "实现", "开发", "编程", "脚本",
    "debug", "fix", "修复", "重构", "refactor",
    "python", "java", "typescript", "javascript", "go", "rust", "c++",
    "api", "接口", "rest", "graphql", "react", "vue", "css", "html",
    "组件", "component", "页面", "服务", "service",
})


def _detect_coding_intent(message: str, analysis: dict | None = None) -> bool:
    """判断任务是否涉及代码生成（用于决定是否提取代码块写入 workspace）。

    优先用 LLM 分析结果，否则用关键词匹配。
    """
    # 如果有 LLM 分析，用 domain 判断
    if analysis:
        domain = analysis.get("domain", "general")
        if domain in ("frontend", "backend", "devops", "testing"):
            return True
        if domain in ("general", "design"):
            # general/design 不一定是 coding，再用关键词确认
            pass
        else:
            return False

    # 兜底: 关键词匹配
    msg = message.strip().lower()
    for kw in _CODING_INTENT_KEYWORDS:
        if kw in msg:
            return True
    return False


# ── Code extraction & file writing for single_agent mode ──

# Language → file extension
LANG_EXT = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "java": ".java",
    "go": ".go",
    "rust": ".rs", "rs": ".rs",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "ruby": ".rb", "rb": ".rb",
    "php": ".php",
    "sql": ".sql",
    "html": ".html",
    "css": ".css",
    "shell": ".sh", "bash": ".sh", "sh": ".sh",
    "yaml": ".yaml", "yml": ".yaml",
    "json": ".json",
    "xml": ".xml",
    "dockerfile": "Dockerfile",
}

# Common code keywords → guess filename
def _guess_filename(code: str, lang: str, user_message: str) -> str:
    """Guess a reasonable filename from the code content and context."""
    ext = LANG_EXT.get(lang.lower(), ".txt")

    # Try to extract class/function name for filename
    if ext == ".py":
        m = re.search(r'def\s+(\w+)\s*\(', code)
        if m:
            return m.group(1) + ext
        m = re.search(r'class\s+(\w+)', code)
        if m:
            return m.group(1).lower() + ext
    elif ext in (".js", ".ts"):
        m = re.search(r'(?:function|const|export\s+default\s+class)\s+(\w+)', code)
        if m:
            name = re.sub(r'([A-Z])', r'_\1', m.group(1)).lower().lstrip('_')
            return name + ext

    # Fallback: derive from user message
    msg_clean = re.sub(r'[^\w\s]', '', user_message.lower())
    words = msg_clean.split()[:3]
    name = '_'.join(w for w in words if len(w) > 1)[:30] or 'output'
    if ext == "Dockerfile":
        return "Dockerfile"
    return name + ext


def _extract_code_blocks(content: str) -> list[tuple[str, str, str]]:
    """Extract fenced code blocks from markdown content.

    Returns list of (language, code, guessed_filename).
    """
    pattern = r'```(\w*)\s*\n(.*?)```'
    blocks = []
    for match in re.finditer(pattern, content, re.DOTALL):
        lang = match.group(1) or "text"
        code = match.group(2).strip()
        if len(code) < 10:  # Skip tiny snippets
            continue
        blocks.append((lang, code))
    return blocks


async def _write_code_to_workspace(
    session_id: str,
    user_message: str,
    content: str,
) -> list[dict]:
    """Extract code blocks from LLM response and write to workspace.

    Returns list of {name, status, path} for files written.
    """
    blocks = _extract_code_blocks(content)
    if not blocks:
        return []

    # Resolve workspace path
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_workspace(session_id)
        if not ws or not ws.path:
            return []
        ws_path = ws.path
    except Exception:
        return []

    if not os.path.isdir(ws_path):
        os.makedirs(ws_path, exist_ok=True)

    written = []
    used_names: set[str] = set()

    for lang, code in blocks:
        filename = _guess_filename(code, lang, user_message)
        # Deduplicate filenames
        base, ext = os.path.splitext(filename)
        if not ext and filename == "Dockerfile":
            base, ext = "", "Dockerfile"
        counter = 1
        final_name = filename
        while final_name in used_names:
            final_name = f"{base}_{counter}{ext}"
            counter += 1
        used_names.add(final_name)

        file_path = os.path.join(ws_path, final_name)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code + '\n')
            written.append({
                "name": final_name,
                "status": "created",
                "path": file_path,
            })
            logger.info(f"M0 single_agent: wrote {final_name} ({len(code)} chars)")
        except Exception as e:
            logger.warning(f"M0 single_agent: failed to write {final_name}: {e}")

    return written


def _build_file_summary(files: list[dict]) -> str:
    """Build a concise summary line for files written."""
    if not files:
        return ""
    parts = [f"`{f['name']}`" for f in files]
    return "📁 已写入文件: " + ", ".join(parts)


def _read_workspace_files(session_id: str, known_files: list[str]) -> str:
    """Read code files from workspace and format as markdown code blocks.

    Used when the agent wrote files via tool calls but the response
    only contains a brief summary without the actual code.
    """
    try:
        from app.services.workspace.manager import workspace_manager
        ws = workspace_manager.get_workspace(session_id)
        if not ws or not ws.path or not os.path.isdir(ws.path):
            return ""
    except Exception:
        return ""

    # Determine language from file extension
    ext_to_lang = {v: k for k, v in LANG_EXT.items() if k != "text"}

    parts = []
    # Read known files first, then any other code files in workspace
    files_to_read = list(known_files)
    try:
        for fname in os.listdir(ws.path):
            if fname not in files_to_read and not fname.startswith('.'):
                files_to_read.append(fname)
    except Exception:
        pass

    for fname in files_to_read[:5]:  # Limit to 5 files
        fpath = os.path.join(ws.path, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                file_content = f.read()
            if len(file_content) < 10:
                continue
            # Detect language from extension
            _, ext = os.path.splitext(fname)
            if fname == "Dockerfile":
                lang = "dockerfile"
            else:
                lang = ext_to_lang.get(ext, ext.lstrip('.')) if ext else ""
            parts.append(f"**{fname}**\n```{lang}\n{file_content}\n```")
        except Exception:
            continue

    return "\n\n".join(parts)


async def _execute_single_agent(
    state: CollabState,
    user_message: str,
    mentioned_agents: list[str],
    team_agents: list[dict],
    analysis: dict | None = None,
) -> dict[str, Any]:
    """Single agent path: directly call agent_chat and return result.

    Agent selection strategy (in priority order):
    1. @mentioned agent → always respect explicit mention
    2. LLM analysis suggested agent (best_agent_name)
    3. Capability-based matching from analysis
    4. Fallback: any available agent
    """
    from app.core.database import async_session
    from app.services.agent_chat import agent_chat
    from app.models.agent import Agent
    from sqlalchemy import select

    session_id = state.get("session_id", "")
    team_id = state.get("team_id", "")

    # Determine task domain for logging
    task_domain = analysis.get("domain", "general") if analysis else "general"
    logger.info(f"M0 single_agent: domain={task_domain}, selecting from {len(team_agents)} agents")

    try:
        async with async_session() as db:
            # 1. @mentioned agent → always respect explicit mention
            agent = None
            import uuid as _uuid
            if mentioned_agents:
                try:
                    agent_id = _uuid.UUID(mentioned_agents[0])
                    stmt = select(Agent).where(Agent.id == agent_id)
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
                except (ValueError, TypeError):
                    pass

            # 2. LLM analysis suggested agent (by name)
            if not agent and analysis and analysis.get("best_agent_name"):
                best_name = analysis["best_agent_name"]
                best_id = _select_agent_by_name(team_agents, best_name)
                if best_id:
                    try:
                        stmt = select(Agent).where(Agent.id == _uuid.UUID(best_id))
                        result = await db.execute(stmt)
                        agent = result.scalar_one_or_none()
                        if agent:
                            logger.info(f"M0 single_agent: selected {agent.name} via LLM suggestion")
                    except (ValueError, TypeError):
                        pass

            # 3. Capability-based matching from analysis (or message keywords)
            if not agent and team_agents:
                required_caps = analysis.get("required_capabilities", []) if analysis else []
                domain = analysis.get("domain", "general") if analysis else "general"
                best_id = _select_agent_by_capabilities(team_agents, required_caps, domain, user_message)
                if best_id:
                    try:
                        stmt = select(Agent).where(Agent.id == _uuid.UUID(best_id))
                        result = await db.execute(stmt)
                        agent = result.scalar_one_or_none()
                        if agent:
                            logger.info(
                                f"M0 single_agent: selected {agent.name} via capabilities "
                                f"(domain={domain}, caps={required_caps})"
                            )
                    except (ValueError, TypeError):
                        pass

            # 4. Fallback: use team agent, not random DB agent
            if not agent:
                # 4a. Try first team agent by ID
                if team_agents:
                    fallback_id = team_agents[0].get("agent_id")
                    if fallback_id:
                        try:
                            stmt = select(Agent).where(Agent.id == _uuid.UUID(fallback_id))
                            result = await db.execute(stmt)
                            agent = result.scalar_one_or_none()
                            if agent:
                                logger.info(f"M0 single_agent: fallback to team agent {agent.name}")
                        except (ValueError, TypeError):
                            pass
                # 4b. Last resort: any agent with non-test model
                if not agent:
                    from app.models.model import Model as ModelModel
                    stmt = (
                        select(Agent)
                        .join(ModelModel, Agent.default_model_id == ModelModel.id)
                        .where(ModelModel.provider != "test")
                        .limit(1)
                    )
                    result = await db.execute(stmt)
                    agent = result.scalar_one_or_none()
                    if agent:
                        logger.info(f"M0 single_agent: last-resort fallback to {agent.name}")

            if not agent:
                return {
                    "status": "completed",
                    "routing_decision": ROUTING_SINGLE,
                    "_agent_name": "系统",
                    "hitl_message": "抱歉，没有可用的 Agent。",
                }

            # Resolve workspace path
            workspace_path = ""
            try:
                from app.services.workspace.manager import workspace_manager
                ws = workspace_manager.get_workspace(session_id)
                if ws:
                    workspace_path = ws.path
            except Exception:
                pass

            # 统一走 AgentExecutor：模式由 Agent.execution_mode 决定
            # （直接聊天也遵循 Agent 配置，与管道一致）
            from app.services.collaboration.agent_executor import agent_executor as _exec
            exec_result = await _exec.execute(
                prompt=user_message, agent=agent, db=db,
                session_id=session_id, team_id=team_id,
                node_key="single_agent",
            )

            content = exec_result.get("content", "")
            reasoning = exec_result.get("reasoning", {}) or {}
            exec_mode = exec_result.get("exec_mode", "single_pass")

            # ── 文件写入策略（防双写）──
            # react / rewoo 模式：executor 已自行写文件到工作区并记入 reasoning.tool_calls，
            #   这里直接汇总，不再二次抽取代码块。
            # 其他模式：沿用旧的"抽取代码块写盘"逻辑。
            _is_coding_task = _detect_coding_intent(user_message, analysis)
            files_written: list[dict] = []

            if exec_mode in ("react", "rewoo"):
                tool_calls = reasoning.get("tool_calls", []) if isinstance(reasoning, dict) else []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    if "file" in (tc.get("tool") or "").lower() and tc.get("success") is not False:
                        params = tc.get("params") or {}
                        path = params.get("path") or params.get("file_path") or params.get("name") or "unknown"
                        files_written.append({"name": path.split("/")[-1], "status": "created", "path": path})
            elif _is_coding_task and session_id:
                files_written = await _write_code_to_workspace(
                    session_id, user_message, content,
                )

            # ── Build display content: code + file summary ──
            display_content = content
            files_changed = []

            # If we extracted and wrote code blocks, append file summary
            if files_written:
                file_summary = _build_file_summary(files_written)
                display_content = f"{display_content}\n\n---\n{file_summary}"
                files_changed = [{"name": f["name"], "status": "created"} for f in files_written]

            return {
                "status": "completed",
                "routing_decision": ROUTING_SINGLE,
                "_content": display_content,
                "_agent_name": agent.name or "Agent",
                "_reasoning": reasoning,
                "_model": reasoning.get("model_routing", {}).get("selected_model", "") if isinstance(reasoning, dict) else "",
                "_latency": reasoning.get("latency", 0) if isinstance(reasoning, dict) else 0,
                "files_changed": files_changed,
            }

    except Exception as e:
        logger.error(f"M0 single agent execution failed: {e}", exc_info=True)
        return {
            "status": "completed",
            "routing_decision": ROUTING_SINGLE,
            "_agent_name": "系统",
            "hitl_message": f"Agent 执行出错: {str(e)[:200]}",
        }


# ── LangGraph node ──

async def m0_intent_node(state: CollabState) -> dict[str, Any]:
    """LangGraph node: M0 intent classification + routing."""
    return await classify_and_route(state)


# ── Route function for graph edges ──

def route_after_m0(state: CollabState) -> str:
    """Determine next node after M0.

    Returns:
        "single_agent" → END (already completed in node)
        "multi_agent"  → m1_analyze
    """
    routing = state.get("routing_decision", ROUTING_SINGLE)
    if routing == ROUTING_MULTI:
        return "m1_analyze"
    return "__end__"
