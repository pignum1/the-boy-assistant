/** 协作完成总结卡 */
import type { SystemSummaryItem } from '../../types/state';

interface Props {
  item: SystemSummaryItem;
}

export function SystemSummaryCard({ item }: Props) {
  return (
    <div style={{
      margin: '14px 0',
      padding: '12px 14px',
      background: 'var(--green-bg)',
      border: '1px solid var(--green-border)',
      borderRadius: 8,
      textAlign: 'center',
    }}>
      <div style={{
        fontSize: 13,
        fontWeight: 600,
        color: 'var(--green-400)',
        marginBottom: 6,
      }}>
        🎉 协作流程完成
      </div>
      <div style={{
        fontSize: 12,
        color: 'var(--text-primary)',
        lineHeight: 1.6,
        marginBottom: 8,
      }}>
        {item.summary}
      </div>
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: 14,
        fontSize: 11,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}>
        <span>⏱ {formatDuration(item.totalDurationMs)}</span>
        <span>📋 {item.totalTasks} 任务</span>
        <span>📎 {item.totalArtifacts} 产物</span>
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.floor(ms / 60000)}分 ${Math.round((ms % 60000) / 1000)}秒`;
}
