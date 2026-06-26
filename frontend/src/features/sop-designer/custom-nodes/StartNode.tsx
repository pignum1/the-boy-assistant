import { Handle, Position, type NodeProps } from '@xyflow/react';

export function StartNode({ selected }: NodeProps) {
  return (
    <div
      style={{
        padding: '7px 22px',
        borderRadius: 20,
        background: 'linear-gradient(135deg, #22c55e, #16a34a)',
        color: '#fff',
        fontWeight: 700,
        fontSize: 12,
        boxShadow: selected
          ? '0 0 0 2px rgba(34,197,94,0.4), 0 4px 12px rgba(34,197,94,0.2)'
          : '0 1px 3px rgba(34,197,94,0.15)',
        transition: 'all 0.15s ease',
        fontFamily: 'var(--font-body)',
        letterSpacing: 0.3,
      }}
    >
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
      <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
      <Handle type="source" position={Position.Left} id="left" style={handleStyle} />
      ▶ Start
    </div>
  );
}

const handleStyle: React.CSSProperties = {
  background: 'rgba(34,197,94,0.4)',
  width: 7,
  height: 7,
  border: '2px solid var(--bg-card)',
};
