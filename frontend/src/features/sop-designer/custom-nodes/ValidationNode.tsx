import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ValidationNode({ data, selected }: NodeProps) {
  const d = data as Record<string, unknown>;
  const label = (d.label as string) || 'Validation';
  const checks = d.checks as string[] | undefined;

  return (
    <div
      style={{
        padding: '12px 18px',
        borderRadius: 10,
        background: 'var(--bg-card)',
        border: `1.5px solid ${selected ? 'var(--blue-400)' : 'rgba(255,255,255,0.08)'}`,
        minWidth: 160,
        boxShadow: selected
          ? '0 0 0 1.5px var(--blue-400), 0 4px 16px rgba(0,0,0,0.12)'
          : '0 1px 3px rgba(0,0,0,0.08)',
        transition: 'all 0.15s ease',
        fontFamily: 'var(--font-body)',
      }}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <Handle type="target" position={Position.Left} id="left" style={handleStyle} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(139,92,246,0.08)', fontSize: 15, flexShrink: 0,
          border: '1px solid rgba(139,92,246,0.15)',
        }}>
          ✅
        </div>
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12, lineHeight: '16px' }}>{label}</div>
          {checks && checks.length > 0 && (
            <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 2, lineHeight: '13px' }}>
              {checks.join(', ')} ≥ {String(d.pass_threshold || 80)}%
            </div>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
      <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
    </div>
  );
}

const handleStyle: React.CSSProperties = {
  background: 'rgba(139,92,246,0.35)',
  width: 7,
  height: 7,
  border: '2px solid var(--bg-card)',
};
