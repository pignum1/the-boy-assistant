/** WebSocket event payload types
 *
 * 与后端 streaming.py 的事件契约一一对应。所有 payload 都是只读输入。
 *
 * 分两类：
 * 1. 既有事件（兼容当前后端）
 * 2. PR4 / PR5 新增事件（前端先定义类型，后端补完后联动）
 */

import type {
  HitlOption,
  HitlKind,
  DeltaPlan,
  WorkTask,
} from './state';

// ── 既有事件（后端已发） ──

export interface RoutingDecisionPayload {
  mode: 'single_agent' | 'multi_agent';
  agent_name?: string;
}

export interface AgentStatusPayload {
  agent_id: string;
  agent_name: string;
  status: 'idle' | 'thinking' | 'working' | 'done' | 'error';
  summary?: string;
}

export interface AgentMessagePayload {
  agent: string;            // agent_name
  content: string;
  type?: 'message' | 'progress';
  model?: string;
  latency?: number;         // ms
  /** PR4: 关联到具体业务任务 */
  task_id?: string;
}

export interface ThinkingUpdatePayload {
  agent: string;
  step: string;             // "supervisor_analysis" | "supervisor_dispatch" | ...
  detail: string;
  result?: string;
}

export interface ReasoningCompletePayload {
  agent: string;
  model_routing?: {
    complexity?: string;
    selected_model?: string;
    fallback_used?: boolean;
    fallback_reason?: string;
    provider?: string;
  };
  tool_calls?: Array<{
    tool: string;
    params?: Record<string, unknown>;
    success: boolean;
    output?: string;
    error?: string;
  }>;
  context_used?: {
    memories_injected?: number;
    rag_chunks?: number;
    total_tokens?: number;
  };
  decision_summary?: string;
  thinking_steps?: string;
  supervisor_analysis?: string;
  dispatch_guidance?: string;
  latency?: number;
}

export interface HitlRequestPayload {
  type: HitlKind;
  message: string;
  options: HitlOption[];
}

export interface PhaseUpdatePayload {
  phases: Array<string | { name: string; role?: string; goal?: string }>;
  current?: number;
}

export interface FilesChangedPayload {
  files: Array<{
    name: string;
    path?: string;
    size?: number;
    status?: 'created' | 'modified' | 'deleted';
    producer_agent_id?: string;
    producer_agent_name?: string;
    producer_task_id?: string;
  }>;
}

export interface MessageCompletePayload {
  message: string;
}

export interface ToolCallPayload {
  agent: string;
  tool: string;
  params?: Record<string, unknown>;
}

export interface StreamTokenPayload {
  agent: string;
  token: string;
  token_type: 'content_token' | 'thinking_token';
}

export interface ErrorPayload {
  message: string;
  code?: string;
}

// ── PR4 新增事件（task_dag / task_status） ──

export interface TaskDagPayload {
  phases: Array<{
    id: string;
    name: string;
    tasks: Array<{
      id: string;
      name: string;
      agent_id: string;
      agent_name: string;
      agent_emoji?: string;
      depends_on?: string[];
    }>;
  }>;
  total_tasks: number;
}

export interface TaskStatusPayload {
  task_id: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'retrying';
  duration?: number;        // ms when done
  artifacts?: Array<{
    name: string;
    path?: string;
    size?: number;
  }>;
  error?: string;
}

// ── PR5 新增事件（介入闭环） ──

/** 客户端 → 服务端：介入 */
export interface InterruptOutbound {
  type: 'interrupt';
  mode: 'soft' | 'hard';
  message?: string;
}

/** 客户端 → 服务端：恢复 */
export interface ResumeOutbound {
  type: 'resume';
  message?: string;
}

/** 客户端 → 服务端：批准/拒绝 delta_plan */
export interface ApproveDeltaPlanOutbound {
  type: 'approve_delta_plan';
  approve: boolean;
  reason?: string;
}

/** 服务端 → 客户端：执行状态变化 */
export interface ExecutionStatePayload {
  state: 'paused' | 'executing' | 'interrupting';
  reason?: string;
}

/** 服务端 → 客户端：delta_plan 推送 */
export interface DeltaPlanPayload extends DeltaPlan {
  /** 业务任务版本号 */
  version: number;
}

// ── 统一 WS 入站消息 ──

/** 所有可能的入站消息（来自后端） */
export type InboundMessage =
  | { type: 'routing_decision'; payload: RoutingDecisionPayload; source?: string; timestamp?: string }
  | { type: 'agent_status'; payload: AgentStatusPayload; source?: string; timestamp?: string }
  | { type: 'agent_message'; payload: AgentMessagePayload; source?: string; timestamp?: string }
  | { type: 'thinking_update'; payload: ThinkingUpdatePayload; source?: string; timestamp?: string }
  | { type: 'reasoning_complete'; payload: ReasoningCompletePayload; source?: string; timestamp?: string }
  | { type: 'hitl_request'; payload: HitlRequestPayload; source?: string; timestamp?: string }
  | { type: 'hitl_notification'; payload: HitlRequestPayload; source?: string; timestamp?: string }
  | { type: 'task_output'; payload: AgentMessagePayload; source?: string; timestamp?: string }
  | { type: 'phase_update'; payload: PhaseUpdatePayload; source?: string; timestamp?: string }
  | { type: 'files_changed'; payload: FilesChangedPayload; source?: string; timestamp?: string }
  | { type: 'message_complete'; payload: MessageCompletePayload; source?: string; timestamp?: string }
  | { type: 'tool_call'; payload: ToolCallPayload; source?: string; timestamp?: string }
  | { type: 'stream_token'; payload: StreamTokenPayload; source?: string; timestamp?: string }
  | { type: 'error'; payload: ErrorPayload; source?: string; timestamp?: string }
  | { type: 'task_dag'; payload: TaskDagPayload; source?: string; timestamp?: string }
  | { type: 'task_status'; payload: TaskStatusPayload; source?: string; timestamp?: string }
  | { type: 'execution_state'; payload: ExecutionStatePayload; source?: string; timestamp?: string }
  | { type: 'delta_plan'; payload: DeltaPlanPayload; source?: string; timestamp?: string }
  | { type: 'pong'; payload?: Record<string, never> };

/** 所有可能的 JSON 出站消息（发到后端）
 *
 * 注意：心跳 "ping" 走裸字符串协议（非 JSON），由 hook 内部直接 send，不走 OutboundMessage 类型。
 */
export type OutboundMessage =
  | { type: 'chat'; message: string; mentioned_agents?: string[] }
  | { type: 'hitl_resume'; response: string }
  | InterruptOutbound
  | ResumeOutbound
  | ApproveDeltaPlanOutbound;

/** Worker 任务的轻量描述（task_dag 内嵌） */
export type TaskDagItem = TaskDagPayload['phases'][number]['tasks'][number];

/** 从 task_dag payload 还原 WorkTask */
export function dagItemToWorkTask(
  item: TaskDagItem,
  phaseId: string,
): WorkTask {
  return {
    id: item.id,
    phaseId,
    name: item.name,
    agentId: item.agent_id,
    agentName: item.agent_name,
    agentEmoji: item.agent_emoji ?? '🤖',
    dependsOn: item.depends_on ?? [],
    status: 'pending',
    version: 1,
    artifactIds: [],
  };
}
