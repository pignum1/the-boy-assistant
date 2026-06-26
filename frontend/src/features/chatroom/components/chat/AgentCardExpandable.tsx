/** Agent 卡片可展开区域：思考过程 / 模型路由 / 工具调用 / 产物 */
import type { AgentMessageItem, ArtifactFile } from '../../types/state';

interface Props {
  item: AgentMessageItem;
  /** 通过 artifactIds 查到的产物文件 */
  artifacts: ArtifactFile[];
}

export function AgentCardExpandable({ item, artifacts }: Props) {
  const r = item.reasoning;
  if (!r && artifacts.length === 0) return null;

  return (
    <div style={{
      borderTop: '1px solid var(--border-subtle)',
      marginTop: 8,
      paddingTop: 8,
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      {r?.supervisorAnalysis && (
        <Section title="主管分析">
          <pre style={preStyle}>{r.supervisorAnalysis}</pre>
        </Section>
      )}

      {r?.thinkingSteps && (
        <Section title="思考过程">
          <pre style={preStyle}>{r.thinkingSteps}</pre>
        </Section>
      )}

      {r?.decisionSummary && !r.supervisorAnalysis && (
        <Section title="决策摘要">
          <pre style={preStyle}>{r.decisionSummary}</pre>
        </Section>
      )}

      {r?.modelRouting?.selectedModel && (
        <Section title="模型路由">
          <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            <span style={{ color: 'var(--cyan-400)' }}>{r.modelRouting.selectedModel}</span>
            {r.modelRouting.complexity && (
              <span style={{ color: 'var(--text-muted)' }}> · 复杂度 {r.modelRouting.complexity}</span>
            )}
            {r.modelRouting.fallbackUsed && (
              <span style={{ color: 'var(--gold-400)' }}> · 已 fallback ({r.modelRouting.fallbackReason || '原因未知'})</span>
            )}
          </div>
        </Section>
      )}

      {r?.toolCalls && r.toolCalls.length > 0 && (
        <Section title={`工具调用 (${r.toolCalls.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {r.toolCalls.map((tc, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
              }}>
                <span style={{
                  color:
                    tc.status === 'done' ? 'var(--green-400)' :
                    tc.status === 'error' ? 'var(--red-400)' : 'var(--blue-400)',
                }}>
                  {tc.status === 'done' ? '✓' : tc.status === 'error' ? '✗' : '⏳'}
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>{tc.tool}</span>
                {tc.detail && (
                  <span style={{ color: 'var(--text-muted)', fontSize: 10, marginLeft: 'auto', maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {tc.detail}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {artifacts.length > 0 && (
        <Section title={`产物 (${artifacts.length})`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {artifacts.map(a => (
              <ArtifactChip key={a.id} artifact={a} />
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{
        fontSize: 10,
        color: 'var(--text-muted)',
        marginBottom: 4,
        fontFamily: 'var(--font-mono)',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function ArtifactChip({ artifact }: { artifact: ArtifactFile }) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '3px 8px',
      borderRadius: 4,
      background: 'rgba(34, 211, 238, 0.06)',
      border: '1px solid var(--cyan-border)',
      color: 'var(--cyan-400)',
      fontSize: 10,
      fontFamily: 'var(--font-mono)',
    }} title={artifact.path}>
      📎 {artifact.name}
      {artifact.sizeBytes > 0 && (
        <span style={{ color: 'var(--text-muted)', marginLeft: 2 }}>
          ({formatSize(artifact.sizeBytes)})
        </span>
      )}
    </span>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

const preStyle: React.CSSProperties = {
  fontSize: 11,
  fontFamily: 'var(--font-mono)',
  color: 'var(--text-secondary)',
  background: 'rgba(148,163,184,0.04)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 4,
  padding: '6px 10px',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  margin: 0,
  lineHeight: 1.6,
};
