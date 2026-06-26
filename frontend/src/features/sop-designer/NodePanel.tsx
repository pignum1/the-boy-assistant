const NODE_TYPES = [
  { type: 'start',          label: 'Start',        icon: '▶',  color: 'var(--gold-500)' },
  { type: 'agent_action',   label: 'Agent Action', icon: '🤖',  color: 'var(--green-400)' },
  { type: 'router',         label: 'Router',       icon: '🔀',  color: 'var(--purple-400)' },
  { type: 'parallel',       label: 'Parallel',     icon: '⫸',  color: 'var(--cyan-400)' },
  { type: 'hitl',           label: 'HITL 审批',    icon: '👤',  color: 'var(--gold-400)' },
  { type: 'validation',     label: 'Validation',   icon: '✅',  color: 'var(--blue-400)' },
  { type: 'condition',      label: 'Condition',    icon: '◇',  color: 'var(--amber-400)' },
  { type: 'end',            label: 'End',           icon: '■',  color: 'var(--red-400)' },
] as const;

interface NodePanelProps {
  onAddNode: (type: string) => void;
}

export function NodePanel({ onAddNode }: NodePanelProps) {
  return (
    <div
      style={{
        width: 200,
        background: 'var(--bg-base)',
        borderRight: '1px solid var(--border-subtle)',
        padding: '12px 10px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        flexShrink: 0,
        overflowY: 'auto',
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-muted)',
          textTransform: 'uppercase' as const,
          letterSpacing: 0.5,
          padding: '6px 8px',
        }}
      >
        节点类型
      </div>
      {NODE_TYPES.map(({ type, label, icon, color }) => (
        <button
          key={type}
          onClick={() => onAddNode(type)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 12px',
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 500,
            color: color,
            background: 'transparent',
            border: '1px solid transparent',
            cursor: 'pointer',
            transition: 'all 0.15s',
            fontFamily: 'var(--font-body)',
            width: '100%',
            textAlign: 'left' as const,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
            e.currentTarget.style.borderColor = 'var(--border-subtle)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.borderColor = 'transparent';
          }}
        >
          <span style={{ fontSize: 14 }}>{icon}</span>
          {label}
        </button>
      ))}
    </div>
  );
}
