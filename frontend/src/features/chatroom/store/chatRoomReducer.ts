/** Chat room reducer
 *
 * 纯函数：(state, action) -> state
 * 副作用（WS 发送、focus、滚动）由 hook 层处理。
 *
 * 此 reducer 不依赖 Date.now()/Math.random() —— 但 helpers.makeId 内部用
 * Math.random()。这是可接受的：id 的随机性对功能无影响，对测试影响通过
 * _resetIdSeqForTest 控制即可。如未来需要严格确定性，把 id 提到 action 里传入。
 */

import type {
  ChatRoomState,
  TimelineItem,
  AgentMessageItem,
  UserMessageItem,
  UserInterruptItem,
  SystemDividerItem,
  HitlCardItem,
  PendingHitl,
  ArtifactFile,
  WorkPlan,
  WorkPhase,
  ThinkingAgent,
  PendingInterrupt,
} from '../types/state';
import { makeInitialChatRoomState, type WorkTaskStatus } from '../types/state';
import type { ChatRoomAction } from './actions';
import {
  makeId,
  isMetaPhaseId,
  metaPhaseFromSource,
  applyAgentStatusToMetaPhases,
  setMetaPhaseDone,
  finalizeAllThinkingPhases,
  upsertThinkingAgent,
  removeThinkingAgent,
  updateThinkingAgentSummary,
  reasoningPayloadToDetail,
  patchLastAgentMessage,
  patchHitlCard,
  inferAgentEmoji,
  type PendingReasoningMap,
} from './helpers';
import { dagItemToWorkTask } from '../types/events';
import { DELTA_PLAN_OPTIONS } from '../constants/hitl-options';

/** 内部携带的 pending reasoning 缓存（不暴露给 UI） */
interface InternalState {
  pendingReasonings: PendingReasoningMap;
}

/** ChatRoomState + InternalState 的合体 */
export interface ReducerState extends ChatRoomState {
  _internal: InternalState;
}

const INITIAL_INTERNAL: InternalState = {
  pendingReasonings: {},

};

/** 创建带内部状态的初始 state */
export function makeInitialReducerState(sessionId: string): ReducerState {
  return {
    ...makeInitialChatRoomState(sessionId),
    _internal: { ...INITIAL_INTERNAL },
  };
}

/** 当前时间。
 *
 * 设计权衡：reducer 调用 Date.now() 是不纯的副作用，但 timestamp 仅用于
 * timeline 的展示排序（hh:mm:ss）和耗时计算，不影响 state 形状或转换正确性。
 * 测试通过断言"结构"而非"具体 timestamp 值"来保持稳定。
 *
 * 如未来需要 100% 纯函数（如 time-travel debugging），可让所有 action 携带 timestamp。 */
function nowFromAction(_state: ReducerState): number {
  return Date.now();
}

// ── main reducer ──

