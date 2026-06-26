import type { NodeState } from './hooks/useTaskEvents';

interface PipelineViewProps {
  nodeStates: Record<string, NodeState>;
  sopName?: string;
}

const STATUS_STYLE: Record<string, { bg: string; color: string; icon: string }> = {
  pending: { bg: 'rgba(148,163,184,0.08)', color: 'var(--text-muted)', icon: '⏸' },
  running: { bg: 'var(--green-bg)', color: 'var(--green-400)', icon: '🔄' },
  completed: { bg: 'var(--green-bg)', color: 'var(--green-400)', icon: '✅' },
  failed: { bg: 'var(--red-bg)', color: 'var(--red-400)', icon: '❌' },
  waiting_approval: { bg: 'var(--gold-bg)', color: 'var(--gold-400)', icon: '🤔' },
};

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
  waiting_approval: '等待确认',
};

export function PipelineView({ nodeStates, sopName }: PipelineViewProps) {
  const entries = Object.values(nodeStates);
  const runningNode = entries.find(n => n.status === 'running');
  const completedCount = entries.filter(n => n.status === 'completed').length;
  const progress = entries.length > 0 ? Math.round((completedCount / entries.length) * 100) : 0;

  return (
    <div
      style={{
        width: 260,
        background: 'var(--bg-base)',
        borderRight: '1px solid var(--border-subtle)',
        padding: 16,
        overflowY: 'auto',
        flexShrink: 0,
      }}
    >
      {/* 工作流标题 */}
      {sopName && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            工作流
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{sopName}</div>
        </div>
      )}

      {/* 当前执行状态 */}
      {runningNode && (
        <div style={{
          padding: 12,
          borderRadius: 8,
          background: 'var(--green-bg)',
          border: '1px solid var(--green-border)',
          marginBottom: 16,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontSize: 14 }}>🔄</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--green-400)' }}>正在执行</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>
            {runningNode.nodeId}
          </div>
          {runningNode.agent && (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
              由 {runningNode.agent} 执行
            </div>
          )}
        </div>
      )}

      {/* 进度条 */}
      {entries.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>进度</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{progress}%</span>
          </div>
          <div style={{
            height: 6,
            borderRadius: 3,
            background: 'var(--bg-elevated)',
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${progress}%`,
              background: 'linear-gradient(90deg, var(--green-400), var(--green-500))',
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      )}

      {/* 节点列表 */}
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>
        执行步骤
      </div>
      {entries.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-dim)', textAlign: 'center', padding: 20 }}>等待节点执行...</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {entries.map((node, index) => {
            const s = STATUS_STYLE[node.status] || STATUS_STYLE.pending;
            return (
              <div
                key={node.nodeId}
                style={{
                  borderRadius: 6,
                  border: '1px solid var(--border-subtle)',
                  padding: '8px 10px',
                  background: node.status === 'running' ? 'var(--green-bg)' : 'var(--bg-card)',
                  borderLeft: node.status === 'running' ? '3px solid var(--green-400)' : '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12 }}>{s.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: node.status === 'running' ? 'var(--green-400)' : 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {node.nodeId}
                    </div>
                    {node.agent && (
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
                        {node.agent}
                      </div>
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 9,
                      padding: '2px 6px',
                      borderRadius: 8,
                      background: s.bg,
                      color: s.color,
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {STATUS_LABELS[node.status] || node.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
