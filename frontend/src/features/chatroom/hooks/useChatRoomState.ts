/** useChatRoomState — useReducer 包装 + selector hooks
 *
 * 提供 state、dispatch 以及一组派生 selector。
 * 不连接 WebSocket（那是 useWsEvents 的职责）。
 */

import { useReducer, useMemo } from 'react';
import {
  chatRoomReducer,
  makeInitialReducerState,
  type ReducerState,
} from '../store/chatRoomReducer';
import type { ChatRoomAction } from '../store/actions';
import type {
  ChatRoomState,
  TimelineItem,
  MetaPhaseState,
  ThinkingAgent,
  WorkPlan,
  ArtifactFile,
  PendingHitl,
  ExecutionState,
  DrawerKind,
  WorkTask,
} from '../types/state';

export interface ChatRoomStateApi {
  state: ChatRoomState;
  dispatch: React.Dispatch<ChatRoomAction>;
}

/** 主 hook：返回 state + dispatch */
export function useChatRoomState(sessionId: string): ChatRoomStateApi {
  const [reducerState, dispatch] = useReducer(
    chatRoomReducer,
    sessionId,
    makeInitialReducerState,
  );
  // 暴露给外部的 state 不包含 _internal
  const state: ChatRoomState = useMemo(() => {
    const { _internal, ...publicState } = reducerState as ReducerState;
    void _internal;
    return publicState;
  }, [reducerState]);
  return { state, dispatch };
}

// ── selector helpers（纯函数，给 UI 用） ──

export function selectMessages(state: ChatRoomState): TimelineItem[] {
  return state.messages;
}

export function selectMetaPhases(state: ChatRoomState): MetaPhaseState[] {
  return state.metaPhases;
}

export function selectCurrentMetaPhase(state: ChatRoomState): MetaPhaseState | null {
  if (!state.currentMetaPhaseId) return null;
  return state.metaPhases.find(p => p.id === state.currentMetaPhaseId) ?? null;
}

export function selectThinkingAgents(state: ChatRoomState): ThinkingAgent[] {
  return state.thinkingAgents;
}

export function selectWorkPlan(state: ChatRoomState): WorkPlan | null {
  return state.workPlan;
}

export function selectWorkPlanStats(state: ChatRoomState): {
  totalTasks: number;
  doneTasks: number;
  totalPhases: number;
  donePhases: number;
  percent: number;
} {
  const wp = state.workPlan;
  if (!wp) {
    return { totalTasks: 0, doneTasks: 0, totalPhases: 0, donePhases: 0, percent: 0 };
  }
  const totalPhases = wp.phases.length;
  const donePhases = wp.phases.filter(p => p.status === 'done').length;
  const percent = wp.totalTasks > 0 ? Math.floor((wp.doneTasks / wp.totalTasks) * 100) : 0;
  return {
    totalTasks: wp.totalTasks,
    doneTasks: wp.doneTasks,
    totalPhases,
    donePhases,
    percent,
  };
}

export function selectArtifacts(state: ChatRoomState): ArtifactFile[] {
  return state.artifacts;
}

export function selectPendingHitl(state: ChatRoomState): PendingHitl | null {
  return state.pendingHitl;
}

export function selectExecutionState(state: ChatRoomState): ExecutionState {
  return state.executionState;
}

export function selectOpenDrawer(state: ChatRoomState): DrawerKind | null {
  return state.openDrawer;
}

/** 判断输入框是否处于 answering 模式（影响按钮 + 提示条） */
export function selectIsAnsweringHitl(state: ChatRoomState): boolean {
  return state.answeringHitlId !== null;
}

/** 根据 executionState 判断输入框按钮文案 */
export function selectInputButtonLabel(state: ChatRoomState): {
  label: '发送' | '💡 介入' | '回复' | '继续';
  color: 'blue' | 'orange';
} {
  if (state.answeringHitlId) return { label: '回复', color: 'orange' };
  switch (state.executionState) {
    case 'thinking':
    case 'executing':
    case 'interrupting':
      return { label: '💡 介入', color: 'orange' };
    case 'paused':
      return { label: '继续', color: 'blue' };
    case 'hitl_pending':
      return { label: '回复', color: 'orange' };
    case 'idle':
    default:
      return { label: '发送', color: 'blue' };
  }
}

/** 找出 M6 期间正在跑的所有任务 */
export function selectRunningTasks(state: ChatRoomState): WorkTask[] {
  if (!state.workPlan) return [];
  return Object.values(state.workPlan.tasks).filter(t => t.status === 'running');
}
