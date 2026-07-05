/**
 * 业务任务抽屉：时间线卡片风格
 *
 * 每条任务 = 一张卡片：左侧 Agent 色条 + 圆点 + 头（头像/名字/耗时）+ 描述 + 进度条
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
    return <EmptyState text="等待 Supervisor 分析后生成业务任务" />;
  }

  const percent = workPlan.totalTasks > 0
    ? Math.floor((workPlan.doneTasks / workPlan.totalTasks) * 100)
    : 0;

  return (
    <div style={{ padding: '8px 6px' }}>
      {/* 介入变更条 */}
      {workPlanDelta && <DeltaSummaryBar delta={workPlanDelta} />}

      {/* 总进度 */}
      <div style={{
        padding: '4px 6px 8px',
        display: 'flex', alignItems: 'center', gap: 10,
        fontSize: 11, fontFamily: 'var(--font-mono)',
        color: 'var(--text-secondary)',
      }}>
        <span>总进度</span>
        <span style={{ flex: 1 }}>
          <span style={{ color: 'var(--cyan-400)', fontWeight: 600 }}>{workPlan.doneTasks}</span>
          <span style={{ color: 'var(--text-muted)' }}>/{workPlan.totalTasks} 任务</span>
        </span>
        <span style={{ color: 'var(--text-muted)' }}>{percent}%</span>
        <div style={progressBarTrack}>
          <div style={{
            width: `${percent}%`, height: '100%',
            background: percent === 100 ? 'var(--green-400)' : 'var(--cyan-400)',
            borderRadius: 2, transition: 'width 0.4s ease',
          }} />
        </div>
      </div>

      {/* 时间线卡片 */}
      <div style={{ position: 'relative', paddingLeft: 10 }}>
        {/* 时间线竖线 */}
        <div style={{
          position: 'absolute', left: 15, top: 6, bottom: 6, width: 2,
          background: 'var(--border-subtle)', zIndex: 0,
        }} />
        {workPlan.phases.map(phase => (
          <PhaseTimeline
            key={phase.id}
            phase={phase}
            tasks={phase.taskIds.map(id => workPlan.tasks[id]).filter(Boolean)}
          />
        ))}
      </div>
    </div>
  );
}

function PhaseTimeline({ phase, tasks }: { phase: WorkPhase; tasks: WorkTask[] }) {
  if (tasks.length === 0) return null;
  const phaseStatus = computePhaseStatus(tasks);
  const phaseColor = PHASE_COLOR[phaseStatus] || 'var(--border-subtle)';
  const doneCount = tasks.filter(t => t.status === 'done').length;

  return (
    <div style={{ marginBottom: 2 }}>
      {/* Phase header — small muted label */}
      <div style={{
        position: 'relative', zIndex: 1,
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '2px 0 4px 8px',
        fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
      }}>
        <span style={{
          position: 'absolute', left: -5, top: 10, width: 8, height: 8, borderRadius: '50%',
          background: phaseStatus === 'done' ? 'var(--green-400)' : phaseStatus === 'running' ? 'var(--cyan-400)' : 'var(--text-dim)',
          border: '2px solid var(--bg-base)', zIndex: 1,
        }} />
        <span>{phase.name}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {doneCount}/{tasks.length}
        </span>
      </div>
      {tasks.map(t => <TaskCard key={t.id} task={t} />)}
    </div>
  );
}

