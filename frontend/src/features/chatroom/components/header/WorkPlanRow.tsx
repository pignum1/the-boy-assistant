/** Work plan row · 业务任务进度条
 *
 * M1 phases_plan 出来后才显示。展示百分比 + 任务数 + 阶段数。
 * 点击整行 → 打开业务任务抽屉。
 */
import type { CSSProperties } from 'react';
import type { WorkPlan } from '../../types/state';

interface Props {
  workPlan: WorkPlan | null;
  onOpenDrawer: () => void;
}

export function WorkPlanRow({ workPlan, onOpenDrawer }: Props) {
  if (!workPlan) return null;

  const total = workPlan.totalTasks;
  const done = workPlan.doneTasks;
  const percent = total > 0 ? Math.floor((done / total) * 100) : 0;
  const totalPhases = workPlan.phases.length;
  const donePhases = workPlan.phases.filter(p => p.status === 'done').length;

  return (
    <button
      onClick={onOpenDrawer}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '4px 0',
        background: 'transparent',
        border: 'none',
        width: '100%',
        cursor: 'pointer',
        textAlign: 'left',
      }}
      title="点击查看业务任务详情"
    >
      <span style={labelStyle}>任务</span>
      <div style={barTrackStyle}>
        <div style={{
          width: `${percent}%`,
          height: '100%',
          background: total > 0 && done === total
            ? 'var(--green-400)'
            : 'var(--cyan-400)',
          borderRadius: 2,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <span style={statText}>
        {total > 0 ? (
          <>
            <span style={{ color: 'var(--cyan-400)' }}>{done}</span>
            <span style={{ color: 'var(--text-muted)' }}>/{total} 任务</span>
            <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>·</span>
            <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>{donePhases}/{totalPhases} 阶段</span>
          </>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>{totalPhases} 阶段待分解</span>
        )}
      </span>
    </button>
  );
}

const labelStyle: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-muted)',
  fontFamily: 'var(--font-mono)',
  minWidth: 30,
};

const barTrackStyle: CSSProperties = {
  flex: 1,
  height: 6,
  background: 'rgba(148,163,184,0.08)',
  borderRadius: 2,
  overflow: 'hidden',
};

const statText: CSSProperties = {
  fontSize: 10,
  fontFamily: 'var(--font-mono)',
  whiteSpace: 'nowrap',
  minWidth: 100,
  textAlign: 'right',
};
