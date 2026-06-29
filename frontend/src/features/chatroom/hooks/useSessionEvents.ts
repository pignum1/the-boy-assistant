/** Session WebSocket 事件钩子：订阅讨论模式实时推送

内部负责加载历史消息，避免父组件同步问题。
切换 sessionId 时自动清空 → 加载历史 → 接收实时消息。
支持流式 token 事件，实时更新消息内容。
*/
import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentMsg } from './useTaskEvents';
import type { ReasoningTrace, TraceEntry, OrchestrationState, OrchestrationStage, OrchestrationThinking } from '../../../shared/types/session';
import type { TaskItem } from '../TaskCard';

interface ThinkingStep {
  agent: string;
  step: string;
  detail: string;
  timestamp: string;
  result?: string;
}

import { getWsUrl } from '../../../shared/api/client';

interface UseSessionEventsOptions {
  sessionId: string;
  onMessage?: (msg: AgentMsg) => void;
  maxRetries?: number;
}

export interface SessionMessageEnriched extends AgentMsg {
  reasoning?: ReasoningTrace;
  questions?: Array<{text: string; type: string}>;
  isThinking?: boolean;
  isStreaming?: boolean;   // 流式输出中
  avatarColor?: string;    // 头像颜色
  roleSlot?: string;       // 角色标识
  taskData?: {             // 任务卡片数据
    tasks: TaskItem[];
    stats: { total: number; done: number; inProgress: number };
  };
}

/** agent -> 颜色映射（按名字 hash） */
const AGENT_COLORS = [
  '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6',
];

function agentColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AGENT_COLORS[Math.abs(hash) % AGENT_COLORS.length];
}

function agentInitial(name: string): string {
  // 提取英文首字母，如 "产品经理-Agent" → "产"
  const match = name.match(/^[一-龥]/);
  return match ? match[0] : name.charAt(0).toUpperCase();
}

const TRACE_COLORS: Record<string, string> = {
  thinking: '#f59e0b',
  reasoning: '#3b82f6',
  tool_call: '#10b981',
  agent_status: '#8b5cf6',
  message_complete: '#64748b',
  storage: '#06b6d4',
  dispatch: '#14b8a6',
};
const TRACE_ICONS: Record<string, string> = {
  thinking: '💭',
  reasoning: '🧠',
  tool_call: '🔧',
  agent_status: '🟡',
  message_complete: '✅',
  storage: '💾',
  dispatch: '📨',
};

// ── M-Stage 编排流水线定义（与后端 streaming.py NODE_DISPLAY_NAMES 同步） ──

const M_STAGES: Array<{ id: string; label: string; shortLabel: string }> = [
  { id: 'm0_intent',      label: 'M0·意图识别',  shortLabel: '意图' },
  { id: 'm1_analyze',     label: 'M1·需求分析',  shortLabel: '分析' },
  { id: 'm2_clarify',     label: 'M2·澄清确认',  shortLabel: '澄清' },
  { id: 'm3_orchestrate', label: 'M3·Agent 编排', shortLabel: '编排' },
  { id: 'm4_decompose',   label: 'M4·任务分解',  shortLabel: '分解' },
  { id: 'm6_execute',     label: 'M6·DAG 执行',  shortLabel: '执行' },
  { id: 'm7_verify',      label: 'M7·独立验证',  shortLabel: '验证' },
];

function makeInitialStages(): OrchestrationStage[] {
  return M_STAGES.map(s => ({ ...s, status: 'pending' as const, agents: [] }));
}

const INITIAL_ORCHESTRATION: OrchestrationState = {
  active: false,
  completed: false,
  stages: makeInitialStages(),
  currentStageId: null,
  thinking: null,
};

