/** 会话相关类型定义 */

export interface SessionInfo {
  id: string;
  team_id: string;
  title: string;
  status: 'active' | 'archived';
  mode: 'discussion' | 'sop';
  workspace_path?: string;
  message_count: number;
  task_total?: number;
  task_completed?: number;
  created_at: string;
  updated_at: string;
  team_name?: string;
}

export interface SessionCreateParams {
  team_id: string;
  title?: string;
  workspace_path?: string;
  mode?: 'discussion' | 'sop';
}

export interface SessionUpdateParams {
  title?: string;
  workspace_path?: string;
  status?: 'active' | 'archived';
}

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  agent_name?: string;
  timestamp: string;
}

export interface WorkspaceInfo {
  session_id: string;
  path: string;
  status: string;
  created_at: string;
  last_accessed: string;
  file_count: number;
  total_size_bytes: number;
}

export interface ThinkingStep {
  agent: string;
  step: string;    // agent_selection | tool_call | model_routing | context_injection
  detail: string;
  timestamp: string;
  result?: string;
}

/** 会话追踪时间线条目 */
export interface TraceEntry {
  id: string;
  type: 'thinking' | 'reasoning' | 'tool_call' | 'agent_status' | 'message_complete' | 'storage' | 'dispatch';
  agent: string;
  timestamp: string;
  summary: string;
  detail?: string;
  icon: string;      // emoji 图标
  color: string;      // CSS 颜色变量
  data?: Record<string, unknown>;  // 展开详情的原始数据
}

export interface ReasoningTrace {
  agent: string;
  model_routing: {
    complexity: string;
    selected_model: string;
    fallback_used: boolean;
    fallback_reason?: string;
    provider?: string;
  };
  tool_calls: Array<{
    tool: string;
    params: Record<string, unknown>;
    success: boolean;
    output: string;
    error?: string;
  }>;
  context_used: {
    memories_injected: number;
    rag_chunks: number;
    total_tokens: number;
  };
  decision_summary?: string;
  prompt_length?: number;
  input_content?: string;
  thinking_steps?: string;
  supervisor_analysis?: string;  // 主管的分析和指派过程
  dispatch_guidance?: string;    // 主管的执行指导
  latency?: number;              // 执行耗时
  exec_mode?: string;            // single_pass | chain_of_thought | plan_execute | rewoo | react | reflexion | self_consistency
  iterations?: number;           // LLM 调用次数 / 循环轮次
}

/** ── 编排流水线类型 ── */

/** 单个 M-Stage 的状态 */
export type OrchestrationStageStatus = 'pending' | 'thinking' | 'done' | 'skipped';

/** 单个 M-Stage 定义 */
export interface OrchestrationStage {
  id: string;          // m0_intent, m1_analyze, ...
  label: string;       // M0·意图识别, M1·需求分析, ...
  shortLabel: string;  // 意图, 分析, 澄清, ...
  status: OrchestrationStageStatus;
  /** 参与本阶段的 Agent（id → 名称） */
  agents: Array<{ id: string; name: string; role: string }>;
  /** 本阶段耗时（秒） */
  duration?: number;
  /** 阶段摘要（完成后填充） */
  summary?: string;
}

/** 实时思考详情（卡片底部展示） */
export interface OrchestrationThinking {
  /** 当前活跃的 Agent 名称 */
  agentName: string;
  /** 思考摘要 */
  summary: string;
  /** 使用的模型 */
  model?: string;
  /** 已耗时（秒） */
  elapsed?: number;
  /** 工具调用记录 */
  toolCalls: Array<{ tool: string; status: 'running' | 'done' | 'error'; detail?: string }>;
  /** 执行模式 */
  execMode?: string;
}

/** 编排卡片整体状态 */
export interface OrchestrationState {
  /** 是否激活（用户发送消息后激活，流程结束后保持） */
  active: boolean;
  /** 是否已完成 */
  completed: boolean;
  /** 有序 M-Stage 列表 */
  stages: OrchestrationStage[];
  /** 当前活跃阶段 id */
  currentStageId: string | null;
  /** 实时思考详情 */
  thinking: OrchestrationThinking | null;
  /** 完成摘要 */
  completionSummary?: string;
}

/** ── 多层委托树类型 ── */

/** Agent 在委托树中的角色 */
export type DelegationRole = 'supervisor' | 'sub_supervisor' | 'executor';

/** Agent 节点状态 */
export type DelegationStatus = 'idle' | 'analyzing' | 'working' | 'waiting' | 'done';

/** 委托树节点 */
export interface DelegationNode {
  /** 唯一标识（agent_id 或临时 id） */
  id: string;
  /** Agent 真实名字，如 "架构师-Agent" */
  agentName: string;
  /** 角色图标 emoji */
  agentEmoji: string;
  /** 颜色 */
  color: string;
  /** 委托角色 */
  role: DelegationRole;
  /** 分配的任务描述 */
  task: string;
  /** 当前状态 */
  status: DelegationStatus;
  /** 父节点 id（null = 顶层主管） */
  parentId: string | null;
  /** 子节点 id 列表 */
  childIds: string[];
  /** 实时思考详情 */
  thinking: {
    summary: string;
    model?: string;
    elapsed: number;
    toolCalls: Array<{ tool: string; status: 'running' | 'done' | 'error'; detail?: string }>;
    execMode?: string;
    iterations?: number;
  } | null;
  /** 产出物列表 */
  outputs: Array<{ name: string; size: string; type: string }>;
  /** 耗时（秒） */
  duration?: number;
}

/** 工作区整体状态 */
export interface WorkspaceState {
  /** 是否激活 */
  active: boolean;
  /** 是否已完成 */
  completed: boolean;
  /** 所有委托节点（id → node） */
  nodes: Record<string, DelegationNode>;
  /** 顶层主管 id */
  rootId: string | null;
  /** 当前选中的节点 id（详情面板） */
  selectedNodeId: string | null;
  /** 是否等待用户 HITL 确认 */
  hitlPending: boolean;
  /** HITL 确认数据 */
  hitlData: {
    message: string;
    options: Array<{ label: string; value: string }>;
  } | null;
  /** 完成摘要 */
  completionSummary?: string;
}

/** xyflow 节点数据（AgentNode 组件 props） */
export interface AgentNodeData {
  node: DelegationNode;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

/** xyflow 边数据（DelegationEdge 组件 props） */
export interface DelegationEdgeData {
  task: string;
  isPending: boolean;
  isSubSupervisor: boolean;
}
