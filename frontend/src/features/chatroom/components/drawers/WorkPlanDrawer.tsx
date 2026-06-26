/** 业务任务抽屉：DeltaSummaryBar + 总进度 + 阶段树
 *
 * 阶段是顶层，任务在阶段下缩进显示。
 * 任务状态徽章 ✓ ⏳ ⏸ ⚠️ 🔄 🆕 ❌
 */
import type { CSSProperties } from 'react';
import type {
  WorkPlan,
  WorkPhase,
  WorkTask,
  DeltaPlan,
  WorkTaskStatus,
} from '../../types/state';

interface Props {
  workPlan: WorkPlan | null;
  workPlanDelta: DeltaPlan | null;
}

export function WorkPlanDrawer({ workPlan, workPlanDelta }: Props) {
  if (!workPlan) {
    return (
      <EmptyState text="等待 Supervisor 分析后生成业务任务" />
    );
  }

  const totalPhases = workPlan.phases.length;
  const donePhases = workPlan.phases.filter(p => p.status === 'done').length;
  const percent = workPlan.totalTasks > 0
    ? Math.floor((workPlan.doneTasks / workPlan.totalTasks) * 100)
    : 0;

  return (
    <div style={{ padding: '10px 14px' }}>
      {/* DeltaSummaryBar */}
      {workPlanDelta && <DeltaSummaryBar delta={workPlanDelta} />}

      {/* 总进度 */}
      <div style={{
        padding: '8px 0',
        borderBottom: '1px solid var(--border-subtle)',
        marginBottom: 10,
      }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11,
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-mono)',
          marginBottom: 4,
        }}>
          <span>总进度</span>
          <span>
            <span style={{ color: 'var(--cyan-400)' }}>{workPlan.doneTasks}</span>
            <span style={{ color: 'var(--text-muted)' }}>/{workPlan.totalTasks} 任务 · </span>
            <span style={{ color: 'var(--text-secondary)' }}>{donePhases}/{totalPhases} 阶段</span>
          </span>
        </div>
        <div style={progressBarTrack}>
          <div style={{
            width: `${percent}%`,
            height: '100%',
            background: percent === 100 ? 'var(--green-400)' : 'var(--cyan-400)',
            borderRadius: 2,
            transition: 'width 0.4s ease',
          }} />
        </div>
      </div>

      {/* 阶段树 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {workPlan.phases.map(phase => (
          <PhaseGroup
            key={phase.id}
            phase={phase}
            tasks={phase.taskIds.map(id => workPlan.tasks[id]).filter(Boolean)}
          />
        ))}
      </div>
    </div>
  );
}

function DeltaSummaryBar({ delta }: { delta: DeltaPlan }) {
  return (
    <div style={{
      marginBottom: 10,
      padding: '8px 10px',
      background: 'var(--gold-bg)',
      border: '1px solid var(--gold-border)',
      borderRadius: 4,
      fontSize: 11,
    }}>
      <div style={{ color: 'var(--gold-400)', fontWeight: 600, marginBottom: 4 }}>
        ⚠️ 介入修改：{delta.summary || '(无说明)'}
      </div>
      <div style={{
        display: 'flex',
        gap: 10,
        flexWrap: 'wrap',
        fontFamily: 'var(--font-mono)',
      }}>
        {delta.keep.length > 0 && (
          <span style={{ color: 'var(--green-400)' }}>✓ 保留 {delta.keep.length}</span>
        )}
        {delta.modify.length > 0 && (
          <span style={{ color: 'var(--gold-400)' }}>🔄 重做 {delta.modify.length}</span>
        )}
        {delta.add.length > 0 && (
          <span style={{ color: 'var(--cyan-400)' }}>🆕 新增 {delta.add.length}</span>
        )}
        {delta.cancel.length > 0 && (
          <span style={{ color: 'var(--red-400)' }}>❌ 取消 {delta.cancel.length}</span>
        )}
      </div>
    </div>
  );
}

function PhaseGroup({ phase, tasks }: { phase: WorkPhase; tasks: WorkTask[] }) {
  const phaseStatus = computePhaseStatus(tasks);
  const phaseIcon = STATUS_ICON[phaseStatus] ?? '⏸';
  return (
    <div style={{
      borderLeft: `2px solid ${PHASE_BORDER[phaseStatus]}`,
      paddingLeft: 8,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        color: 'var(--text-primary)',
        marginBottom: 4,
      }}>
        <span>{phaseIcon}</span>
        <span>{phase.name}</span>
        {tasks.length > 0 && (
          <span style={{
            fontSize: 10,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
            marginLeft: 'auto',
          }}>
            {tasks.filter(t => t.status === 'done').length}/{tasks.length}
          </span>
        )}
      </div>
      {tasks.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingLeft: 14 }}>
          {tasks.map(t => <TaskRow key={t.id} task={t} />)}
        </div>
      )}
    </div>
  );
}

function TaskRow({ task }: { task: WorkTask }) {
  const icon = STATUS_ICON[task.status] ?? '⏸';
  const elapsed = task.startedAt && task.endedAt
    ? `${Math.round((task.endedAt - task.startedAt) / 1000)}s`
    : task.startedAt && task.status === 'running'
      ? `${Math.round((Date.now() - task.startedAt) / 1000)}s`
      : '';
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '3px 0',
      fontSize: 11,
      color: 'var(--text-secondary)',
    }}>
      <span style={{ width: 16, textAlign: 'center' }}>{icon}</span>
      <span style={{
        fontSize: 9,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        minWidth: 36,
      }}>{task.id}</span>
      <span style={{
        flex: 1,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>{task.name}</span>
      <span style={{
        fontSize: 10,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}>
        {task.agentEmoji} {task.agentName}
      </span>
      {elapsed && (
        <span style={{
          fontSize: 9,
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-mono)',
          minWidth: 30,
          textAlign: 'right',
        }}>{elapsed}</span>
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{
      padding: '60px 20px',
      textAlign: 'center',
      color: 'var(--text-muted)',
      fontSize: 12,
    }}>
      {text}
    </div>
  );
}

const STATUS_ICON: Record<WorkTaskStatus | 'partial', string> = {
  pending: '⏸',
  running: '⏳',
  done: '✓',
  failed: '⚠️',
  retrying: '🔁',
  modified: '🔄',
  new: '🆕',
  cancelled: '❌',
  partial: '◐',
};

const PHASE_BORDER: Record<WorkPhase['status'] | 'partial', string> = {
  pending: 'var(--border-subtle)',
  running: 'var(--cyan-400)',
  done: 'var(--green-400)',
  partial: 'var(--gold-400)',
};

function computePhaseStatus(tasks: WorkTask[]): WorkPhase['status'] {
  if (tasks.length === 0) return 'pending';
  if (tasks.every(t => t.status === 'done' || t.status === 'cancelled')) return 'done';
  if (tasks.some(t => t.status === 'running')) return 'running';
  if (tasks.some(t => t.status === 'done')) return 'partial';
  return 'pending';
}

const progressBarTrack: CSSProperties = {
  width: '100%',
  height: 6,
  background: 'rgba(148,163,184,0.08)',
  borderRadius: 2,
  overflow: 'hidden',
};
