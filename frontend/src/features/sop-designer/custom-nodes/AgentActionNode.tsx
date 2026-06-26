import { Handle, Position, type NodeProps } from '@xyflow/react';
import { getRoleInfo } from '../../../shared/types/sop';

export function AgentActionNode({ data, selected }: NodeProps) {
  const d = data as Record<string, unknown>;
  const label = (d.label as string) || (d.role_slot as string) || 'Agent Action';
  const role = getRoleInfo(String(d.role_slot || ''));

  return (
    <div
      style={{
        padding: '12px 18px',
        borderRadius: 10,
        background: 'var(--bg-card)',
        border: `1.5px solid ${selected ? 'var(--green-400)' : 'rgba(255,255,255,0.08)'}`,
        minWidth: 160,
        boxShadow: selected
          ? '0 0 0 1.5px var(--green-400), 0 4px 16px rgba(0,0,0,0.12)'
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
          background: `${role.color}12`, fontSize: 15, flexShrink: 0,
          border: `1px solid ${role.color}20`,
        }}>
          {role.icon}
        </div>
        <div>
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 12, lineHeight: '16px' }}>{label}</div>
          <div style={{ fontSize: 10, color: role.color, marginTop: 2, fontWeight: 500, lineHeight: '14px' }}>
            {role.label !== role.slot ? role.label : ''}
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
      <Handle type="source" position={Position.Right} id="right" style={handleStyle} />
    </div>
  );
}

const handleStyle: React.CSSProperties = {
  background: 'rgba(52,211,153,0.35)',
  width: 7,
  height: 7,
  border: '2px solid var(--bg-card)',
};
