"""Collaboration system types — LangGraph state + structured outputs.

Each M module reads/writes only its own section of CollabState.
LangGraph Checkpointer auto-persists every state transition.
"""

from typing import TypedDict, Annotated, Literal
import operator


# ── LangGraph State ──────────────────────────────────────────

class CollabState(TypedDict, total=False):
    """Shared state flowing through all LangGraph nodes.

    Field naming convention: {module}_{field} for module outputs.
    Base fields (team_id, session_id, etc.) are injected by the API layer.
    """

    # ── 基础上下文（API 层注入，只读）──
    messages: Annotated[list[dict], operator.add]
    team_id: str
    session_id: str               # For tool execution (file-ops needs this)
    team_agents: list[dict]       # [{agent_id, name, role, capabilities: [str], status}]
    available_roles: list[str]    # ["pm", "architect", "backend_dev", ...]
    workflow_template: dict | None  # 团队关联的工作流模板（M1 参考）

    # ── M0: 意图识别输出 ──
    routing_decision: str         # "single_agent" | "multi_agent"
    single_agent_id: str | None   # 单 Agent 时的目标 agent_id

    # ── M1: 需求分析输出 ──
    problem_type: str             # feature_request | bug_fix | refactor | question
    complexity: str               # simple | medium | complex
    analysis_summary: str         # 需求分析摘要（展示给用户）
    required_roles: list[str]     # ["architect", "backend_dev"]
    phases_plan: list[dict]       # [{name, role, goal}]（参考模板设计）
    clarity_score: float          # 信息完整度 0.0~1.0

    # ── M2: 需求澄清输出 ──
    clarified_requirements: str   # 澄清后的完整需求

    # ── M3: Agent 编排输出 ──
    agent_assignments: dict       # {role: {agent_id, name, ...}}
    missing_roles: list[str]      # 缺失的角色列表

    # ── M4: 任务分解输出 ──
    task_dag: dict                # {phases: [{id, name, tasks: [{...}]}]}
    requirements_anchor: str      # 冻结的需求（不可变，M7 验证基准）

    # ── M5/M6: 执行产出 ──
    artifacts: dict[str, str]     # {task_id: output_content}
    files_changed: list[dict]     # [{name, status: created|modified, meta}]
    agent_messages: list[dict]    # M8 通信记录 [{from, to, type, content}]

    # ── M7: 验证输出 ──
    verification: dict | None     # {passed, feedback, severity, drift_detected}

    # ── HITL（人机交互）──
    hitl_type: str                # clarification | confirmation | agent_invite | review
    hitl_message: str             # 展示给用户的消息
    hitl_options: list[dict]      # [{label, value}]
    force_confirm: bool           # 用户在澄清 HITL 中点了「确认并继续」→ M1 强制进入确认模式
    user_response: str            # HITL resume 时 hitl_node 写入的用户响应

    # ── 流程控制 ──
    status: str                   # init | analyzing | clarifying | awaiting_confirm | executing | completed | blocked | interrupted | awaiting_delta_confirm
    current_phase: int            # 当前阶段索引
    retry_count: int              # M7 验证重试计数

    # ── PR5 介入闭环 ──
    interrupt_message: str | None     # 用户介入消息（M6 → M1' 携带）
    interrupt_mode: str | None        # "soft" | "hard"
    delta_plan: dict | None           # M1' 输出的增量计划（HITL 确认前的暂存）

    # ── 组织架构（m6_org_loader 从 DB 加载）──
    org_structure: dict | None        # 从 TeamSupervisorConfig + TeamSupervisorRelation 构建的层级数据
                                      # { leader_member_id, relations: [{member_id, supervisor_member_id}],
                                      #   member_roles: {member_id: {role_name, agent_id, agent_name}} }
    # ── 分层执行状态（v2 Route A，逐步废弃）──
    execution_levels: list[list[dict]]   # topological_sort 输出 [[task, ...], ...]
    current_level: int                   # 当前执行的 level 索引（0-based）
    level_results: list[dict]            # [{level_idx, task_results: {tid: {status, output, error}}, reviewer, passed}]
    phase_retry_counts: dict[str, int]   # {"level_0": 2} per-level 重试计数
    max_level_retries: int               # 每 level 最大重试次数，默认 2

    # ── Route B 层级委派状态 ──
    delegation_stack: list[dict]            # 委派栈（模拟函数调用栈），DFS 遍历 org tree
    current_delegation: dict | None         # 当前正在处理的委派 {member_id, role_name, goal, is_leaf, ...}
    delegation_tree: dict                   # 委派树（只存元数据+路径引用，不存文件内容）
    delegation_depth: int                   # 当前递归深度
    max_delegation_depth: int               # 最大递归深度（默认 5）
    delegation_plan: dict | None            # 待验证的委派计划 {assignments: [{member_id, goal, is_leaf}]}
    pending_parallel_results: list[dict]    # 并行 Worker 独立结果（merge 在 m6_collect 中）
    _delegate_route: str                    # 路由标记: worker | supervisor | merge_to_parent | parallel_collect
    _validation_result: str                 # approved | rejected | fallback
    _validation_issues: list[dict]          # 委派计划验证问题
    escalation_history: list[dict]          # [{from_member_id, to_member_id, guidance}] — Route A/B 共用