export function chatRoomReducer(
  state: ReducerState,
  action: ChatRoomAction,
): ReducerState {
  switch (action.type) {
    // ── CTRL ──

    case 'CTRL/INIT_SESSION': {
      return makeInitialReducerState(action.sessionId);
    }

    case 'CTRL/WS_CONNECTED': {
      return { ...state, wsConnected: action.connected };
    }

    case 'CTRL/HISTORY_REFRESH': {
      // 重连轮询用：递增版本号触发 useSessionHistory 重载
      return { ...state, historyVersion: (state.historyVersion || 0) + 1 };
    }

    case 'CTRL/HISTORY_LOADED': {
      // 历史加载：去重 HITL 卡片（相同 hitlId 只保留 answered > pending）
      const existingHitlIds = new Set(
        state.messages.filter(m => m.kind === 'hitl_card').map(m => (m as HitlCardItem).hitlId)
      );
      // 对历史消息中的 HITL 卡片，按 hitlId 去重，answered 优先，合并通知+回答数据
      const hitlBest = new Map<string, TimelineItem>();
      for (const m of action.messages) {
        if (m.kind === 'hitl_card') {
          const h = m as HitlCardItem;
          const cur = hitlBest.get(h.hitlId);
          if (!cur) {
            hitlBest.set(h.hitlId, m);
          } else if (h.cardState === 'answered' && (cur as HitlCardItem).cardState !== 'answered') {
            // 用已回答版本，但保留通知中的 message 和 options
            const curPending = cur as HitlCardItem;
            const merged: HitlCardItem = {
              ...h,
              message: curPending.message || h.message,  // 通知的消息优先
              options: curPending.options?.length ? curPending.options : h.options, // 通知的选项优先
            };
            hitlBest.set(h.hitlId, merged);
          } else if ((cur as HitlCardItem).cardState === 'answered' && h.cardState !== 'answered') {
            // 当前是已回答版本，新来的是通知 → 保留已回答版本但补充通知数据
            const curAnswered = cur as HitlCardItem;
            if (!curAnswered.message || curAnswered.message === curAnswered.answer) {
              const merged: HitlCardItem = {
                ...curAnswered,
                message: h.message || curAnswered.message,
                options: h.options?.length ? h.options : curAnswered.options,
              };
              hitlBest.set(h.hitlId, merged);
            }
          }
        }
      }
      // 替换：每个 hitlId 用最佳版本替代（合并后的对象）
      const seenHitlIds = new Set<string>();
      const filteredHistory = action.messages.map(m => {
        if (m.kind !== 'hitl_card') return m;
        const h = m as HitlCardItem;
        if (existingHitlIds.has(h.hitlId)) return null;
        if (seenHitlIds.has(h.hitlId)) return null;
        seenHitlIds.add(h.hitlId);
        // 返回合并后的最佳版本
        return hitlBest.get(h.hitlId) || m;
      }).filter(Boolean) as TimelineItem[];
      const next: ReducerState = { ...state, messages: [...state.messages, ...filteredHistory] };
      if (action.workPlan !== undefined) {
        next.workPlan = action.workPlan;
        if (action.workPlan) next.workPlanVersion = state.workPlanVersion + 1;
      }
      if (action.artifacts && action.artifacts.length > 0) {
        next.artifacts = action.artifacts;
      }
      if (action.routing !== undefined) {
        next.routing = action.routing;
      }
      if (action.workspacePath !== undefined) {
        next.workspacePath = action.workspacePath;
      }
      // 恢复 pendingHitl
      let lastHitl: PendingHitl | null = null;
      for (const item of [...next.messages].reverse()) {
        if (item.kind === 'hitl_card' && item.cardState !== 'answered') {
          lastHitl = {
            id: (item as HitlCardItem).hitlId,
            kind: (item as HitlCardItem).hitlKind,
            message: (item as HitlCardItem).message,
            options: (item as HitlCardItem).options,
            cardState: 'pending',
            createdAt: item.timestamp,
          };
          break;
        }
      }
      if (lastHitl) {
        next.pendingHitl = lastHitl;
        next.executionState = 'hitl_pending';
      }
      return next;
    }

    case 'CTRL/TICK': {
      // 仅占位，UI 端 selector 自行 tick 计算耗时
      return state;
    }

    // ── WS · routing decision ──

    case 'WS/ROUTING_DECISION': {
      const mode = action.payload.mode;
      // M0 完成
      const phases = setMetaPhaseDone(state.metaPhases, 'm0_intent', '已路由', nowFromAction(state));

      if (mode === 'single_agent') {
        // 单 Agent 路径：跳过 M1~M7
        const skipped = phases.map(p =>
          p.id === 'm0_intent' ? p : { ...p, status: 'skipped' as const }
        );
        return {
          ...state,
          routing: 'single_agent',
          metaPhases: skipped,
          executionState: 'thinking',
        };
      }

      // 多 Agent 路径
      return {
        ...state,
        routing: 'multi_agent',
        metaPhases: phases,
        executionState: 'thinking',
      };
    }

    // ── WS · agent_status ──

    case 'WS/AGENT_STATUS': {
      const p = action.payload;
      const now = nowFromAction(state);
      const newPhases = applyAgentStatusToMetaPhases(state.metaPhases, p, now);

      // 思考指示器更新
      let newThinking = state.thinkingAgents;
      if (p.status === 'thinking' || p.status === 'working') {
        const metaPhase = isMetaPhaseId(p.agent_id) ? p.agent_id : metaPhaseFromSource(p.agent_id) ?? undefined;
        const agent: ThinkingAgent = {
          agentId: p.agent_id,
          agentName: p.agent_name,
          agentEmoji: inferAgentEmoji(p.agent_name, p.agent_id),
          metaPhase,
          summary: p.summary ?? '',
          startedAt: now,
          status: 'thinking',
        };
        newThinking = upsertThinkingAgent(newThinking, agent);
      } else if (p.status === 'done' || p.status === 'idle') {
        newThinking = removeThinkingAgent(newThinking, p.agent_id);
      }

      // 当前阶段
      let currentMetaPhaseId = state.currentMetaPhaseId;
      if (isMetaPhaseId(p.agent_id)) {
        if (p.status === 'thinking' || p.status === 'working') {
          currentMetaPhaseId = p.agent_id;
        } else if ((p.status === 'done' || p.status === 'idle') && currentMetaPhaseId === p.agent_id) {
          currentMetaPhaseId = null;
        }
      }

      return {
        ...state,
        metaPhases: newPhases,
        thinkingAgents: newThinking,
        currentMetaPhaseId,
      };
    }

    // ── WS · agent_message ──

    case 'WS/AGENT_MESSAGE': {
      const p = action.payload;
      if (!p.content) return state;

      const source = action.source;
      const metaPhase = state.routing === 'single_agent'
        ? null
        : (metaPhaseFromSource(source) ?? state.currentMetaPhaseId ?? null);
      const reasoning = state._internal.pendingReasonings[p.agent];

      const newItem: AgentMessageItem = {
        id: makeId('agent_msg'),
        kind: 'agent_message',
        agentId: source ?? p.agent,
        agentName: p.agent,
        agentEmoji: inferAgentEmoji(p.agent, source),
        metaPhase,
        taskId: p.task_id,
        content: p.content,
        reasoning,
        execMode: (p as any).exec_mode || reasoning?.execMode || '',
        model: p.model,
        latency: p.latency,
        artifactIds: [],
        expanded: false,
        isStreaming: false,
        timestamp: nowFromAction(state),
      };

      // 消耗 pending reasoning
      const newPendingReasonings = { ...state._internal.pendingReasonings };
      delete newPendingReasonings[p.agent];

      // 从 thinkingAgents 移除该 agent
      const newThinking = state.thinkingAgents.filter(
        a => a.agentName !== p.agent && a.agentId !== source
      );

      // 替换流式占位消息（如果存在）
      const streamId = `stream_${p.agent}`;
      const streamIdx = state.messages.findIndex(m => m.id === streamId);
      let newMessages: TimelineItem[];
      if (streamIdx >= 0) {
        newMessages = state.messages.map((m, i) =>
          i === streamIdx ? { ...newItem, id: newItem.id, isStreaming: false } : m
        );
      } else {
        newMessages = [...state.messages, newItem];
      }

      return {
        ...state,
        messages: newMessages,
        thinkingAgents: newThinking,
        _internal: {
          ...state._internal,
          pendingReasonings: newPendingReasonings,
        },
      };
    }

    // ── WS · thinking_update ──

    case 'WS/THINKING_UPDATE': {
      const p = action.payload;
      // 仅更新思考指示器摘要
      const newThinking = updateThinkingAgentSummary(state.thinkingAgents, p.agent, p.detail);
      return { ...state, thinkingAgents: newThinking };
    }

    // ── WS · reasoning_complete ──

    case 'WS/REASONING_COMPLETE': {
      const p = action.payload;
      const detail = reasoningPayloadToDetail(p);
      // 缓存，待 agent_message 消费
      const newPendingReasonings = {
        ...state._internal.pendingReasonings,
        [p.agent]: detail,
      };
      // 若已有该 agent 的 message（部分场景 reasoning 在 message 之后），就 patch 进去
      const newMessages = patchLastAgentMessage(state.messages, p.agent, { reasoning: detail, execMode: detail.execMode || '' });
      return {
        ...state,
        messages: newMessages,
        _internal: {
          ...state._internal,
          pendingReasonings: newPendingReasonings,
        },
      };
    }

    // ── WS · hitl_request ──

    case 'WS/HITL_REQUEST': {
      const p = action.payload;
      // Dedup：同样的 message + kind 还 pending 时跳过（防止后端重复推送）
      if (state.pendingHitl &&
          state.pendingHitl.kind === p.type &&
          state.pendingHitl.message === p.message &&
          state.pendingHitl.cardState !== 'answered') {
        return state;
      }
      const hitlId = makeId('hitl');
      const pendingHitl: PendingHitl = {
        id: hitlId,
        kind: p.type,
        message: p.message,
        options: p.options,
        cardState: 'pending',
        createdAt: nowFromAction(state),
      };
      const cardItem: HitlCardItem = {
        id: makeId('item'),
        kind: 'hitl_card',
        hitlId,
        cardState: 'pending',
        hitlKind: p.type,
        message: p.message,
        options: p.options,
        timestamp: nowFromAction(state),
      };
      return {
        ...state,
        pendingHitl,
        messages: [...state.messages, cardItem],
        executionState: 'hitl_pending',
      };
    }

    // ── WS · phase_update（M1 给的粗版 phases_plan） ──

    case 'WS/PHASE_UPDATE': {
      const p = action.payload;
      if (!p.phases || p.phases.length === 0) return state;

      // 只在 workPlan 还没建立时初始化（M4 task_dag 来时会覆盖）
      if (state.workPlan) return state;

      const phases: WorkPhase[] = p.phases.map((item, i) => {
        const name = typeof item === 'string' ? item : item.name;
        return {
          id: `phase-${i + 1}`,
          name,
          status: 'pending',
          taskIds: [],
        };
      });
      const newWorkPlan: WorkPlan = {
        phases,
        tasks: {},
        totalTasks: 0,
        doneTasks: 0,
      };
      return {
        ...state,
        workPlan: newWorkPlan,
        workPlanVersion: 1,
      };
    }

    // ── WS · files_changed ──

    case 'WS/FILES_CHANGED': {
      const p = action.payload;
      const now = nowFromAction(state);
      const newArtifacts: ArtifactFile[] = p.files.map(f => ({
        id: makeId('art'),
        name: f.name,
        path: f.path ?? f.name,
        sizeBytes: f.size ?? 0,
        producerAgentId: f.producer_agent_id ?? '',
        producerAgentName: f.producer_agent_name ?? '',
        producerTaskId: f.producer_task_id,
        status: f.status ?? 'created',
        createdAt: now,
      }));
      // 关联到 producer 对应的最近一条 agent_message：按 task_id 或 agent_name 匹配
      const newMessages = state.messages.map(m => {
        if (m.kind !== 'agent_message') return m;
        const matched = newArtifacts.filter(a =>
          (a.producerTaskId && a.producerTaskId === m.taskId) ||
          (a.producerAgentName && a.producerAgentName === m.agentName)
        );
        if (matched.length === 0) return m;
        return { ...m, artifactIds: [...m.artifactIds, ...matched.map(a => a.id)] };
      });
      // 按路径去重
      const existingPaths = new Set(state.artifacts.map(a => a.path));
      const uniqueNew = newArtifacts.filter(a => !existingPaths.has(a.path));
      return {
        ...state,
        artifacts: [...state.artifacts, ...uniqueNew],
        messages: newMessages,
      };
    }

    // ── WS · message_complete ──

    case 'WS/MESSAGE_COMPLETE': {
      const now = nowFromAction(state);
      return {
        ...state,
        metaPhases: finalizeAllThinkingPhases(state.metaPhases, now),
        thinkingAgents: [],
        currentMetaPhaseId: null,
        executionState: 'idle',
        pendingHitl: null,
        pendingInterrupt: null,
      };
    }

    // ── WS · tool_call ──

    case 'WS/TOOL_CALL': {
      // 工具调用：暂时只更新 thinkingAgents 的 summary
      const p = action.payload;
      const newThinking = updateThinkingAgentSummary(
        state.thinkingAgents,
        p.agent,
        `🔧 调用 ${p.tool}`,
      );
      return { ...state, thinkingAgents: newThinking };
    }

    // ── WS · stream_token（流式渲染） ──

    case 'WS/STREAM_TOKEN': {
      const p = action.payload;
      const streamId = `stream_${p.agent}`;
      const existingIdx = state.messages.findIndex(m => m.id === streamId);

      if (existingIdx >= 0) {
        // 追加 token 到已有流式消息
        const newMessages = state.messages.map((m, i) => {
          if (i !== existingIdx) return m;
          if (m.kind === 'agent_message') {
            return { ...m, content: m.content + p.token, isStreaming: true };
          }
          return m;
        });
        return { ...state, messages: newMessages };
      }

      // 创建新的流式消息占位
      const streamMsg: AgentMessageItem = {
        id: streamId,
        kind: 'agent_message',
        agentId: p.agent_id || p.agent,
        agentName: p.agent,
        agentEmoji: '🤖',
        content: p.token,
        model: '',
        latency: 0,
        phase: null,
        metaPhase: null,
        taskId: p.task_id || null,
        nodeKey: p.node_key || null,
        artifactIds: [],
        expanded: false,
        isStreaming: true,
        timestamp: nowFromAction(state),
      };
      return {
        ...state,
        messages: [...state.messages, streamMsg],
        thinkingAgents: updateThinkingAgentSummary(
          state.thinkingAgents, p.agent, '流式输出中...',
        ),
      };
    }

    // ── WS · error ──

    case 'WS/ERROR': {
      const errItem: SystemDividerItem = {
        id: makeId('div'),
        kind: 'system_divider',
        reason: 'paused',
        text: `❌ 错误：${action.payload.message}`,
        timestamp: nowFromAction(state),
      };
      return {
        ...state,
        messages: [...state.messages, errItem],
      };
    }

    // ── WS · task_dag（M4 完成时的细版 DAG） ──

    case 'WS/TASK_DAG': {
      const p = action.payload;
      // eslint-disable-next-line no-console
      console.log('[reducer] task_dag received:', { phases: p.phases?.length, total: p.total_tasks, sample: p.phases?.[0] });
      const tasks: WorkPlan['tasks'] = {};
      const phases: WorkPhase[] = p.phases.map(ph => {
        const taskIds: string[] = [];
        ph.tasks.forEach(t => {
          const wt = dagItemToWorkTask(t, ph.id);
          tasks[wt.id] = wt;
          taskIds.push(wt.id);
        });
        return {
          id: ph.id,
          name: ph.name,
          status: 'pending',
          taskIds,
        };
      });
      const newWorkPlan: WorkPlan = {
        phases,
        tasks,
        totalTasks: p.total_tasks,
        doneTasks: 0,
      };
      return {
        ...state,
        workPlan: newWorkPlan,
        workPlanVersion: state.workPlanVersion + 1,
      };
    }

    // ── WS · task_status ──

    case 'WS/TASK_STATUS': {
      if (!state.workPlan) return state;
      const p = action.payload;
      const task = state.workPlan.tasks[p.task_id];
      if (!task) return state;

      const now = nowFromAction(state);
      const newStatus: WorkTaskStatus =
        p.status === 'pending' ? 'pending'
        : p.status === 'running' ? 'running'
        : p.status === 'done' ? 'done'
        : p.status === 'failed' ? 'failed'
        : p.status === 'rejected' ? 'rejected'
        : p.status === 'rollback' ? 'rollback'
        : p.status === 'skipped' ? 'skipped'
        : 'retrying';

      const updatedTask: WorkPlan['tasks'][string] = {
        ...task,
        status: newStatus,
        startedAt: p.status === 'running' ? now : task.startedAt,
        endedAt: p.status === 'done' || p.status === 'failed' ? now : task.endedAt,
      };
      const newTasks = { ...state.workPlan.tasks, [p.task_id]: updatedTask };
      const doneTasks = Object.values(newTasks).filter(t => t.status === 'done').length;

      const newWorkPlan: WorkPlan = {
        ...state.workPlan,
        tasks: newTasks,
        doneTasks,
      };

      // 同步更新思考指示器
      let newThinking = state.thinkingAgents;
      if (p.status === 'running') {
        newThinking = upsertThinkingAgent(newThinking, {
          agentId: task.agentId,
          agentName: task.agentName,
          agentEmoji: task.agentEmoji,
          metaPhase: 'm6_execute',
          taskId: task.id,
          summary: task.name,
          startedAt: now,
          status: 'thinking',
        });
      } else if (p.status === 'done' || p.status === 'failed') {
        newThinking = removeThinkingAgent(newThinking, task.agentId);
      }

      return {
        ...state,
        workPlan: newWorkPlan,
        thinkingAgents: newThinking,
      };
    }

    // ── WS · execution_state（PR5） ──

    case 'WS/EXECUTION_STATE': {
      const p = action.payload;
      return { ...state, executionState: p.state };
    }

    // ── WS · interrupt_failed（PR5） ──

    case 'WS/INTERRUPT_FAILED': {
      const now = nowFromAction(state);
      const divider: SystemDividerItem = {
        id: makeId('div'),
        kind: 'system_divider',
        reason: 'paused',
        text: `⚠️ 介入处理失败：${action.reason}。已恢复原计划。`,
        timestamp: now,
      };
      return {
        ...state,
        messages: [...state.messages, divider],
        pendingInterrupt: null,
        // 回退到 executing（M6 还在跑）；若原本不是 executing，保留 idle
        executionState: state.pendingInterrupt ? 'executing' : 'idle',
      };
    }

    // ── WS · delta_plan（PR5） ──

    case 'WS/DELTA_PLAN': {
      const p = action.payload;
      const hitlId = makeId('hitl');
      const pendingHitl: PendingHitl = {
        id: hitlId,
        kind: 'delta_plan',
        message: p.summary,
        options: DELTA_PLAN_OPTIONS,
        cardState: 'pending',
        deltaPlan: { keep: p.keep, modify: p.modify, add: p.add, cancel: p.cancel, summary: p.summary },
        createdAt: nowFromAction(state),
      };
      const cardItem: HitlCardItem = {
        id: makeId('item'),
        kind: 'hitl_card',
        hitlId,
        cardState: 'pending',
        hitlKind: 'delta_plan',
        message: p.summary,
        options: pendingHitl.options,
        deltaPlan: pendingHitl.deltaPlan,
        timestamp: nowFromAction(state),
      };
      return {
        ...state,
        pendingHitl,
        workPlanDelta: pendingHitl.deltaPlan!,
        messages: [...state.messages, cardItem],
        executionState: 'hitl_pending',
      };
    }

    // ── UI · user send / interrupt / resume ──

    case 'UI/USER_SEND_MESSAGE': {
      const userItem: UserMessageItem = {
        id: makeId('user'),
        kind: 'user_message',
        content: action.content,
        timestamp: nowFromAction(state),
      };
      // 占位思考指示器
      const placeholder: ThinkingAgent = {
        agentId: '__placeholder__',
        agentName: '正在连接团队',
        agentEmoji: '⏺',
        summary: '...',
        startedAt: nowFromAction(state),
        status: 'thinking',
      };
      // 重置 meta phases（新一轮）
      const resetPhases = state.metaPhases.map(p => ({ ...p, status: 'pending' as const }));

      return {
        ...state,
        messages: [...state.messages, userItem],
        thinkingAgents: [placeholder],
        executionState: 'thinking',
        metaPhases: resetPhases,
        currentMetaPhaseId: null,
        routing: null,
      };
    }

    case 'UI/USER_SOFT_INTERRUPT': {
      const now = nowFromAction(state);
      // 决策 2：若 HITL 待答时被介入，自动把 HITL 标为 answered（用户介入）
      let messages = state.messages;
      let newPendingHitl = state.pendingHitl;
      if (state.pendingHitl) {
        messages = patchHitlCard(messages, state.pendingHitl.id, {
          cardState: 'answered',
          answer: '（用户介入，HITL 由介入流程接管）',
        });
        newPendingHitl = null;
      }

      const divider: SystemDividerItem = {
        id: makeId('div'),
        kind: 'system_divider',
        reason: 'interrupt',
        text: '⚠️ 你介入了（软）',
        timestamp: now,
      };
      const userItem: UserInterruptItem = {
        id: makeId('user'),
        kind: 'user_interrupt',
        content: action.content,
        mode: 'soft',
        timestamp: now,
      };
      const pendingInterrupt: PendingInterrupt = {
        id: makeId('interrupt'),
        userMessage: action.content,
        mode: 'soft',
        triggeredAt: now,
        state: 'analyzing',
      };
      return {
        ...state,
        messages: [...messages, divider, userItem],
        pendingHitl: newPendingHitl,
        answeringHitlId: null,
        pendingInterrupt,
        executionState: 'interrupting',
      };
    }

    case 'UI/USER_HARD_INTERRUPT': {
      const now = nowFromAction(state);
      const divider: SystemDividerItem = {
        id: makeId('div'),
        kind: 'system_divider',
        reason: 'paused',
        text: '⏹ 已硬中断，等待你的指示',
        timestamp: now,
      };
      const pendingInterrupt: PendingInterrupt = {
        id: makeId('interrupt'),
        userMessage: '',
        mode: 'hard',
        triggeredAt: now,
        state: 'awaiting_pause',
      };
      return {
        ...state,
        messages: [...state.messages, divider],
        pendingInterrupt,
        executionState: 'paused',
      };
    }

    case 'UI/USER_RESUME': {
      const now = nowFromAction(state);
      const divider: SystemDividerItem = {
        id: makeId('div'),
        kind: 'system_divider',
        reason: 'resumed',
        text: '▶ 恢复执行',
        timestamp: now,
      };
      const next: TimelineItem[] = [...state.messages, divider];
      if (action.content) {
        const userItem: UserInterruptItem = {
          id: makeId('user'),
          kind: 'user_interrupt',
          content: action.content,
          mode: 'soft',
          timestamp: now,
        };
        next.push(userItem);
      }
      return {
        ...state,
        messages: next,
        pendingInterrupt: null,
        executionState: 'executing',
      };
    }

    // ── UI · HITL ──

    case 'UI/HITL_ENTER_ANSWERING': {
      if (!state.pendingHitl || state.pendingHitl.id !== action.hitlId) return state;
      const newPending = { ...state.pendingHitl, cardState: 'answering' as const };
      const newMessages = patchHitlCard(state.messages, action.hitlId, { cardState: 'answering' });
      return {
        ...state,
        pendingHitl: newPending,
        answeringHitlId: action.hitlId,
        messages: newMessages,
      };
    }

    case 'UI/HITL_EXIT_ANSWERING': {
      if (!state.pendingHitl || state.pendingHitl.id !== action.hitlId) return state;
      const newPending = { ...state.pendingHitl, cardState: 'pending' as const };
      const newMessages = patchHitlCard(state.messages, action.hitlId, { cardState: 'pending' });
      return {
        ...state,
        pendingHitl: newPending,
        answeringHitlId: null,
        messages: newMessages,
      };
    }

    case 'UI/HITL_ANSWER': {
      if (!state.pendingHitl || state.pendingHitl.id !== action.hitlId) return state;
      const newPending = {
        ...state.pendingHitl,
        cardState: 'answered' as const,
        answer: action.answer,
        selectedValue: action.selectedValue,
      };
      const newMessages = patchHitlCard(state.messages, action.hitlId, {
        cardState: 'answered',
        answer: action.answer,
        selectedValue: action.selectedValue,
      });
      return {
        ...state,
        pendingHitl: null,
        answeringHitlId: null,
        messages: newMessages,
        executionState: 'thinking',
      };
    }

    // ── UI · drawer（多抽屉支持） ──

    case 'UI/TOGGLE_DRAWER': {
      const { kind } = action as { kind: import('../types/state').DrawerKind };
      const existingIdx = state.openDrawers.findIndex(d => d.kind === kind);
      if (existingIdx >= 0) {
        return { ...state, openDrawers: state.openDrawers.filter(d => d.kind !== kind) };
      }
      // 最多 3 个抽屉同时打开
      const current = state.openDrawers.length >= 3
        ? state.openDrawers.slice(1)
        : state.openDrawers;
      return {
        ...state,
        openDrawers: [...current, { kind, width: 30, order: current.length }],
      };
    }

    case 'UI/CLOSE_ALL_DRAWERS':
      return { ...state, openDrawers: [] };

    case 'UI/SET_DRAWER_WIDTH': {
      const { kind, width } = action as { kind: import('../types/state').DrawerKind; width: number };
      const w = Math.max(20, Math.min(60, width));
      return {
        ...state,
        openDrawers: state.openDrawers.map(d =>
          d.kind === kind ? { ...d, width: w } : d
        ),
      };
    }

    case 'UI/TOGGLE_MESSAGE_EXPANDED': {
      const newMessages = state.messages.map(m => {
        if (m.id !== action.messageId) return m;
        if (m.kind === 'agent_message') return { ...m, expanded: !m.expanded };
        if (m.kind === 'verification') return { ...m, expanded: !m.expanded };
        return m;
      });
      return { ...state, messages: newMessages };
    }

    case 'UI/TOGGLE_VERIFICATION_EXPANDED': {
      const newMessages = state.messages.map(m => {
        if (m.id !== action.messageId || m.kind !== 'verification') return m;
        return { ...m, expanded: !m.expanded };
      });
      return { ...state, messages: newMessages };
    }

    default: {
      // 编译期穷举检查
      const _exhaustive: never = action;
      void _exhaustive;
      return state;
    }
  }
}
