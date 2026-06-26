/** 顶部双行进度条 = MetaPhaseRow + WorkPlanRow + 右侧抽屉按钮
 *
 * 布局：
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │ 系统  ●──●──●──○──○──○──○   M0 M1 ...      🟢sid · 空闲    │
 *   │ 任务  ████░░░░░░ 4/30 · 1/7                  📋 📁 👥        │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * 注意：在多 Agent 路径下 MetaPhaseRow 才有意义。
 * 单 Agent 路径或还没开始路由时，会显示骨架/隐藏。
 */
import type { CSSProperties } from 'react';
import type {
  MetaPhaseId,
  MetaPhaseState,
  WorkPlan,
  ExecutionState,
  DrawerKind,
  RoutingMode,
} from '../../types/state';
import { MetaPhaseRow } from './MetaPhaseRow';
import { WorkPlanRow } from './WorkPlanRow';
import { DrawerToggleButtons } from './DrawerToggleButtons';
import { ExecutionControlBar } from '../input/ExecutionControlBar';

interface Props {
  sessionId: string;
  wsConnected: boolean;
  executionState: ExecutionState;
  routing: RoutingMode;
  phases: MetaPhaseState[];
  currentPhaseId: MetaPhaseId | null;
  workPlan: WorkPlan | null;
  artifactsCount: number;
  teamCount: number;
  openDrawers: import('../../types/state').DrawerState[];
  workspacePath?: string;
  /** PR-D：当前团队协作模式，用于切换视图 */
  collabMode?: 'swarm' | 'supervisor' | 'langgraph';
  onJumpToPhase: (phaseId: MetaPhaseId) => void;
  onToggleDrawer: (drawer: DrawerKind) => void;
  onHardInterrupt: () => void;
}

const MODE_BADGE: Record<string, { icon: string; label: string; color: string; bg: string; border: string }> = {
  swarm:      { icon: '💬', label: '群聊式',   color: 'var(--cyan-400)',   bg: 'var(--cyan-bg)',   border: 'var(--cyan-border)' },
  supervisor: { icon: '👑', label: '主管式',   color: 'var(--gold-400)',   bg: 'var(--gold-bg)',   border: 'var(--gold-border)' },
  langgraph:  { icon: '🔀', label: '图编排',   color: 'var(--purple-400)', bg: 'var(--purple-bg)', border: 'var(--purple-border)' },
};

export function PhaseProgressBar({
  sessionId, wsConnected, executionState, routing,
  phases, currentPhaseId, workPlan,
  artifactsCount, teamCount, openDrawers,
  workspacePath,
  collabMode = 'supervisor',
  onJumpToPhase, onToggleDrawer, onHardInterrupt,
}: Props) {
  // supervisor 才显示 M-stage 行；暂时隐藏，聚焦任务分解
  const showMetaRow = false; // routing === 'multi_agent' && collabMode === 'supervisor';
  const modeBadge = MODE_BADGE[collabMode] || MODE_BADGE.supervisor;

  return (
    <div style={{
      padding: '8px 14px',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--bg-card)',
    }}>
      {/* 顶行：session status + drawer buttons */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        marginBottom: showMetaRow || workPlan ? 6 : 0,
      }}>
        <span style={smallText}>
          {wsConnected ? '🟢' : '⚪'} {sessionId.slice(0, 8)}
        </span>
        <span style={dimSep}>·</span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          fontSize: 11, fontFamily: 'var(--font-mono)',
          padding: '2px 8px', borderRadius: 4,
          background: modeBadge.bg, color: modeBadge.color, border: `1px solid ${modeBadge.border}`,
        }}>
          {modeBadge.icon} {modeBadge.label}
        </span>
        <span style={dimSep}>·</span>
        <span style={smallText}>{executionStateLabel(executionState)}</span>
        <div style={{ flex: 1 }} />
        <ExecutionControlBar
          executionState={executionState}
          onHardInterrupt={onHardInterrupt}
        />
        <DrawerToggleButtons
          openDrawers={openDrawers}
          onToggle={onToggleDrawer}
          taskCount={workPlan ? { done: workPlan.doneTasks, total: workPlan.totalTasks } : undefined}
          artifactCount={artifactsCount}
          teamCount={teamCount}
          workspacePath={workspacePath}
        />
      </div>

      {/* Row 1 · 系统阶段（仅多 Agent） */}
      {showMetaRow && (
        <MetaPhaseRow
          phases={phases}
          currentPhaseId={currentPhaseId}
          onJumpToPhase={onJumpToPhase}
        />
      )}

      {/* Row 2 · 业务任务（有 workPlan 才显示） */}
      {workPlan && (
        <WorkPlanRow
          workPlan={workPlan}
          onOpenDrawer={() => onToggleDrawer('plan')}
        />
      )}
    </div>
  );
}

function executionStateLabel(s: ExecutionState): string {
  switch (s) {
    case 'idle': return '空闲';
    case 'thinking': return '思考中';
    case 'executing': return '执行中';
    case 'hitl_pending': return '等回复';
    case 'paused': return '已暂停';
    case 'interrupting': return '处理介入';
    default: return s;
  }
}

const smallText: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-mono)',
};

const dimSep: CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: 11,
};
