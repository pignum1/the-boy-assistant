/** AgentDetailPanel — 右侧详情面板，展示选中 Agent 的完整信息

包含：角色、任务、实时思考、工具调用、产出物、委托记录
*/
import type { DelegationNode } from '../../shared/types/session';

interface AgentDetailPanelProps {
  node: DelegationNode;
  onClose: () => void;
}

const ROLE_MAP: Record<string, { label: string; color: string }> = {
  supervisor:      { label: '主管',     color: '#f59e0b' },
  sub_supervisor:  { label: '子主管',   color: '#8b5cf6' },
  executor:        { label: '执行者',   color: '#64748b' },
};

const MODE_LABEL_MAP: Record<string, { label: string; icon: string; color: string }> = {
  single_pass:        { label: '单次',       icon: '⚡', color: '#64748b' },
  chain_of_thought:   { label: '思维链',     icon: '🔗', color: '#8b5cf6' },
  plan_execute:       { label: '规划-执行',   icon: '📋', color: '#3b82f6' },
  rewoo:              { label: 'ReWOO',      icon: '📦', color: '#10b981' },
  react:              { label: 'ReAct',      icon: '🔄', color: '#f59e0b' },
  reflexion:          { label: 'Reflexion',  icon: '🪞', color: '#ec4899' },
  self_consistency:   { label: '自一致性',    icon: '🗳️', color: '#06b6d4' },
};

const STATUS_MAP: Record<string, { label: string; icon: string; color: string }> = {
  idle:      { label: '空闲',   icon: '⚪', color: '#475569' },
  analyzing: { label: '分析中', icon: '🔄', color: '#f59e0b' },
  working:   { label: '工作中', icon: '🔄', color: '#3b82f6' },
  waiting:   { label: '等待中', icon: '⏳', color: '#64748b' },
  done:      { label: '已完成', icon: '✅', color: '#10b981' },
};

export function AgentDetailPanel({ node, onClose }: AgentDetailPanelProps) {
  const role = ROLE_MAP[node.role] || ROLE_MAP.executor;
  const status = STATUS_MAP[node.status] || STATUS_MAP.idle;

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <span style={{ fontSize: 20 }}>{node.agentEmoji}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: node.color, flex: 1 }}>
          {node.agentName}
        </span>
        <button onClick={onClose} style={closeBtnStyle}>✕</button>
      </div>

      {/* Role + Status */}
      <div style={metaRowStyle}>
        <span style={badgeStyle(role.color)}>{role.label}</span>
        <span style={badgeStyle(status.color)}>{status.icon} {status.label}</span>
      </div>

      {/* Task */}
      <div style={sectionStyle}>
        <div style={sectionTitleStyle}>📋 任务</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
          {node.task || '未分配'}
        </div>
      </div>

      {/* Real-time thinking */}
      {node.thinking && (
        <div style={sectionStyle}>
          <div style={sectionTitleStyle}>🧠 实时思考</div>
          <div style={thinkingMetaStyle}>
            {node.thinking.model && <span>🧠 {node.thinking.model}</span>}
            {node.thinking.elapsed > 0 && <span>⏱️ {node.thinking.elapsed}s</span>}
            {node.thinking.execMode && MODE_LABEL_MAP[node.thinking.execMode] && (
              <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: `${MODE_LABEL_MAP[node.thinking.execMode].color}22`, color: MODE_LABEL_MAP[node.thinking.execMode].color, border: `1px solid ${MODE_LABEL_MAP[node.thinking.execMode].color}44` }}>
                {MODE_LABEL_MAP[node.thinking.execMode].icon} {MODE_LABEL_MAP[node.thinking.execMode].label}
              </span>
            )}
            {node.thinking.iterations != null && node.thinking.iterations > 1 && (
              <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>🔄 {node.thinking.iterations}次调用</span>
            )}
          </div>
          <div style={thinkingBodyStyle}>
            {node.thinking.summary}
          </div>

          {/* Tool calls */}
          {node.thinking.toolCalls.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, marginBottom: 4 }}>🔧 工具调用</div>
              {node.thinking.toolCalls.map((tc, i) => (
                <div key={i} style={toolCallStyle(tc.status)}>
                  {tc.status === 'done' ? '✅' : tc.status === 'running' ? '🔄' : '❌'} {tc.tool}
                  {tc.detail && <span style={{ color: 'var(--text-dim)', marginLeft: 6 }}>{tc.detail}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Outputs */}
      {node.outputs.length > 0 && (
        <div style={sectionStyle}>
          <div style={sectionTitleStyle}>📄 产出物</div>
          {node.outputs.map((o, i) => (
            <div key={i} style={outputItemStyle}>
              <span>{o.type === 'file' ? '📄' : '📝'} {o.name}</span>
              <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{o.size}</span>
            </div>
          ))}
        </div>
      )}

      {/* Duration */}
      {node.duration != null && (
        <div style={sectionStyle}>
          <div style={sectionTitleStyle}>⏱️ 耗时</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {node.duration}s
          </div>
        </div>
      )}
    </div>
  );
}

// ── Styles ──

const panelStyle: React.CSSProperties = {
  width: 280,
  minWidth: 280,
  borderLeft: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: 0,
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '12px 14px',
  borderBottom: '1px solid var(--border)',
};

const closeBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-dim)',
  cursor: 'pointer',
  fontSize: 14,
  padding: '2px 6px',
  borderRadius: 4,
};

const metaRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 6,
  padding: '8px 14px',
  borderBottom: '1px solid var(--border)',
};

const badgeStyle = (color: string): React.CSSProperties => ({
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 4,
  background: `${color}22`,
  color,
  border: `1px solid ${color}44`,
});

const sectionStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderBottom: '1px solid var(--border)',
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-dim)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 6,
};

const thinkingMetaStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  fontSize: 10,
  color: 'var(--text-dim)',
  marginBottom: 6,
};

const thinkingBodyStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  lineHeight: 1.6,
  background: 'rgba(0,0,0,0.2)',
  padding: 8,
  borderRadius: 6,
  whiteSpace: 'pre-wrap' as const,
};

const toolCallStyle = (s: string): React.CSSProperties => ({
  fontSize: 10,
  padding: '3px 0',
  color: s === 'done' ? '#10b981' : s === 'running' ? '#3b82f6' : '#ef4444',
});

const outputItemStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontSize: 11,
  color: 'var(--text-secondary)',
  padding: '4px 0',
};
