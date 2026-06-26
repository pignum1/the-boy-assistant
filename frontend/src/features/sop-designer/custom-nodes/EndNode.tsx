import { Handle, Position, type NodeProps } from '@xyflow/react';

export function EndNode({ selected }: NodeProps) {
  return (
    <div
      style={{
        padding: '7px 22px',
        borderRadius: 20,
        background: 'linear-gradient(135deg, #ef4444, #dc2626)',
        color: '#fff',
        fontWeight: 700,
        fontSize: 12,
        boxShadow: selected
          ? '0 0 0 2px rgba(239,68,68,0.4), 0 4px 12px rgba(239,68,68,0.2)'
          : '0 1px 3px rgba(239,68,68,0.15)',
        transition: 'all 0.15s ease',
        fontFamily: 'var(--font-body)',
        letterSpacing: 0.3,
      }}
    >
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <Handle type="target" position={Position.Right} id="right" style={handleStyle} />
      <Handle type="target" position={Position.Left} id="left" style={handleStyle} />
      ■ End
    </div>
  );
}

const handleStyle: React.CSSProperties = {
  background: 'rgba(239,68,68,0.4)',
  width: 7,
  height: 7,
  border: '2px solid var(--bg-card)',
};
