/** M7 验证卡：✓ 通过 / ⚠️ 不通过 + 反馈展开 */
import type { VerificationItem } from '../../types/state';

interface Props {
  item: VerificationItem;
  onToggleExpand: (messageId: string) => void;
}

export function VerificationCard({ item, onToggleExpand }: Props) {
  const passed = item.passed;
  const color = passed ? 'var(--green-400)' : 'var(--red-400)';
  const bg = passed ? 'var(--green-bg)' : 'var(--red-bg)';
  const border = passed ? 'var(--green-border)' : 'var(--red-border)';
  return (
    <div style={{
      margin: '10px 0',
      padding: '10px 12px',
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 8,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 6,
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>
          🔍 验证员 {passed ? '✓ 通过' : '⚠️ 不通过'}
        </span>
        {item.severity !== 'none' && (
          <span style={{
            fontSize: 10,
            padding: '1px 6px',
            borderRadius: 3,
            color,
            border: `1px solid ${color}33`,
            fontFamily: 'var(--font-mono)',
          }}>
            {item.severity}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          onClick={() => onToggleExpand(item.id)}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            fontSize: 11,
            padding: '2px 6px',
          }}
        >
          {item.expanded ? '▾' : '▸'}
        </button>
      </div>
      <div style={{
        fontSize: 12,
        color: 'var(--text-primary)',
        lineHeight: 1.6,
      }}>
        {item.feedback}
      </div>
      {item.expanded && item.suggestions.length > 0 && (
        <ul style={{
          marginTop: 8,
          paddingLeft: 18,
          fontSize: 11,
          color: 'var(--text-secondary)',
          lineHeight: 1.8,
        }}>
          {item.suggestions.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
