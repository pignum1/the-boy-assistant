import { Handle, Position, type NodeProps } from '@xyflow/react';

export function ConditionNode({ data, selected }: NodeProps) {
  const d = data as Record<string, unknown>;
  const label = (d.label as string) || 'Condition';

  return (
    <div
      style={{
        width: 100,
        height: 70,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
      }}
    >
      {/* 菱形背景 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'var(--bg-card)',
          border: `1.5px solid ${selected ? 'var(--amber-400)' : 'rgba(249,115,22,0.4)'}`,
          transform: 'rotate(45deg)',
          borderRadius: 6,
          boxShadow: selected ? '0 0 16px rgba(249,115,22,0.2)' : 'none',
          transition: 'all 0.15s',
        }}
      />
      {/* 文字层（不旋转） */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          textAlign: 'center',
          fontFamily: 'var(--font-body)',
        }}
      >
        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--amber-400)' }}>{label}</div>
        {d.expression && (
          <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
            {String(d.expression)}
          </div>
        )}
      </div>
      <Handle type="target" position={Position.Top} style={{ background: 'var(--text-dim)', width: 7, height: 7 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'var(--text-dim)', width: 7, height: 7 }} />
      <Handle type="source" position={Position.Right} id="right" style={{ background: 'var(--text-dim)', width: 7, height: 7, top: '50%' }} />
      <Handle type="source" position={Position.Left} id="left" style={{ background: 'var(--text-dim)', width: 7, height: 7, top: '50%' }} />
    </div>
  );
}
