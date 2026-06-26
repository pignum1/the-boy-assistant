/** ChatRoomView — PR3 新对话流入口（含双行进度条 + 抽屉）
 *
 * 布局：
 *   ┌─ PhaseProgressBar（顶 36~70px） ─────────────────────────┐
 *   ├─ Main (Chat + ThinkingIndicator + Banner + Input)  ─ │ Drawer (可选) │
 *   └─────────────────────────────────────────────────────┴──────────────┘
 */
import { useEffect, useRef, useCallback, lazy, Suspense } from 'react';
import { useChatRoomState } from './hooks/useChatRoomState';
import { useWsEvents } from './hooks/useWsEvents';
import { useTeamMembers } from './hooks/useTeamMembers';
import { useTeamMode } from './hooks/useTeamMode';
import { useSessionHistory } from './hooks/useSessionHistory';
import { PhaseProgressBar } from './components/header/PhaseProgressBar';
import { ChatStream } from './components/chat/ChatStream';
import { ThinkingIndicator } from './components/chat/ThinkingIndicator';
import { ChatInput, type ChatInputHandle } from './components/input/ChatInput';
import { InputModeBanner } from './components/input/InputModeBanner';
import { DrawerHost } from './components/drawers/DrawerHost';

// 抽屉组件延迟加载（用户点击时才加载，减少首屏体积）
const WorkPlanDrawer = lazy(() => import('./components/drawers/WorkPlanDrawer').then(m => ({ default: m.WorkPlanDrawer })));
const ArtifactsDrawer = lazy(() => import('./components/drawers/ArtifactsDrawer').then(m => ({ default: m.ArtifactsDrawer })));
const TeamDrawer = lazy(() => import('./components/drawers/TeamDrawer').then(m => ({ default: m.TeamDrawer })));
const WorkflowDrawer = lazy(() => import('./components/drawers/WorkflowDrawer').then(m => ({ default: m.WorkflowDrawer })));
import { injectStatusDotAnimation } from './components/shared/StatusDot';
import { ChatRoomErrorBoundary } from './components/shared/ErrorBoundary';
import { ensureGlobalAnimations } from './components/styles';
import type { DrawerKind, MetaPhaseId } from './types/state';

interface Props {
  sessionId: string;
  teamId: string;
}

