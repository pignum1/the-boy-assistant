/** 系统分隔线：── ⚠️ 你介入了 ── 等里程碑 */
import type { SystemDividerItem } from '../../types/state';

interface Props {
  item: SystemDividerItem;
}

const COLOR_BY_REASON: Record<SystemDividerItem['reason'], { line: string; text: string }> = {
  interrupt:     { line: 'var(--gold-border)', text: 'var(--gold-400)' },
  m6_start:      { line: 'var(--cyan-border)', text: 'var(--cyan-400)' },
  m6_done:       { line: 'var(--green-border)', text: 'var(--green-400)' },
  delta_applied: { line: 'var(--green-border)', text: 'var(--green-400)' },
  paused:        { line: 'var(--gold-border)', text: 'var(--gold-400)' },
  resumed:       { line: 'var(--blue-border)', text: 'var(--blue-400)' },
};

export function SystemDivider({ item }: Props) {
  const c = COLOR_BY_REASON[item.reason];
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      margin: '14px 0 10px',
      color: c.text,
      fontSize: 11,
      fontFamily: 'var(--font-mono)',
    }}>
      <span style={{ flex: 1, height: 1, background: c.line }} />
      <span style={{ flexShrink: 0 }}>{item.text}</span>
      <span style={{ flex: 1, height: 1, background: c.line }} />
    </div>
  );
}
