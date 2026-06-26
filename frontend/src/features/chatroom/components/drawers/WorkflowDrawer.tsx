/** WorkflowDrawer — 工作流执行状态面板（Jira 风格流程列表）

显示每个节点的执行状态、Agent、耗时、错误，按流程顺序排列。
格式：垂直时间线 + 节点卡片，直观展示流程进度。
*/
import { useState, useEffect } from 'react';
import { api } from '../../../../shared/api/client';

interface WorkflowNodeData {
  id: string;
  type: string;
  label: string;
  node_key: string;
  config: Record<string, unknown>;
  position_x: number;
  position_y: number;
  agent_id?: string;
  agent_name?: string;
}

interface WorkflowEdgeData {
  id: string;
  source_id: string;
  target_id: string;
  type: string;
}

interface NodeStatus {
  nodeId: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  output?: string;
  error?: string;
}

interface Props {
  teamId: string;
  nodeStatuses: NodeStatus[];
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; icon: string }> = {
  pending:  { color: 'var(--text-dim)',    bg: 'rgba(148,163,184,0.06)', label: '待执行', icon: '○' },
  running:  { color: 'var(--blue-400)',    bg: 'rgba(59,130,246,0.08)',  label: '执行中', icon: '◉' },
  done:     { color: 'var(--green-400)',   bg: 'rgba(16,185,129,0.08)',  label: '完成',   icon: '●' },
  failed:   { color: 'var(--red-400)',     bg: 'rgba(239,68,68,0.08)',   label: '失败',   icon: '✕' },
  skipped:  { color: 'var(--gold-400)',    bg: 'rgba(245,158,11,0.08)',  label: '跳过',   icon: '⊘' },
};

const NODE_TYPE_ICONS: Record<string, string> = {
  Start:      '▶',
  End:        '⏹',
  Agent:      '🤖',
  Condition:  '◆',
  HITL:       '👤',
  Validation: '✓',
  Router:     '↗',
  Parallel:   '≣',
};

export function WorkflowDrawer({ teamId, nodeStatuses }: Props) {
  const [nodes, setNodes] = useState<WorkflowNodeData[]>([]);
  const [edges, setEdges] = useState<WorkflowEdgeData[]>([]);
  const [workflowName, setWorkflowName] = useState('');
  const [loading, setLoading] = useState(true);

  const statusMap = new Map(nodeStatuses.map(s => [s.nodeId, s]));

  useEffect(() => {
    api.get<{
      nodes: WorkflowNodeData[]; edges: WorkflowEdgeData[]; workflow_name: string;
    }>(`/api/v1/teams/${teamId}/langgraph-workflow`)
      .then(data => {
        setNodes(data.nodes || []);
        setEdges(data.edges || []);
        setWorkflowName(data.workflow_name || '');
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [teamId]);

  // Build ordered node list following the DAG flow (topological order by position_y)
  const orderedNodes = [...nodes].sort((a, b) => (a.position_y || 0) - (b.position_y || 0));
  const total = orderedNodes.length;
  const done = nodeStatuses.filter(s => s.status === 'done').length;
  const failed = nodeStatuses.filter(s => s.status === 'failed').length;

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        加载工作流...
      </div>
    );
  }

  if (orderedNodes.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        暂无工作流定义
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--surface-elevated)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            🔀 {workflowName || '工作流'}
          </span>
        </div>
        {/* Progress */}
        <div style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
            <span>{done}/{total} 节点完成</span>
            {failed > 0 && <span style={{ color: 'var(--red-400)' }}>⚠ {failed} 失败</span>}
          </div>
          <div style={{
            height: 4, borderRadius: 2, background: 'var(--border-subtle)',
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${total > 0 ? (done / total) * 100 : 0}%`,
              background: failed > 0 ? 'var(--red-400)' : 'var(--green-400)',
              borderRadius: 2,
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      </div>

      {/* Node timeline */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
        {orderedNodes.map((node, idx) => {
          const status = statusMap.get(node.id);
          const st = STATUS_CONFIG[status?.status || 'pending'];
          const typeIcon = NODE_TYPE_ICONS[node.type] || '●';
          const isLast = idx === orderedNodes.length - 1;

          return (
            <div key={node.id} style={{ position: 'relative', paddingLeft: 40 }}>
              {/* Timeline connector */}
              {!isLast && (
                <div style={{
                  position: 'absolute',
                  left: 19,
                  top: 36,
                  bottom: 0,
                  width: 2,
                  background: status?.status === 'done'
                    ? 'var(--green-400)'
                    : 'var(--border-subtle)',
                }} />
              )}

              {/* Node card */}
              <div style={{
                margin: '0 12px 2px 0',
                padding: '10px 12px',
                borderRadius: 8,
                border: `1px solid ${status?.status === 'running' ? st.color : 'var(--border-subtle)'}`,
                background: status?.status === 'running' ? st.bg : 'var(--bg-card)',
                position: 'relative',
              }}>
                {/* Status dot on timeline */}
                <div style={{
                  position: 'absolute',
                  left: -29,
                  top: 12,
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: st.bg,
                  border: `2px solid ${st.color}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  color: st.color,
                }}>
                  {status?.status === 'running' ? (
                    <span style={{ animation: 'chatroom-pulse 1.5s infinite' }}>◉</span>
                  ) : (
                    st.icon
                  )}
                </div>

                {/* Node header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 14 }} title={node.type}>
                    {typeIcon}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {node.label}
                  </span>
                  <span style={{
                    marginLeft: 'auto',
                    padding: '2px 8px',
                    borderRadius: 10,
                    background: st.bg,
                    color: st.color,
                    fontSize: 10,
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                  }}>
                    {st.label}
                  </span>
                </div>

                {/* Node meta */}
                <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span style={{
                    padding: '1px 6px',
                    borderRadius: 3,
                    background: 'var(--surface-elevated)',
                    color: NODE_TYPE_COLORS[node.type] || 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                  }}>
                    {node.type}
                  </span>
                  {node.agent_name && (
                    <span>👤 {node.agent_name}</span>
                  )}
                  {node.node_key && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, opacity: 0.6 }}>
                      {node.node_key}
                    </span>
                  )}
                </div>

                {/* Error message */}
                {status?.error && (
                  <div style={{
                    marginTop: 6,
                    padding: '6px 8px',
                    borderRadius: 4,
                    background: 'rgba(239,68,68,0.06)',
                    color: 'var(--red-400)',
                    fontSize: 11,
                    wordBreak: 'break-word',
                  }}>
                    ⚠ {status.error}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{
        padding: '10px 16px',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        gap: 12,
        flexWrap: 'wrap',
        fontSize: 10,
        color: 'var(--text-muted)',
        flexShrink: 0,
      }}>
        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
          <span key={key} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <span style={{ color: cfg.color }}>{cfg.icon}</span>
            {cfg.label}
          </span>
        ))}
      </div>
    </div>
  );
}

const NODE_TYPE_COLORS: Record<string, string> = {
  Agent: 'var(--blue-400)',
  Condition: 'var(--gold-400)',
  HITL: 'var(--pink-400)',
  Validation: 'var(--purple-400)',
  Router: 'var(--green-400)',
  Start: 'var(--text-dim)',
  End: 'var(--text-dim)',
  Parallel: 'var(--cyan-400)',
};