# ── M1: Supervisor LLM 结构化输出 ────────────────────────────

class SupervisorDecision(TypedDict, total=False):
    """M1 LLM outputs this structured decision.

    Parsed from raw LLM text by m1_requirement_analyzer.
    """
    action: Literal[
        "need_clarify",      # → M2: ask user questions
        "need_confirm",      # → HITL: show analysis, wait approval
        "execute_task",      # → M3: dispatch to agents
        "done",              # → END
        "invite_agent",      # → HITL: missing agent, ask user to invite
    ]

    # For need_clarify
    questions: list[str]
    clarity_score: float

    # For need_confirm
    problem_type: str
    complexity: str
    summary: str
    required_roles: list[str]
    phases: list[dict]           # [{name, role, goal}]
    clarity_score: float

    # For execute_task
    tasks: list[dict]
    guidance: str

    # For invite_agent
    missing_roles: list[str]


# ── M5: Worker Context ───────────────────────────────────────

class WorkerContext(TypedDict, total=False):
    """Trimmed context for a single worker — only what's needed.

    Principle: CONTEXT ISOLATION
    - Each worker receives ONLY what they need
    - NOT what other workers thought (their reasoning)
    - NOT irrelevant conversation history
    """
    requirement_anchor: str            # Original confirmed requirements
    previous_artifacts: dict[str, str] # Only dependent artifacts
    current_task: dict                 # Task description
    supervisor_guidance: str           # Execution guidance
    constraints: list[str]             # Technical constraints
    agent_messages: list[dict]         # Messages from peer agents (M8)
    # ── Route B 新增 ──
    delegation_goal: str               # 主管分配的具体目标 "你负责后端 API 开发"
    org_role_context: str              # "你是小王（后端开发），向李经理（后端主管）汇报"
    retry_feedback: str                # 审核不通过时的具体原因


# ── Internal metadata keys (prefixed with _ to avoid collisions) ──
# These are used by graph nodes to pass data to streaming.py
# without polluting the persisted CollabState.

class NodeMetadata(TypedDict, total=False):
    """Internal metadata passed between graph nodes and streaming.

    These fields use _ prefix and are NOT persisted by the checkpointer.
    They exist only in the node return value for the streaming layer.
    """
    _content: str                # Chat bubble content
    _agent_name: str             # Display agent name (Supervisor/Worker/Verifier)
    _reasoning: dict             # LLM reasoning data for frontend display
    _model: str                  # Model used
    _latency: float              # LLM call latency in seconds