export function ChatRoomView({ sessionId, teamId }: Props) {
  const { state, dispatch } = useChatRoomState(sessionId);
  const ws = useWsEvents({ sessionId, dispatch });
  const teamMembers = useTeamMembers(teamId);
  const collabMode = useTeamMode(teamId) || 'supervisor';
  useSessionHistory(sessionId, dispatch, state.messages.length);
  const inputRef = useRef<ChatInputHandle>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  // 注入全局动画
  useEffect(() => {
    injectStatusDotAnimation();
    ensureGlobalAnimations();
  }, []);

  // ── 用户操作处理 ──

  const handleSubmit = useCallback((text: string) => {
    if (state.answeringHitlId) {
      const hitlId = state.answeringHitlId;
      dispatch({ type: 'UI/HITL_ANSWER', hitlId, answer: text });
      ws.sendHitlResume(text);
      return;
    }
    if (state.executionState === 'hitl_pending' && state.pendingHitl) {
      const hitlId = state.pendingHitl.id;
      dispatch({ type: 'UI/HITL_ANSWER', hitlId, answer: text });
      ws.sendHitlResume(text);
      return;
    }
    if (state.executionState === 'paused') {
      dispatch({ type: 'UI/USER_RESUME', content: text });
      ws.sendResume(text);
      return;
    }
    if (
      state.executionState === 'thinking' ||
      state.executionState === 'executing' ||
      state.executionState === 'interrupting'
    ) {
      dispatch({ type: 'UI/USER_SOFT_INTERRUPT', content: text });
      ws.sendInterrupt('soft', text);
      return;
    }
    dispatch({ type: 'UI/USER_SEND_MESSAGE', content: text });
    ws.sendChat(text);
  }, [state.answeringHitlId, state.executionState, state.pendingHitl, dispatch, ws]);

  const handleHardInterrupt = useCallback(() => {
    dispatch({ type: 'UI/USER_HARD_INTERRUPT' });
    ws.sendInterrupt('hard');
  }, [dispatch, ws]);

  const handleHitlPrimary = useCallback((hitlId: string, value: string) => {
    let answer = value;
    if (value === 'approve') answer = '确认';
    else if (value === 'reject') answer = '不对，重新来';
    else if (value === 'skip' || value === 'cancel') answer = '取消';
    dispatch({ type: 'UI/HITL_ANSWER', hitlId, answer });
    ws.sendHitlResume(answer);
  }, [dispatch, ws]);

  const handleHitlEnterAnswering = useCallback((hitlId: string) => {
    dispatch({ type: 'UI/HITL_ENTER_ANSWERING', hitlId });
  }, [dispatch]);

  const handleHitlExitAnswering = useCallback(() => {
    if (state.answeringHitlId) {
      dispatch({ type: 'UI/HITL_EXIT_ANSWERING', hitlId: state.answeringHitlId });
    }
  }, [state.answeringHitlId, dispatch]);

  // ── 顶部圆点点击跳转到对应阶段消息 ──

  const handleJumpToPhase = useCallback((phaseId: MetaPhaseId) => {
    const root = chatScrollRef.current;
    if (!root) return;
    const target = root.querySelector(`[data-meta-phase="${phaseId}"]`);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // ── 跳到最后一个 HITL 卡片 ──

  const handleJumpToHitl = useCallback(() => {
    const root = chatScrollRef.current;
    if (!root) return;
    const cards = root.querySelectorAll('[data-hitl-card]');
    cards[cards.length - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  // ── 抽屉操作 ──

  const handleToggleDrawer = useCallback((d: DrawerKind) => {
    dispatch({ type: 'UI/TOGGLE_DRAWER', kind: d });
  }, [dispatch]);

  // ── 团队人数：优先用 fetch 到的完整 roster，否则降级到对话流派生 ──
  const teamCount = teamMembers.length > 0
    ? teamMembers.length
    : uniqueAgentCount(state.messages, state.thinkingAgents);

  return (
    <ChatRoomErrorBoundary>
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--bg-base)',
    }}>
      {/* 顶部：双行进度条 + 抽屉按钮 + 控制 */}
      <PhaseProgressBar
        sessionId={sessionId}
        wsConnected={state.wsConnected}
        executionState={state.executionState}
        routing={state.routing}
        phases={state.metaPhases}
        currentPhaseId={state.currentMetaPhaseId}
        workPlan={state.workPlan}
        artifactsCount={state.artifacts.length}
        teamCount={teamCount}
        openDrawers={state.openDrawers}
        workspacePath={state.workspacePath}
        collabMode={collabMode}
        onJumpToPhase={handleJumpToPhase}
        onToggleDrawer={handleToggleDrawer}
        onHardInterrupt={handleHardInterrupt}
      />

      {/* 主体：Chat（左）+ Drawer（右，可选） */}
      <div style={{
        flex: 1,
        display: 'flex',
        overflow: 'hidden',
      }}>
        {/* Chat 区域 */}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
        }}>
          <div ref={chatScrollRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <ChatStream
              messages={state.messages}
              workPlan={state.workPlan}
              artifacts={state.artifacts}
              onToggleExpand={messageId => dispatch({ type: 'UI/TOGGLE_MESSAGE_EXPANDED', messageId })}
              onToggleVerification={messageId => dispatch({ type: 'UI/TOGGLE_VERIFICATION_EXPANDED', messageId })}
              onHitlPrimaryAction={handleHitlPrimary}
              onHitlEnterAnswering={handleHitlEnterAnswering}
            />
          </div>
          <ThinkingIndicator agents={state.thinkingAgents} />
          <InputModeBanner
            executionState={state.executionState}
            isAnsweringHitl={state.answeringHitlId !== null}
            onCancelAnswering={handleHitlExitAnswering}
            onJumpToHitl={handleJumpToHitl}
          />
          <ChatInput
            ref={inputRef}
            executionState={state.executionState}
            isAnsweringHitl={state.answeringHitlId !== null}
            onSubmit={handleSubmit}
            onCancelAnswering={handleHitlExitAnswering}
            onHardInterrupt={handleHardInterrupt}
          />
        </div>

        {/* Drawer 区域 */}
        <DrawerHost
          openDrawers={state.openDrawers}
          onClose={(kind) => dispatch({ type: 'UI/TOGGLE_DRAWER', kind })}
          onCloseAll={() => dispatch({ type: 'UI/CLOSE_ALL_DRAWERS' })}
          onWidthChange={(kind, width) => dispatch({ type: 'UI/SET_DRAWER_WIDTH', kind, width })}
        >
          <Suspense fallback={<div style={{ padding: 24, color: 'var(--text-muted)' }}>加载中...</div>}>
          {state.openDrawers.some(d => d.kind === 'plan') && (
            <WorkPlanDrawer
              workPlan={state.workPlan}
              workPlanDelta={state.workPlanDelta}
            />
          )}
          {state.openDrawers.some(d => d.kind === 'artifacts') && (
            <ArtifactsDrawer artifacts={state.artifacts} sessionId={sessionId} workspacePath={state.workspacePath} />
          )}
          {state.openDrawers.some(d => d.kind === 'team') && (
            <TeamDrawer
              messages={state.messages}
              thinkingAgents={state.thinkingAgents}
              teamMembers={teamMembers}
            />
          )}
          {state.openDrawers.some(d => d.kind === 'workflow') && (
            <WorkflowDrawer
              teamId={teamId}
              nodeStatuses={
                state.workPlan
                  ? Object.entries(state.workPlan.tasks).map(([taskId, t]) => ({
                      nodeId: taskId,
                      status: (t.status === 'retrying' ? 'running' : t.status) as any,
                      output: '',
                      error: t.status === 'failed' ? '执行失败' : undefined,
                    }))
                  : []
              }
            />
          )}
          </Suspense>
        </DrawerHost>
      </div>
    </div>
    </ChatRoomErrorBoundary>
  );
}

/** 估算"团队人数" = 已发言 Agent + 当前活跃（去重） */
function uniqueAgentCount(
  messages: import('./types/state').TimelineItem[],
  thinking: import('./types/state').ThinkingAgent[],
): number {
  const names = new Set<string>();
  for (const m of messages) {
    if (m.kind === 'agent_message') names.add(m.agentName);
  }
  for (const t of thinking) {
    if (t.agentId !== '__placeholder__') names.add(t.agentName);
  }
  return names.size;
}
