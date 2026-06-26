interface TaskStatusBarProps {
  taskStatus: string;
  connected: boolean;
  messageCount: number;
}

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  pending: { bg: 'rgba(148,163,184,0.08)', color: 'var(--text-muted)' },
  running: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  completed: { bg: 'var(--green-bg)', color: 'var(--green-400)' },
  failed: { bg: 'var(--red-bg)', color: 'var(--red-400)' },
  paused: { bg: 'var(--gold-bg)', color: 'var(--gold-400)' },
};

export function TaskStatusBar({ taskStatus, connected, messageCount }: TaskStatusBarProps) {
  const s = STATUS_COLORS[taskStatus] || STATUS_COLORS.pending;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '8px 20px',
        borderTop: '1px solid var(--border-subtle)',
        background: 'var(--bg-base)',
        fontSize: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: connected ? 'var(--green-400)' : 'var(--red-400)',
          }}
        />
        <span style={{ color: 'var(--text-muted)' }}>{connected ? '已连接' : '已断开'}</span>
      </div>

      <div style={{ width: 1, height: 14, background: 'var(--border-subtle)' }} />

      <span style={{ padding: '2px 10px', borderRadius: 10, background: s.bg, color: s.color, fontSize: 10, fontWeight: 600 }}>
        {taskStatus.toUpperCase()}
      </span>

      <div style={{ width: 1, height: 14, background: 'var(--border-subtle)' }} />

      <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{messageCount} 消息</span>
    </div>
  );
}
