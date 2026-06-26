/** AgentNode — xyflow 自定义节点，展示单个 Agent 的实时状态

4 种状态视觉：
- 🔄 工作中：亮色边框 + 脉冲呼吸动画
- ⏳ 等待中：半透明 + 灰色
- ✅ 已完成：绿色边框 + 产出物缩略
- ⚪ 空闲/未参与：最小化
*/
import { memo, useState } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { AgentNodeData, DelegationNode, DelegationStatus } from '../../shared/types/session';

// ── 状态配置 ──

const STATUS_CONFIG: Record<DelegationStatus, {
  border: string; bg: string; label: string; icon: string; opacity: number;
}> = {
  idle:       { border: '#334155', bg: '#0f172a', label: '空闲',     icon: '⚪', opacity: 0.5 },
  analyzing:  { border: '#f59e0b', bg: '#1a1500', label: '分析中',   icon: '🔄', opacity: 1 },
  working:    { border: '#3b82f6', bg: '#0a1628', label: '工作中',   icon: '🔄', opacity: 1 },
  waiting:    { border: '#64748b', bg: '#0f172a', label: '等待中',   icon: '⏳', opacity: 0.7 },
  done:       { border: '#10b981', bg: '#051a12', label: '已完成',   icon: '✅', opacity: 1 },
};

const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  supervisor:      { label: '主管',   color: '#f59e0b' },
  sub_supervisor:  { label: '子主管', color: '#8b5cf6' },
  executor:        { label: '执行者', color: '#64748b' },
};

// ── 组件 ──

function AgentNodeRaw({ data }: NodeProps & { data: AgentNodeData }) {
  const { node, isSelected, onSelect } = data;
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const config = STATUS_CONFIG[node.status];

  const isActive = node.status === 'working' || node.status === 'analyzing';

  return (
    <>
      {/* 顶部 Handle（接收父节点连线） */}
      <Handle type="target" position={Position.Top} style={{ visibility: node.parentId ? 'visible' : 'hidden', background: config.border, width: 8, height: 8 }} />

      <div
        onClick={() => onSelect(node.id)}
        style={{
          ...containerStyle(config.border, config.bg, config.opacity, isSelected, isActive),
          cursor: 'pointer',
          minWidth: node.status === 'idle' ? 160 : 220,
          maxWidth: 300,
        }}
      >
        {/* 顶部：Agent 名 + 角色标签 */}
        <div style={headerStyle}>
          <span style={{ fontSize: 16 }}>{node.agentEmoji}</span>
          <span style={{ fontSize: 12, fontWeight: 600, color: node.color, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {node.agentName}
          </span>
          <span style={roleBadgeStyle(ROLE_BADGE[node.role]?.color || '#64748b')}>
            {ROLE_BADGE[node.role]?.label || ''}
          </span>
        </div>

        {/* 空闲状态：只显示名字 */}
        {node.status === 'idle' && (
          <div style={{ fontSize: 10, color: 'var(--text-dim)', padding: '4px 10px' }}>
            未参与本次协作
          </div>
        )}

        {/* 非空闲：显示状态+任务+思考 */}
        {node.status !== 'idle' && (
          <>
            {/* 状态行 */}
            <div style={statusLineStyle}>
              <span style={{ fontSize: 11 }}>
                {config.icon} {config.label}
              </span>
              {node.thinking?.model && (
                <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 8 }}>
                  🧠 {node.thinking.model}
                </span>
              )}
              {node.thinking?.elapsed != null && node.thinking.elapsed > 0 && (
                <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 8 }}>
                  ⏱️ {node.thinking.elapsed}s
                </span>
              )}
            </div>

            {/* 任务描述 */}
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', padding: '2px 10px', lineHeight: 1.4 }}>
              📋 {node.task}
            </div>

            {/* 思考摘要（仅工作中显示，可点击展开） */}
            {node.thinking && node.thinking.summary && isActive && (
              <div
                onClick={(e) => { e.stopPropagation(); setThinkingOpen(!thinkingOpen); }}
                style={thinkingFoldStyle}
              >
                <span style={{ fontSize: 9, transform: thinkingOpen ? 'rotate(90deg)' : 'rotate(0)', display: 'inline-block', transition: 'transform 0.2s' }}>▶</span>
                <span style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600 }}> 思考过程</span>
                {!thinkingOpen && (
                  <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140, display: 'inline-block', verticalAlign: 'middle' }}>
                    {node.thinking.summary.slice(0, 40)}...
                  </span>
                )}
              </div>
            )}
            {thinkingOpen && node.thinking && (
              <div style={thinkingBodyStyle}>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                  {node.thinking.summary}
                </div>
                {node.thinking.toolCalls.map((tc, i) => (
                  <div key={i} style={{ fontSize: 9, color: tc.status === 'done' ? 'var(--green-400)' : 'var(--text-dim)', marginTop: 3 }}>
                    🔧 {tc.tool} {tc.status === 'done' ? '✅' : tc.status === 'running' ? '🔄' : '❌'}
                  </div>
                ))}
              </div>
            )}

            {/* 产出物 */}
            {node.outputs.length > 0 && (
              <div style={{ padding: '4px 10px', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {node.outputs.map((o, i) => (
                  <span key={i} style={outputTagStyle}>
                    📄 {o.name}
                  </span>
                ))}
              </div>
            )}

            {/* 耗时 */}
            {node.status === 'done' && node.duration != null && (
              <div style={{ fontSize: 9, color: 'var(--text-dim)', padding: '2px 10px 4px' }}>
                ⏱️ {node.duration}s
              </div>
            )}
          </>
        )}
      </div>

      {/* 底部 Handle（发送子节点连线） */}
      <Handle type="source" position={Position.Bottom} style={{ visibility: node.childIds.length > 0 || node.status === 'analyzing' ? 'visible' : 'hidden', background: config.border, width: 8, height: 8 }} />
    </>
  );
}

export const AgentNode = memo(AgentNodeRaw);

// ── 样式 ──

const containerStyle = (border: string, bg: string, opacity: number, selected: boolean, active: boolean): React.CSSProperties => ({
  borderRadius: 10,
  border: `2px solid ${selected ? '#f59e0b' : border}`,
  background: bg,
  opacity,
  overflow: 'hidden',
  transition: 'all 0.3s ease',
  animation: active ? 'pulse 2s ease-in-out infinite' : 'none',
  boxShadow: selected ? `0 0 12px ${border}44` : 'none',
});

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 10px 4px',
};

const roleBadgeStyle = (color: string): React.CSSProperties => ({
  fontSize: 9,
  fontWeight: 600,
  padding: '1px 6px',
  borderRadius: 4,
  background: `${color}22`,
  color,
  border: `1px solid ${color}44`,
  flexShrink: 0,
});

const statusLineStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  padding: '4px 10px 2px',
  color: 'var(--text-secondary)',
};

const thinkingFoldStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  padding: '4px 10px',
  cursor: 'pointer',
  userSelect: 'none',
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const thinkingBodyStyle: React.CSSProperties = {
  padding: '4px 10px 6px',
  borderTop: '1px solid rgba(148,163,184,0.06)',
  background: 'rgba(0,0,0,0.2)',
};

const outputTagStyle: React.CSSProperties = {
  fontSize: 9,
  padding: '1px 6px',
  borderRadius: 4,
  background: 'rgba(16,185,129,0.1)',
  color: 'var(--green-400)',
  border: '1px solid rgba(16,185,129,0.2)',
};
