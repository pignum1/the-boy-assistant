/** Reducer 辅助函数（纯函数，无副作用） */

import type {
  ChatRoomState,
  MetaPhaseId,
  MetaPhaseState,
  TimelineItem,
  AgentMessageItem,
  HitlCardItem,
  ThinkingAgent,
  ReasoningDetail,
} from '../types/state';
import { META_PHASES_STATIC } from '../types/state';
import type {
  ReasoningCompletePayload,
  AgentStatusPayload,
} from '../types/events';

// ── id 生成（避免 Date.now() 在 reducer 内被调用——但 reducer 是 pure，外部传入更好） ──
// 为了保持纯函数性，我们在 reducer 中接收带 nonce 的 action；如果 action 没带 nonce，则用 deterministic seq。
// 实战：外部 dispatch 时已有 timestamp，id 用 timestamp + random 即可。这里暂时直接生成（pure-ish）。
let _idSeq = 0;
export function makeId(prefix: string): string {
  _idSeq += 1;
  return `${prefix}_${_idSeq}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 重置 id seq（仅测试用） */
export function _resetIdSeqForTest(): void {
  _idSeq = 0;
}

// ── meta phase 映射 ──

const META_PHASE_IDS: ReadonlySet<MetaPhaseId> = new Set(
  META_PHASES_STATIC.map(p => p.id)
);

/** 判断 agent_id 是否是 M-stage 节点 id */
export function isMetaPhaseId(id: string): id is MetaPhaseId {
  return META_PHASE_IDS.has(id as MetaPhaseId);
}

/** 从 source 字段（后端 LangGraph node name）反查 meta phase id */
export function metaPhaseFromSource(source?: string): MetaPhaseId | null {
  if (!source) return null;
  if (isMetaPhaseId(source)) return source;
  return null;
}

// ── meta phase 状态更新 ──

/** 标记某个 meta phase 为 thinking，同时把之前的 pending 标为 skipped */
export function setMetaPhaseThinking(
  phases: MetaPhaseState[],
  phaseId: MetaPhaseId,
  agentName: string,
  summary: string,
  now: number,
): MetaPhaseState[] {
  const idx = phases.findIndex(p => p.id === phaseId);
  if (idx < 0) return phases;
  return phases.map((p, i) => {
    if (i === idx) {
      return {
        ...p,
        status: 'thinking',
        currentAgent: agentName,
        currentSummary: summary,
        startedAt: p.startedAt ?? now,
      };
    }
    // 把当前阶段之前的 pending 标为 skipped（路径跳跃，如 M0→M1→M2 跳 M3 直接到 M4）
    if (i < idx && p.status === 'pending') {
      return { ...p, status: 'skipped' };
    }
    return p;
  });
}

/** 标记某个 meta phase 为 done */
export function setMetaPhaseDone(
  phases: MetaPhaseState[],
  phaseId: MetaPhaseId,
  summary: string | undefined,
  now: number,
): MetaPhaseState[] {
  const idx = phases.findIndex(p => p.id === phaseId);
  if (idx < 0) return phases;
  return phases.map((p, i) => {
    if (i === idx) {
      return {
        ...p,
        status: 'done',
        endedAt: now,
        summary: summary ?? p.summary,
        currentAgent: undefined,
        currentSummary: undefined,
      };
    }
    return p;
  });
}

/** 标记某个 meta phase 为 waiting（HITL） */
export function setMetaPhaseWaiting(
  phases: MetaPhaseState[],
  phaseId: MetaPhaseId,
): MetaPhaseState[] {
  return phases.map(p =>
    p.id === phaseId ? { ...p, status: 'waiting' } : p
  );
}

/** 把所有 thinking 的 phase 标为 done（message_complete 时调用） */
export function finalizeAllThinkingPhases(
  phases: MetaPhaseState[],
  now: number,
): MetaPhaseState[] {
  return phases.map(p =>
    p.status === 'thinking' || p.status === 'waiting'
      ? { ...p, status: 'done', endedAt: now }
      : p
  );
}

// ── thinking agent 列表维护 ──

export function upsertThinkingAgent(
  list: ThinkingAgent[],
  agent: ThinkingAgent,
): ThinkingAgent[] {
  const idx = list.findIndex(a => a.agentId === agent.agentId);
  if (idx < 0) return [...list, agent];
  return list.map((a, i) =>
    i === idx ? { ...a, ...agent, startedAt: a.startedAt } : a
  );
}

export function removeThinkingAgent(
  list: ThinkingAgent[],
  agentId: string,
): ThinkingAgent[] {
  return list.filter(a => a.agentId !== agentId);
}

export function updateThinkingAgentSummary(
  list: ThinkingAgent[],
  agentName: string,
  summary: string,
): ThinkingAgent[] {
  return list.map(a =>
    a.agentName === agentName ? { ...a, summary } : a
  );
}

// ── reasoning 转换 ──

export function reasoningPayloadToDetail(
  payload: ReasoningCompletePayload,
): ReasoningDetail {
  return {
    supervisorAnalysis: payload.supervisor_analysis,
    thinkingSteps: payload.thinking_steps,
    decisionSummary: payload.decision_summary,
    modelRouting: payload.model_routing ? {
      complexity: payload.model_routing.complexity,
      selectedModel: payload.model_routing.selected_model,
      fallbackUsed: payload.model_routing.fallback_used,
      fallbackReason: payload.model_routing.fallback_reason,
      provider: payload.model_routing.provider,
    } : undefined,
    toolCalls: payload.tool_calls?.map(tc => ({
      tool: tc.tool,
      status: (tc.success ? 'done' : 'error') as 'running' | 'done' | 'error',
      detail: tc.output ?? (tc.params ? JSON.stringify(tc.params) : undefined),
    })),
  };
}

// ── pending reasoning 暂存 ──

/** 用 Map 模拟 pendingReasoning，由 reducer 持有在 state.x.pendingReasonings */
export type PendingReasoningMap = Record<string, ReasoningDetail>;

// ── timeline 操作 ──

/** 找到最后一条匹配条件的 agent_message，更新它 */
export function patchLastAgentMessage(
  messages: TimelineItem[],
  agentName: string,
  patch: Partial<AgentMessageItem>,
): TimelineItem[] {
  // 从后往前找
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m.kind === 'agent_message' && m.agentName === agentName) {
      const next: TimelineItem[] = [...messages];
      next[i] = { ...m, ...patch };
      return next;
    }
  }
  return messages;
}

/** 找到对应 hitl_card 并 patch */
export function patchHitlCard(
  messages: TimelineItem[],
  hitlId: string,
  patch: Partial<HitlCardItem>,
): TimelineItem[] {
  const idx = messages.findIndex(
    m => m.kind === 'hitl_card' && m.hitlId === hitlId
  );
  if (idx < 0) return messages;
  const target = messages[idx] as HitlCardItem;
  const next: TimelineItem[] = [...messages];
  next[idx] = { ...target, ...patch };
  return next;
}

// ── workPlan 操作 ──

/** 重新计算 doneTasks */
export function recalcDoneTasks(workPlan: NonNullable<ChatRoomState['workPlan']>): number {
  return Object.values(workPlan.tasks).filter(t => t.status === 'done').length;
}

// ── agent emoji 推断（fallback） ──

const ROLE_EMOJI_MAP: Record<string, string> = {
  // 英文 role key
  supervisor: '👑',
  architect: '🏗',
  pm: '📋',
  ui: '🎨',
  designer: '🎨',
  frontend: '🌐',
  backend: '💻',
  fullstack: '💻',
  devops: '🚀',
  test: '🧪',
  qa: '🧪',
  verifier: '🔍',
  reviewer: '🔍',
  // 中文 agent name keyword（顺序：长词在前以避免被短词截胡）
  主管: '👑',
  架构师: '🏗',
  产品经理: '📋',
  产品: '📋',
  '前端工程师': '🌐',
  前端: '🌐',
  '后端工程师': '💻',
  后端: '💻',
  全栈: '💻',
  'ui设计师': '🎨',
  设计师: '🎨',
  设计: '🎨',
  运维: '🚀',
  部署: '🚀',
  测试员: '🧪',
  测试: '🧪',
  验证员: '🔍',
  验证: '🔍',
};

const NODE_EMOJI_MAP: Record<MetaPhaseId, string> = {
  m0_intent: '🧭',
  m1_analyze: '👑',
  m2_clarify: '🤔',
  m3_orchestrate: '🎯',
  m4_decompose: '🏗',
  m6_execute: '⚙️',
  m7_verify: '🔍',
};

export function inferAgentEmoji(
  agentName: string | undefined,
  source?: string,
  role?: string,
): string {
  if (role && ROLE_EMOJI_MAP[role.toLowerCase()]) return ROLE_EMOJI_MAP[role.toLowerCase()];
  if (source && isMetaPhaseId(source)) return NODE_EMOJI_MAP[source];
  if (agentName) {
    const lower = agentName.toLowerCase();
    // 中文匹配用原 name，英文匹配用 lower
    for (const key of Object.keys(ROLE_EMOJI_MAP)) {
      const isChinese = /[一-龥]/.test(key);
      const haystack = isChinese ? agentName : lower;
      if (haystack.includes(key)) return ROLE_EMOJI_MAP[key];
    }
  }
  return '🤖';
}

// ── agent_status payload → meta phase 影响 ──

/** 把 agent_status 翻译为对 metaPhases 的更新（如果 agent_id 是 M-stage 节点） */
export function applyAgentStatusToMetaPhases(
  phases: MetaPhaseState[],
  payload: AgentStatusPayload,
  now: number,
): MetaPhaseState[] {
  if (!isMetaPhaseId(payload.agent_id)) return phases;
  const phaseId = payload.agent_id;
  switch (payload.status) {
    case 'thinking':
    case 'working':
      return setMetaPhaseThinking(phases, phaseId, payload.agent_name, payload.summary ?? '', now);
    case 'done':
    case 'idle':
      return setMetaPhaseDone(phases, phaseId, payload.summary, now);
    default:
      return phases;
  }
}
