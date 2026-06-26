/** CompletionSummary — 所有 Agent 完成后的汇总面板

显示：参与 Agent 数、委托层级数、总耗时、产出物列表
*/
import type { DelegationNode } from '../../shared/types/session';

interface CompletionSummaryProps {
  nodes: Record<string, DelegationNode>;
  rootId: string | null;
  completionSummary?: string;
}

/** 计算委托树最大深度 */
function getMaxDepth(nodes: Record<string, DelegationNode>, rootId: string | null): number {
  if (!rootId || !nodes[rootId]) return 0;
  const node = nodes[rootId];
  if (node.childIds.length === 0) return 1;
  return 1 + Math.max(...node.childIds.map(cid => getMaxDepth(nodes, cid)));
}

/** 计算总耗时（所有 node duration 之和） */
function getTotalDuration(nodes: Record<string, DelegationNode>): number {
  return Object.values(nodes).reduce((sum, n) => sum + (n.duration || 0), 0);
}

/** 格式化耗时 */
function fmtDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}m ${sec}s`;
}

export function CompletionSummary({ nodes, rootId, completionSummary }: CompletionSummaryProps) {
  const nodeList = Object.values(nodes);
  const activeNodes = nodeList.filter(n => n.status !== 'idle');
  const allOutputs = activeNodes.flatMap(n => n.outputs);
  const maxDepth = getMaxDepth(nodes, rootId);
  const totalDuration = getTotalDuration(nodes);

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>✅ 协作完成</div>

      <div style={statsRowStyle}>
        <span style={statStyle}>
          <span style={statNumStyle}>{activeNodes.length}</span>
          <span style={statLabelStyle}>Agent 参与</span>
        </span>
        <span style={statStyle}>
          <span style={statNumStyle}>{maxDepth}</span>
          <span style={statLabelStyle}>层委托</span>
        </span>
        <span style={statStyle}>
          <span style={statNumStyle}>{fmtDuration(totalDuration)}</span>
          <span style={statLabelStyle}>总耗时</span>
        </span>
      </div>

      {allOutputs.length > 0 && (
        <div style={outputsStyle}>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, marginBottom: 6 }}>
            📄 {allOutputs.length} 个产出物
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {allOutputs.map((o, i) => (
              <span key={i} style={outputTagStyle}>
                {o.type === 'file' ? '📄' : '📝'} {o.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {completionSummary && (
        <div style={summaryStyle}>
          {completionSummary}
        </div>
      )}
    </div>
  );
}

// ── Styles ──

const containerStyle: React.CSSProperties = {
  background: 'rgba(16, 185, 129, 0.06)',
  border: '1px solid rgba(16, 185, 129, 0.2)',
  borderRadius: 10,
  padding: 16,
  margin: '12px 0',
};

const headerStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: '#10b981',
  marginBottom: 10,
};

const statsRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 16,
  marginBottom: 12,
};

const statStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const statNumStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: 'var(--text-primary)',
};

const statLabelStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
};

const outputsStyle: React.CSSProperties = {
  borderTop: '1px solid rgba(148,163,184,0.1)',
  paddingTop: 10,
};

const outputTagStyle: React.CSSProperties = {
  fontSize: 10,
  padding: '3px 8px',
  borderRadius: 4,
  background: 'rgba(16,185,129,0.1)',
  color: '#10b981',
  border: '1px solid rgba(16,185,129,0.2)',
};

const summaryStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  lineHeight: 1.6,
  marginTop: 10,
  paddingTop: 10,
  borderTop: '1px solid rgba(148,163,184,0.1)',
};