function TaskCard({ task }: { task: WorkTask }) {
  const icon = STATUS_ICON[task.status] ?? '⏸';
  const isRunning = task.status === 'running';
  const isDone = task.status === 'done';
  const elapsed = task.startedAt && task.endedAt
    ? `${Math.round((task.endedAt - task.startedAt) / 1000)}s`
    : task.startedAt && task.status === 'running'
      ? `${Math.round((Date.now() - task.startedAt) / 1000)}s`
      : '';
  const borderColor = isDone ? 'var(--green-400)' : isRunning ? 'var(--cyan-400)' : 'var(--border-strong)';

  return (
    <div style={{
      position: 'relative', zIndex: 1,
      marginLeft: 10, marginBottom: 6, padding: '8px 10px 8px 14px',
      borderRadius: 10, border: '1px solid var(--border-subtle)',
      borderLeft: `3px solid ${borderColor}`,
      background: isRunning ? 'rgba(6,182,212,0.04)' : 'var(--bg-soft)',
      fontSize: 11,
    }}>
      {/* 时间线圆点 */}
      <span style={{
        position: 'absolute', left: -17, top: 13, width: 10, height: 10, borderRadius: '50%',
        background: isDone ? 'var(--green-400)' : isRunning ? 'var(--cyan-400)' : 'var(--bg-base)',
        border: `2px solid ${isDone ? 'var(--green-400)' : isRunning ? 'var(--cyan-400)' : 'var(--border-strong)'}`,
        zIndex: 1,
      }} />
      {/* 头部 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11 }}>{task.agentEmoji || '🤖'}</span>
        <span style={{
          flex: 1, fontWeight: 500, color: 'var(--text-primary)', fontSize: 12,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{task.name}</span>
        <span style={{
          fontSize: 10, fontWeight: 600, fontFamily: 'var(--font-mono)',
          color: isDone ? 'var(--green-400)' : isRunning ? 'var(--cyan-400)' : 'var(--text-muted)',
          whiteSpace: 'nowrap',
        }}>
          {icon} {task.agentName}
        </span>
        {elapsed && (
          <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
            {elapsed}
          </span>
        )}
      </div>
      {/* 进度条（仅运行中） */}
      {isRunning && (
        <div style={{
          marginTop: 5, height: 3, borderRadius: 2, background: 'rgba(148,163,184,0.08)', overflow: 'hidden',
        }}>
          <div style={{
            width: '65%', height: '100%', borderRadius: 2,
            background: 'linear-gradient(90deg, var(--cyan-400), var(--green-400))',
            animation: 'chatroom-pulse 1.5s infinite',
          }} />
        </div>
      )}
    </div>
  );
}

function DeltaSummaryBar({ delta }: { delta: DeltaPlan }) {
  return (
    <div style={{
      marginBottom: 8, padding: '6px 8px', borderRadius: 6,
      background: 'var(--gold-bg)', border: '1px solid var(--gold-border)',
      fontSize: 11,
    }}>
      <div style={{ color: 'var(--gold-400)', fontWeight: 600, marginBottom: 2 }}>
        ⚠️ 介入修改：{delta.summary || '(无说明)'}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontFamily: 'var(--font-mono)' }}>
        {delta.keep.length > 0 && <span style={{ color: 'var(--green-400)' }}>✓ 保留 {delta.keep.length}</span>}
        {delta.modify.length > 0 && <span style={{ color: 'var(--gold-400)' }}>🔄 重做 {delta.modify.length}</span>}
        {delta.add.length > 0 && <span style={{ color: 'var(--cyan-400)' }}>🆕 新增 {delta.add.length}</span>}
        {delta.cancel.length > 0 && <span style={{ color: 'var(--red-400)' }}>❌ 取消 {delta.cancel.length}</span>}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div style={{
      padding: '60px 20px', textAlign: 'center',
      color: 'var(--text-muted)', fontSize: 12,
    }}>
      {text}
    </div>
  );
}

const STATUS_ICON: Record<WorkTaskStatus | 'partial', string> = {
  pending: '⏸', running: '⏳', done: '✓', failed: '⚠️',
  retrying: '🔁', modified: '🔄', new: '🆕', cancelled: '❌', partial: '◐',
};

const PHASE_COLOR: Record<string, string> = {
  done: 'var(--green-400)', running: 'var(--cyan-400)', partial: 'var(--gold-400)',
  pending: 'var(--text-dim)',
};

function computePhaseStatus(tasks: WorkTask[]): WorkPhase['status'] {
  if (tasks.length === 0) return 'pending';
  if (tasks.every(t => t.status === 'done' || t.status === 'cancelled')) return 'done';
  if (tasks.some(t => t.status === 'running')) return 'running';
  if (tasks.some(t => t.status === 'done')) return 'partial';
  return 'pending';
}

const progressBarTrack: CSSProperties = {
  width: 60, height: 5, background: 'rgba(148,163,184,0.08)',
  borderRadius: 2, overflow: 'hidden', flexShrink: 0,
};
