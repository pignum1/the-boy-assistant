import { Handle, Position, type NodeProps } from '@xyflow/react';

export function RouterNode({ data, selected }: NodeProps) {
  const d = data as Record<string, unknown>;
  const label = (d.label as string) || 'Router';

  return (
    <div
      style={{
        padding: '12px 18px',
        borderRadius: 10,
        background: 'var(--bg-card)',
        border: `1.5px solid ${selected ? 'var(--purple-400)' : 'rgba(168,85,247,0.3)'}`,
        minWidth: 160,
        boxShadow: selected
          ? '0 0 0 1.5px var(--purple-400), 0 4px 16px rgba(0,0,0,0.12)'
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
          background: 'rgba(168,85,247,0.12)', fontSize: 15, flexShrink: 0,
          border: '1px solid rgba(168,85,247,0.3)',
        }}>
          🔀
        </div>
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12, lineHeight: '16px' }}>{label}</div>
          <div style={{ fontSize: 10, color: 'var(--purple-400)', marginTop: 2, fontWeight: 500, lineHeight: '14px' }}>
            LLM 路由
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
      <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
    </div>
  );
}

const handleStyle: React.CSSProperties = {
  background: 'rgba(168,85,247,0.35)',
  width: 7,
  height: 7,
  border: '2px solid var(--bg-card)',
};