function pushTrace(
  setTrace: React.Dispatch<React.SetStateAction<TraceEntry[]>>,
  type: TraceEntry['type'],
  agent: string,
  summary: string,
  detail?: string,
  data?: Record<string, unknown>,
) {
  setTrace(prev => [...prev, {
    id: `trace_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    type, agent,
    timestamp: new Date().toISOString(),
    summary, detail,
    icon: TRACE_ICONS[type] || '📌',
    color: TRACE_COLORS[type] || '#64748b',
    data,
  }]);
}

/** 将 API 返回的 SessionMessage 转为 AgentMsg（含 reasoning） */
function historyToMsg(m: {
  id: string; role: string; content: string;
  agent_name?: string; timestamp: string; metadata?: Record<string, unknown>;
}): SessionMessageEnriched {
  const meta = (m.metadata || {}) as Record<string, unknown>;
  const agent = m.role === 'user' ? '我' : (String(meta.agent || m.agent_name || 'Agent'));
  const hasReasoning = meta.model_routing || meta.tool_calls || meta.thinking_steps || meta.decision_summary;
  return {
    id: m.id,
    agent,
    content: m.content,
    timestamp: new Date(m.timestamp).getTime(),
    type: m.role === 'system' ? 'system' : 'message',
    avatarColor: agent === '我' ? '#64748b' : agentColor(agent),
    reasoning: hasReasoning ? {
      agent,
      model_routing: (meta.model_routing || {}) as ReasoningTrace['model_routing'],
      tool_calls: (meta.tool_calls || []) as ReasoningTrace['tool_calls'],
      context_used: (meta.context_used || {}) as ReasoningTrace['context_used'],
      decision_summary: meta.decision_summary as string | undefined,
      thinking_steps: meta.thinking_steps as string | undefined,
      prompt_length: meta.prompt_length as number | undefined,
      input_content: meta.input_content as string | undefined,
      supervisor_analysis: meta.supervisor_analysis as string | undefined,
      dispatch_guidance: meta.dispatch_guidance as string | undefined,
      latency: meta.latency as number | undefined,
    } : undefined,
  };
}

export function useSessionEvents({ sessionId, onMessage, maxRetries = 5 }: UseSessionEventsOptions) {
  const [messages, setMessages] = useState<SessionMessageEnriched[]>([]);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, { status: string; agent_name: string; summary: string; timestamp: string }>>({});
  const [connected, setConnected] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [traceEntries, setTraceEntries] = useState<TraceEntry[]>([]);
  const [orchestrationState, setOrchestrationState] = useState<OrchestrationState>(INITIAL_ORCHESTRATION);
  const [routingMode, setRoutingMode] = useState<'single_agent' | 'multi_agent' | null>(null);
  const [routingAgentName, setRoutingAgentName] = useState<string>('');
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const pendingReasoningRef = useRef<ReasoningTrace | null>(null);
  const lastSessionRef = useRef(sessionId);
  // 流式消息的引用（避免闭包问题）
  const streamingMsgIdRef = useRef<string | null>(null);
  const agentStatusesRef = useRef<Record<string, { status: string; agent_name: string; summary: string; timestamp: string }>>({});

  const connect = useCallback(() => {
    const url = getWsUrl(`/ws/sessions/${sessionId}`);
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const p = msg.payload || {};
        switch (msg.type) {
          // ── 流式 token ──
          case 'stream_token': {
            const agent = p.agent || 'Agent';
            const token = p.token || '';
            const tokenType = p.token_type || 'content_token';

            setMessages((prev) => {
              const streamId = `stream_${agent}`;
              streamingMsgIdRef.current = streamId;

              // 查找已有的流式消息
              const existingIdx = prev.findIndex(m => m.id === streamId);
              if (existingIdx >= 0) {
                // 更新现有流式消息
                return prev.map((m, i) => {
                  if (i !== existingIdx) return m;
                  const newContent = tokenType === 'content_token'
                    ? m.content + token
                    : m.content;
                  return {
                    ...m,
                    content: newContent,
                    isStreaming: true,
                    // 如果 thinking token，保留 reasoning
                    reasoning: tokenType === 'thinking_token'
                      ? { ...m.reasoning, thinking_steps: (m.reasoning?.thinking_steps || '') + token }
                      : m.reasoning,
                  };
                });
              } else {
                // 创建新的流式消息
                const newMsg: SessionMessageEnriched = {
                  id: streamId,
                  agent,
                  content: tokenType === 'content_token' ? token : '',
                  timestamp: Date.now(),
                  type: 'message',
                  isStreaming: true,
                  isThinking: false,
                  avatarColor: agentColor(agent),
                  reasoning: tokenType === 'thinking_token'
                    ? { agent, thinking_steps: token, model_routing: {}, tool_calls: [], context_used: {} }
                    : undefined,
                };
                return [...prev, newMsg];
              }
            });
            break;
          }

          // ── Agent 最终消息 ──
          case 'agent_message': {
            setMessages((prev) => {
              let agent = p.agent || 'System';
              // 如果 agent 是 UUID 或 "Agent"，尝试从 agentStatuses 查找真实名字
              if (agent === 'Agent' || /^[0-9a-f-]{30,}$/.test(agent)) {
                // 查找 agentStatuses 中匹配的 agent_name
                const statuses = agentStatusesRef.current;
                for (const s of Object.values(statuses)) {
                  if (s.agent_name && s.agent_name !== agent) {
                    // 使用第一个找到的真实名字
                    agent = s.agent_name;
                    break;
                  }
                }
              }
              const streamId = `stream_${agent}`;
              // 保存流式消息上的 reasoning（可能已被 reasoning_complete 设置）作为 fallback
              const streamMsg = prev.find(m => m.id === streamId) as SessionMessageEnriched | undefined;
              const streamReasoning = streamMsg?.reasoning;
              // 只删除对应 agent 的流式消息
              const filtered = prev.filter(m => m.id !== streamId);
              // 优先使用 pendingReasoningRef（匹配 agent 名），其次使用流式消息上的 reasoning
              const finalReasoning = pendingReasoningRef.current?.agent === agent
                ? pendingReasoningRef.current
                : streamReasoning;
              const finalMsg: SessionMessageEnriched = {
                id: `agent_${Date.now()}_${Math.random().toString(36).slice(2)}`,
                agent,
                content: p.content || '',
                timestamp: Date.now(),
                type: (p.type as string) === 'progress' ? 'system' : 'message',
                isStreaming: false,
                isThinking: false,
                avatarColor: agentColor(agent),
                reasoning: finalReasoning,
                questions: p.questions,
              };
              onMessage?.(finalMsg);
              return [...filtered, finalMsg];
            });
            // 只在 reasoning 属于当前 agent 时才清空
            if (pendingReasoningRef.current?.agent === (p.agent || '')) {
              pendingReasoningRef.current = null;
            }
            streamingMsgIdRef.current = null;
            pushTrace(setTraceEntries, 'dispatch', p.agent || 'Agent', `${p.agent} 回复完成`, p.content as string, {
              model: p.model, latency: p.latency,
              output: p.content, questions: p.questions,
            });
            break;
          }

          // ── 思考步骤更新 ──
          case 'thinking_update': {
            setThinkingSteps((prev) => [...prev, {
              agent: p.agent || 'System',
              step: p.step || '',
              detail: p.detail || '',
              timestamp: msg.timestamp || new Date().toISOString(),
              result: p.result,
            }]);
            pushTrace(setTraceEntries, 'thinking', p.agent || 'System', p.detail || p.step || '', p.result, { step: p.step });

            // ── 编排卡片思考详情更新 ──
            setOrchestrationState(prev => {
              if (!prev.active || prev.completed || !prev.thinking) return prev;
              return {
                ...prev,
                thinking: {
                  ...prev.thinking,
                  summary: p.detail || prev.thinking.summary,
                },
              };
            });

            // 将思考内容附加到当前流式消息，同时更新 content 让聊天室有可见的动作
            if (p.step === 'supervisor_analysis' || p.step === 'supervisor_dispatch' || p.step === 'swarm_thinking' || p.step === 'swarm_notify') {
              const agentName = p.agent || 'System';
              setMessages((prev) => {
                const streamId = `stream_${agentName}`;
                const existingIdx = prev.findIndex(m => m.id === streamId);

                // 构建可见的动作文字
                let actionText = '';
                if (p.step === 'supervisor_analysis') {
                  actionText = '🔍 正在分析消息...';
                } else if (p.step === 'supervisor_dispatch') {
                  // 尝试提取指派信息
                  const detail = p.detail || '';
                  actionText = '📋 ' + (detail || '正在指派任务...');
                } else if (p.step === 'swarm_thinking') {
                  actionText = '🐝 ' + (p.detail || 'Swarm 思考中...');
                } else if (p.step === 'swarm_notify') {
                  actionText = '📢 ' + (p.detail || '通知成员中...');
                }

                if (existingIdx >= 0) {
                  return prev.map((m, i) => i === existingIdx ? {
                    ...m,
                    content: actionText || m.content || '',
                    reasoning: {
                      ...(m.reasoning || { agent: agentName, model_routing: {}, tool_calls: [], context_used: {} }),
                      supervisor_analysis: p.step === 'supervisor_analysis'
                        ? ((m.reasoning as any)?.supervisor_analysis || '') + '\n' + (p.detail || '')
                        : (m.reasoning as any)?.supervisor_analysis,
                      dispatch_guidance: p.step === 'supervisor_dispatch'
                        ? ((m.reasoning as any)?.dispatch_guidance || '') + '\n' + (p.detail || '')
                        : (m.reasoning as any)?.dispatch_guidance,
                      thinking_steps: (p.step === 'swarm_thinking' || p.step === 'swarm_notify')
                        ? ((m.reasoning as any)?.thinking_steps || '') + '\n' + (p.detail || '')
                        : (m.reasoning as any)?.thinking_steps,
                    } as ReasoningTrace,
                  } : m);
                }
                // 创建新的流式消息
                const thinkingMsg: SessionMessageEnriched = {
                  id: streamId,
                  agent: agentName,
                  content: actionText,
                  timestamp: Date.now(),
                  type: 'message',
                  isStreaming: true,
                  isThinking: false,
                  avatarColor: agentColor(agentName),
                  reasoning: {
                    agent: agentName,
                    model_routing: {},
                    tool_calls: [],
                    context_used: {},
                    supervisor_analysis: p.step === 'supervisor_analysis' ? (p.detail || '') : undefined,
                    dispatch_guidance: p.step === 'supervisor_dispatch' ? (p.detail || '') : undefined,
                    thinking_steps: (p.step === 'swarm_thinking' || p.step === 'swarm_notify') ? (p.detail || '') : undefined,
                  } as ReasoningTrace,
                };
                return [...prev, thinkingMsg];
              });
            }
            break;
          }

          // ── 推理完成 ──
          case 'reasoning_complete': {
            const reasoningData: ReasoningTrace = {
              agent: p.agent || '',
              model_routing: p.model_routing || {},
              tool_calls: p.tool_calls || [],
              context_used: p.context_used || {},
              decision_summary: p.decision_summary,
              thinking_steps: p.thinking_steps,
              prompt_length: p.prompt_length,
              input_content: p.input_content,
              supervisor_analysis: p.supervisor_analysis,
              dispatch_guidance: p.dispatch_guidance,
              latency: p.latency,
            };
            pushTrace(setTraceEntries, 'reasoning', p.agent || '', p.decision_summary || '推理完成', p.thinking_steps as string, {
              tool_count: p.tool_calls?.length,
              model: p.model_routing?.selected_model,
              provider: p.model_routing?.provider,
              thinking_steps: p.thinking_steps,
              input: p.input_content,
              prompt_length: p.prompt_length,
              supervisor_analysis: p.supervisor_analysis,
              latency: p.latency,
            });

            // 保存到 pending — agent_message 事件会使用它
            pendingReasoningRef.current = reasoningData;

            // ── 编排卡片模型和工具调用更新 ──
            setOrchestrationState(prev => {
              if (!prev.active || prev.completed) return prev;
              const model = p.model_routing?.selected_model || prev.thinking?.model;
              // 更新已完成阶段的 summary
              const newStages = prev.stages.map(s => {
                if (s.status === 'thinking') {
                  return { ...s, status: 'done' as const, summary: p.decision_summary || s.summary };
                }
                return s;
              });
              return {
                ...prev,
                stages: newStages,
                thinking: prev.thinking ? {
                  ...prev.thinking,
                  model,
                  toolCalls: prev.thinking.toolCalls.map(tc => ({ ...tc, status: 'done' as const })),
                } : prev.thinking,
              };
            });

            // 将 reasoning 数据合并到当前流式消息中，并更新可见内容
            setMessages((prev) => {
              const agent = p.agent || '';
              const streamId = `stream_${agent}`;
              const existingIdx = prev.findIndex(m => m.id === streamId);
              if (existingIdx >= 0) {
                return prev.map((m, i) => {
                  if (i !== existingIdx) return m;
                  // 如果流式消息内容为空，设置一个有意义的状态文字
                  let updatedContent = m.content;
                  if (!updatedContent || updatedContent === '思考中') {
                    if (p.dispatch_guidance) {
                      // 主管指派完成
                      updatedContent = '✅ 分析完成，已指派任务';
                    } else if (p.decision_summary) {
                      updatedContent = p.decision_summary;
                    } else if (p.supervisor_analysis) {
                      updatedContent = '✅ 分析完成';
                    } else if (p.thinking_steps) {
                      updatedContent = '✅ 推理完成';
                    }
                  }
                  return {
                    ...m,
                    content: updatedContent,
                    reasoning: reasoningData,
                  };
                });
              }
              return prev;
            });
            break;
          }

          case 'message_complete': {
            setThinkingSteps([]);
            streamingMsgIdRef.current = null;
            // Reset routing state for next message
            setRoutingMode(null);
            setRoutingAgentName('');
            // 将所有剩余的流式消息标记为完成（去掉"输入中"状态）
            setMessages((prev) => prev.map(m =>
              m.id.startsWith('stream_') ? { ...m, isStreaming: false } : m
            ));
            pushTrace(setTraceEntries, 'message_complete', 'System', '消息处理完成', '', {});
            // 所有 agent 状态回归 idle
            setAgentStatuses((prev) => {
              const reset: Record<string, { status: string; agent_name: string; summary: string; timestamp: string }> = {};
              for (const [id, s] of Object.entries(prev)) {
                reset[id] = { ...s, status: 'idle', summary: `${s.agent_name} 空闲` };
              }
              return reset;
            });
            // ── 编排卡片标记完成 ──
            setOrchestrationState(prev => {
              if (!prev.active) return prev;
              const doneStages = prev.stages.map(s =>
                s.status === 'thinking' ? { ...s, status: 'done' as const } : s
              );
              return {
                ...prev,
                completed: true,
                stages: doneStages,
                currentStageId: null,
                thinking: null,
              };
            });
            break;
          }

          // ── 工具调用（替换掉流中的 JSON）──
          case 'tool_call': {
            const agent = p.agent || 'Agent';
            setMessages((prev) => {
              const streamId = `stream_${agent}`;
              return prev.map((m) =>
                m.id === streamId
                  ? { ...m, content: `🔧 正在执行工具: **${p.tool}**...`, isStreaming: false }
                  : m
              );
            });
            pushTrace(setTraceEntries, 'tool_call', agent, `🔧 ${p.tool}`, p.params ? JSON.stringify(p.params) : '', { tool: p.tool, params: p.params });

            // ── 编排卡片工具调用更新 ──
            setOrchestrationState(prev => {
              if (!prev.active || prev.completed || !prev.thinking) return prev;
              return {
                ...prev,
                thinking: {
                  ...prev.thinking,
                  toolCalls: [...prev.thinking.toolCalls, {
                    tool: p.tool as string || 'unknown',
                    status: 'running',
                    detail: p.params ? JSON.stringify(p.params).slice(0, 120) : undefined,
                  }],
                },
              };
            });
            break;
          }

          // ── Agent 状态灯 ──
          case 'agent_status': {
            const newStatus = {
              status: p.status as string || 'idle',
              agent_name: p.agent_name as string || '',
              summary: p.summary as string || '',
              timestamp: msg.timestamp || new Date().toISOString(),
            };
            setAgentStatuses((prev) => ({ ...prev, [p.agent_id as string]: newStatus }));
            // 同步 ref（用于 agent_message 中查找真实名字）
            agentStatusesRef.current = { ...agentStatusesRef.current, [p.agent_id as string]: newStatus };
            const statusEmoji: Record<string, string> = { idle: '⚪', thinking: '🟡', working: '🔵', done: '🟢', error: '🔴' };
            pushTrace(setTraceEntries, 'agent_status', p.agent_name as string || '', `${statusEmoji[p.status as string] || '🟡'} ${p.summary || p.status}`, '', { status: p.status, agent_id: p.agent_id });
            console.log('[ORCH] agent_status raw:', { agent_id: p.agent_id, status: p.status, agent_name: p.agent_name }); // TODO: remove debug log

            // ── 编排卡片状态更新 ──
            const agentId = p.agent_id as string;
            const agentStatus = p.status as string;
            console.log('[ORCH] agent_status:', { agentId, agentStatus, agentName: p.agent_name });
            // 检查是否是 M-stage 节点
            const stageIdx = M_STAGES.findIndex(s => s.id === agentId);
            if (stageIdx >= 0) {
              setOrchestrationState(prev => {
                console.log('[ORCH] updating stage:', { stageIdx, agentStatus, prevActive: prev.active, prevCompleted: prev.completed });
                if (prev.completed) return prev;
                const newStages = [...prev.stages];
                newStages[stageIdx] = { ...newStages[stageIdx] };

                if (agentStatus === 'thinking') {
                  newStages[stageIdx].status = 'thinking';
                  // 将当前阶段之前的 pending 阶段标记为 skipped
                  for (let j = 0; j < stageIdx; j++) {
                    if (newStages[j].status === 'pending') {
                      newStages[j].status = 'skipped';
                    }
                  }
                  return {
                    ...prev,
                    active: true,
                    stages: newStages,
                    currentStageId: agentId,
                    thinking: {
                      agentName: (p.agent_name as string) || newStages[stageIdx].label,
                      summary: (p.summary as string) || '',
                      model: undefined,
                      elapsed: undefined,
                      toolCalls: [],
                    },
                  };
                } else if (agentStatus === 'idle' || agentStatus === 'done') {
                  // 阶段完成
                  newStages[stageIdx].status = 'done';
                  return {
                    ...prev,
                    stages: newStages,
                    thinking: prev.currentStageId === agentId ? null : prev.thinking,
                  };
                }
                return { ...prev, stages: newStages };
              });
            }

            // ── 工作区事件分发 ──
            if (routingMode === 'multi_agent') {
              const wsAgentId = `agent-${agentId}`;
              if (agentStatus === 'thinking' || agentStatus === 'working') {
                window.dispatchEvent(new CustomEvent('workspace:agent-status', {
                  detail: { agentId: wsAgentId, status: 'working' },
                }));
              } else if (agentStatus === 'done') {
                window.dispatchEvent(new CustomEvent('workspace:agent-done', {
                  detail: { agentId: wsAgentId, duration: 0 },
                }));
              }
            }
            break;
          }

          // ── Agent 间 Mailbox 消息 ──
          case 'agent_to_agent': {
            const mailboxMsg: SessionMessageEnriched = {
              id: `mailbox_${Date.now()}_${Math.random().toString(36).slice(2)}`,
              agent: `${p.from_agent_name} → ${p.to_agent_name}`,
              content: p.content as string || '',
              timestamp: Date.now(),
              type: 'message',
              isThinking: false,
              isStreaming: false,
              avatarColor: '#06b6d4', // teal accent for Mailbox
            };
            setMessages((prev) => [...prev, mailboxMsg]);
            pushTrace(setTraceEntries, 'dispatch', `${p.from_agent_name} → ${p.to_agent_name || '@all'}`, `📬 ${p.message_type || 'direct'}: ${(p.content as string) || ''}`, '', { message_type: p.message_type });
            break;
          }

          // ── Planner 计划创建（DAG 模式）──
          case 'plan_created': {
            const plan = p.plan as { tasks?: Array<{id:string;seq:number;title:string;dependencies?:string[];status:string}>; total?: number } || {};
            const planTasks = (plan.tasks || []).map((t: {id:string;seq:number;title:string;dependencies?:string[];status:string}) => ({
              id: t.id, seq: t.seq, title: t.title,
              status: (t.status || 'pending') as TaskItem['status'],
              dependencies: t.dependencies || [],
            }));
            if (planTasks.length > 0) {
              setMessages((prev) => {
                const filtered = prev.filter(m => m.type !== 'task_card');
                const cardMsg: SessionMessageEnriched = {
                  id: `taskcard_plan_${Date.now()}`,
                  agent: 'Planner',
                  content: '任务计划已生成，回复 **/approve** 确认执行，或 **/reject 序号** 移除任务',
                  timestamp: Date.now(),
                  type: 'task_card',
                  isThinking: false, isStreaming: false,
                  avatarColor: '#f59e0b',
                  taskData: {
                    tasks: planTasks,
                    stats: { total: planTasks.length, done: 0, inProgress: 0 },
                  },
                };
                return [...filtered, cardMsg];
              });
            }
            break;
          }

          // ── 任务创建 ──
          case 'task_created': {
            const taskData = p.task as Record<string, unknown> || {};
            const seq = p.seq as number || 1;
            const total = p.total as number || 1;
            setMessages((prev) => {
              const existingCardIdx = prev.findIndex(m => m.type === 'task_card');
              if (existingCardIdx >= 0) {
                // 追加到已有任务卡片（去重）
                return prev.map((m, i) => {
                  if (i !== existingCardIdx) return m;
                  const cardData = (m as { taskData?: { tasks: TaskItem[]; stats: { total: number; done: number; inProgress: number } } }).taskData;
                  if (!cardData) return m;
                  // 检查是否已存在相同 ID 的任务
                  const taskId = taskData.id as string;
                  if (cardData.tasks.some(t => t.id === taskId)) return m;
                  const newTasks = [...cardData.tasks, {
                    id: taskId,
                    seq: cardData.tasks.length + 1,
                    title: taskData.title as string,
                    status: (taskData.status as string) || 'pending',
                    assigned_agent_name: taskData.assigned_agent_name as string,
                  }];
                  return {
                    ...m,
                    taskData: {
                      tasks: newTasks,
                      stats: { ...cardData.stats, total: newTasks.length },
                    },
                  };
                });
              } else {
                // 新建任务卡片消息
                const cardMsg: SessionMessageEnriched = {
                  id: `taskcard_${Date.now()}`,
                  agent: 'System',
                  content: '',
                  timestamp: Date.now(),
                  type: 'task_card',
                  isThinking: false,
                  isStreaming: false,
                  avatarColor: '#f59e0b',
                  taskData: {
                    tasks: [{
                      id: taskData.id as string,
                      seq,
                      title: taskData.title as string,
                      status: (taskData.status as string) || 'pending',
                      assigned_agent_name: taskData.assigned_agent_name as string,
                    }],
                    stats: { total, done: 0, inProgress: 0 },
                  },
                };
                return [...prev, cardMsg];
              }
            });
            break;
          }

          // ── 任务更新 ──
          case 'task_updated': {
            const taskId = p.task_id as string;
            const newStatus = p.status as string;
            const stats = p.stats as { total: number; done: number; inProgress: number } | undefined;
            setMessages((prev) => {
              return prev.map((m) => {
                if (m.type !== 'task_card') return m;
                const cardData = (m as { taskData?: { tasks: TaskItem[]; stats: { total: number; done: number; inProgress: number } } }).taskData;
                if (!cardData) return m;
                const updatedTasks = cardData.tasks.map(t =>
                  t.id === taskId ? { ...t, status: newStatus as TaskItem['status'] } : t
                );
                const newStats = stats || {
                  ...cardData.stats,
                  done: updatedTasks.filter(t => t.status === 'done').length,
                };
                return { ...m, taskData: { tasks: updatedTasks, stats: newStats } };
              });
            });
            break;
          }

          // ── 记忆存储完成 ──
          case 'storage_update': {
            pushTrace(setTraceEntries, 'storage', p.agent as string || 'System', `💾 已存储到记忆 · ${p.memory_level || 'context'}`, `记忆 ID: ${p.memory_id}`, { memory_id: p.memory_id, memory_level: p.memory_level, session_id: p.session_id });
            break;
          }

          case 'error': {
            setMessages((prev) => [...prev, {
              id: `err_${Date.now()}`,
              agent: 'System',
              content: p.message || 'Unknown error',
              timestamp: Date.now(),
              type: 'error',
              avatarColor: '#ef4444',
            }]);
            break;
          }

          // ── Collaboration Phase Update ──
          case 'phase_update': {
            const phases = (p.phases || []).map((item: string | { name: string; role?: string; goal?: string }) =>
              typeof item === 'string' ? { name: item, role: '', goal: '' } : item
            );
            // PhaseBar will pick this up via useCollabEvents
            window.dispatchEvent(new CustomEvent('collab-phase-update', {
              detail: { phases, current: p.current || 0 },
            }));

            // ── 工作区委托计划 ──
            if (phases.length > 0) {
              const children = phases.map((ph: { name: string; role?: string; goal?: string }, i: number) => ({
                id: `agent-phase-${i}`,
                name: ph.name,
                emoji: '🤖',
                task: ph.goal || ph.role || '',
                role: 'executor' as const,
              }));
              window.dispatchEvent(new CustomEvent('workspace:delegation-plan', {
                detail: {
                  plan: `已完成需求分析，共 ${phases.length} 个阶段`,
                  children,
                  rootId: 'supervisor-0',
                },
              }));

              // Check if all phases are completed
              const allDone = phases.every((ph: { name: string; role?: string; goal?: string }) =>
                ph.name.includes('✓') || ph.name.includes('✅')
              );
              if (allDone) {
                window.dispatchEvent(new CustomEvent('workspace:complete', {
                  detail: { summary: '所有阶段已完成' },
                }));
              }
            }
            break;
          }

          // ── Collaboration HITL Request ──
          case 'hitl_request': {
            window.dispatchEvent(new CustomEvent('collab-hitl-request', {
              detail: {
                type: p.type || 'confirmation',
                message: p.message || '',
                options: p.options || [],
              },
            }));
            break;
          }

          // ── Routing Decision (single_agent vs multi_agent) ──
          case 'routing_decision': {
            const mode = p.mode as string;
            const agentName = p.agent_name as string || '';
            setRoutingMode(mode as 'single_agent' | 'multi_agent');
            setRoutingAgentName(agentName);

            // For multi_agent, inject a system message to show the chain start
            if (mode === 'multi_agent') {
              setMessages((prev) => [...prev, {
                id: `routing_${Date.now()}`,
                agent: 'System',
                content: '🔄 已进入多Agent协作模式，系统将自动编排任务...',
                timestamp: Date.now(),
                type: 'system' as const,
                avatarColor: '#f59e0b',
              }]);
              // ── 激活工作区 ──
              window.dispatchEvent(new CustomEvent('workspace:init', {
                detail: {
                  supervisorId: 'supervisor-0',
                  supervisorName: 'Supervisor',
                  supervisorEmoji: '👑',
                  task: '分析需求并编排任务...',
                },
              }));
            }
            break;
          }

          case 'pong':
            break;
        }
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setConnected(false);
      if (retriesRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
        retriesRef.current += 1;
        setTimeout(connect, delay);
      }
    };

    ws.onerror = (err) => { console.error('[useSessionEvents] WebSocket error:', err); ws.close(); };
    wsRef.current = ws;
  }, [sessionId, onMessage, maxRetries]);

  // sessionId 变化时：清空 + 加载历史 + 重连
  useEffect(() => {
    if (lastSessionRef.current !== sessionId) {
      lastSessionRef.current = sessionId;
      setMessages([]);
      setThinkingSteps([]);
      setTraceEntries([]);
      setHistoryLoaded(false);
      pendingReasoningRef.current = null;
      streamingMsgIdRef.current = null;
      setOrchestrationState({ ...INITIAL_ORCHESTRATION, stages: makeInitialStages() });
    }

    const loadHistory = async () => {
      try {
        const API = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';
        const res = await fetch(`${API}/api/v1/sessions/${sessionId}/messages?limit=100`);
        if (res.ok) {
          const data = await res.json();
          const agentMsgs = (data.messages || []).map(historyToMsg);
          if (agentMsgs.length > 0) {
            // Cherry Studio 风格：reasoning 直接附加到 agent 消息上，不创建单独的思考气泡
            const enrichedMsgs: SessionMessageEnriched[] = [];
            let supervisorReasoning: ReasoningTrace | null = null;
            for (const msg of agentMsgs) {
              // 用户消息：重置 supervisor 标记
              if (msg.agent === '我') {
                supervisorReasoning = null;
              }
              // 主管分析数据附加到第一个 agent 消息上（Cherry Studio 风格：内联展示）
              if (msg.reasoning && msg.agent !== '我') {
                const r = msg.reasoning;
                if (!supervisorReasoning && r.supervisor_analysis) {
                  supervisorReasoning = r;
                }
                // 将 reasoning 直接附加到消息上（MessageBubble 会渲染内联思考过程）
                enrichedMsgs.push({
                  ...msg,
                  reasoning: r,
                });
              } else {
                enrichedMsgs.push(msg);
              }
            }
            setMessages(enrichedMsgs);
            // 从 API 加载任务列表，重建任务卡片
            try {
              const taskRes = await fetch(`${API}/api/v1/sessions/${sessionId}/tasks`);
              if (taskRes.ok) {
                const taskData = await taskRes.json();
                const allTasks = taskData.tasks || [];
                if (allTasks.length > 0) {
                  // 检查是否已有任务卡片（防止 StrictMode 双重渲染）
                  setMessages(prev => {
                    if (prev.some(m => m.type === 'task_card')) return prev;
                    const done = allTasks.filter((t: {status:string}) => t.status === 'done').length;
                    const inProgress = allTasks.filter((t: {status:string}) => t.status === 'in_progress').length;
                    const cardMsg: SessionMessageEnriched = {
                      id: `taskcard_history_${sessionId}`,
                      agent: 'System', content: '', timestamp: Date.now(),
                      type: 'task_card' as 'message', isThinking: false, isStreaming: false,
                      avatarColor: '#f59e0b',
                      taskData: {
                        tasks: allTasks.map((t: {id:string;title:string;status:string;assigned_agent_name?:string}, i: number) => ({
                          id: t.id, seq: i + 1, title: t.title, status: t.status,
                          assigned_agent_name: t.assigned_agent_name,
                        })),
                        stats: { total: allTasks.length, done, inProgress },
                      },
                    };
                    return [...prev, cardMsg];
                  });
                }
              }
            } catch { /* ignore */ }
            // 从历史消息重建 trace entries（含思考步骤）
            for (const msg of agentMsgs) {
              if (msg.reasoning) {
                // 思考步骤 trace
                if (msg.reasoning.decision_summary) {
                  pushTrace(setTraceEntries, 'thinking', msg.agent,
                    msg.reasoning.decision_summary,
                    msg.reasoning.thinking_steps as string,
                    {});
                }
                pushTrace(setTraceEntries, 'reasoning', msg.agent,
                  msg.reasoning.decision_summary || `${msg.agent} 推理完成`,
                  msg.reasoning.thinking_steps,
                  { tool_count: msg.reasoning.tool_calls?.length, model: msg.reasoning.model_routing?.selected_model });
                // 为每个 tool_call 创建独立的 trace entry
                if (msg.reasoning.tool_calls) {
                  for (const tc of msg.reasoning.tool_calls) {
                    pushTrace(setTraceEntries, 'tool_call', msg.agent,
                      `🔧 ${tc.tool}`,
                      tc.params ? JSON.stringify(tc.params) : '',
                      { tool: tc.tool, success: tc.success });
                  }
                }
              }
            }
          }
        }
      } catch { /* ignore */ }
      setHistoryLoaded(true);
    };
    loadHistory();

    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [sessionId, connect]);

  const sendMessage = useCallback((text: string, mentionedAgents?: string[]) => {
    const userMsg: SessionMessageEnriched = {
      id: `user_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      agent: '我',
      content: text,
      timestamp: Date.now(),
      type: 'message',
      avatarColor: '#64748b',
    };
    setMessages((prev) => [...prev, userMsg]);
    onMessage?.(userMsg);
    pushTrace(setTraceEntries, 'dispatch', '用户', `用户发送`, text, {});

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        message: text,
        mentioned_agents: mentionedAgents || [],
      }));
    }
  }, [onMessage]);

  const sendPing = useCallback(() => {
    wsRef.current?.send('ping');
  }, []);

  /** Send HITL resume response via WebSocket */
  const sendHitlResume = useCallback((response: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'hitl_resume',
        response,
      }));
    }
  }, []);

  const addTaskToCard = useCallback((task: {id:string;title:string;status:string;assigned_agent_name?:string}) => {
    setMessages(prev => {
      const cardIdx = prev.findIndex(m => m.type === 'task_card');
      if (cardIdx >= 0) {
        return prev.map((m, i) => {
          if (i !== cardIdx) return m;
          const cd = (m as { taskData?: { tasks: TaskItem[]; stats: { total: number; done: number; inProgress: number } } }).taskData;
          if (!cd || cd.tasks.some(t => t.id === task.id)) return m;
          return { ...m, taskData: { tasks: [...cd.tasks, { id: task.id, seq: cd.tasks.length + 1, title: task.title, status: task.status as TaskItem['status'], assigned_agent_name: task.assigned_agent_name }], stats: { ...cd.stats, total: cd.stats.total + 1 } } };
        });
      }
      // 没有任务卡片时创建新的
      const cardMsg: SessionMessageEnriched = {
        id: `taskcard_manual_${Date.now()}`,
        agent: 'System', content: '', timestamp: Date.now(),
        type: 'task_card' as 'message', isThinking: false, isStreaming: false,
        avatarColor: '#f59e0b',
        taskData: {
          tasks: [{ id: task.id, seq: 1, title: task.title, status: task.status as TaskItem['status'], assigned_agent_name: task.assigned_agent_name }],
          stats: { total: 1, done: task.status === 'done' ? 1 : 0, inProgress: 0 },
        },
      };
      return [...prev, cardMsg];
    });
  }, []);

  return { messages, thinkingSteps, traceEntries, agentStatuses, connected, sendMessage, sendPing, sendHitlResume, historyLoaded, addTaskToCard, orchestrationState, routingMode, routingAgentName };
}
