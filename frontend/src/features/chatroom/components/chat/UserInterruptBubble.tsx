/** 用户介入气泡：橙边框，表明此条是软/硬介入 */
import type { UserInterruptItem } from '../../types/state';

interface Props {
  item: UserInterruptItem;
}

export function UserInterruptBubble({ item }: Props) {
  const label = item.mode === 'hard' ? '⏹ 硬中断' : '⚠️ 软介入';
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '8px 0' }}>
      <div style={{ maxWidth: '70%' }}>
        <div style={{
          textAlign: 'right',
          fontSize: 10,
          color: 'var(--gold-400)',
          marginBottom: 4,
          fontFamily: 'var(--font-mono)',
        }}>
          {label}
        </div>
        <div style={{
          padding: '8px 14px',
          background: 'var(--gold-bg)',
          color: 'var(--text-primary)',
          border: '1px solid var(--gold-border)',
          borderRadius: 8,
          fontSize: 13,
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {item.content || '（无附带说明）'}
        </div>
      </div>
    </div>
  );
}
