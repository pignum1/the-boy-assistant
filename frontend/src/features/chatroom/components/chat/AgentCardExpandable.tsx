/** Agent 卡片可展开区域：思考过程 / 模型路由 / 工具调用 / 产物 / 模式专属详情 */
import type { AgentMessageItem, ArtifactFile } from '../../types/state';

interface Props {
  item: AgentMessageItem;
  artifacts: ArtifactFile[];
}

const MODE_LABEL: Record<string, string> = {
  single_pass: '单次执行', chain_of_thought: '思维链', plan_execute: '规划-执行',
  rewoo: 'ReWOO', react: 'ReAct', reflexion: 'Reflexion', self_consistency: '自一致性',
};

export function AgentCardExpandable({ item, artifacts }: Props) {
  const r = item.reasoning as Record<string, unknown> | undefined;
  if (!r && artifacts.length === 0) return null;

  // 兼容 camelCase + snake_case
  const supervisorAnalysis = (r?.supervisorAnalysis || '') as string;
  const thinkingSteps = (r?.thinkingSteps || r?.thinking_steps || '') as string;
  const decisionSummary = (r?.decisionSummary || '') as string;
  const execMode = (item.execMode || r?.execMode || r?.exec_mode || '') as string;
  const iterations = (r?.iterations as number) || 0;
  const modelRouting = r?.modelRouting as Record<string, unknown> | undefined;
  const toolCalls = (r?.toolCalls as Array<Record<string, unknown>>) || [];
  const modeLabel = MODE_LABEL[execMode] || execMode;

  // ── 模式专属数据 ──
  const reviewScore = r?.review_score as number | undefined;
  const history = (r?.history as string[]) || [];
  const reflections = (r?.reflections as Array<Record<string, unknown>>) || [];
  const samples = (r?.samples as string[]) || [];
  const merged = r?.merged as boolean | undefined;
  const plan = r?.plan as Record<string, unknown> | undefined;
  const rewooResults = (r?.tool_results as Array<Record<string, unknown>>) || [];

  return (
    <div style={{
      borderTop: '1px solid var(--border-subtle)',
      marginTop: 8, paddingTop: 8,
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      {/* ── 模式概览 ── */}
      {execMode && (
        <Section title={`${modeLabel} · ${iterations} 次调用`}>
          {/* plan_execute: 审查评分 */}
          {reviewScore != null && (
            <div style={{ fontSize: 12, color: reviewScore >= 70 ? '#10b981' : '#f59e0b' }}>
              📊 审查评分: {reviewScore}/100 {reviewScore >= 70 ? '✓ 通过' : '⚠ 需补全'}
            </div>
          )}
          {/* self_consistency: 采样概览 */}
          {samples.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              🗳️ {samples.length} 次采样{merged ? ' → 已综合' : ''}
            </div>
          )}
        </Section>
      )}

      {/* ── React: THOUGHT/ACTION 迭代链 ── */}
      {history.length > 0 && (
        <Section title={`ReAct 迭代链 (${history.length} 步)`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {history.map((h, i) => (
              <div key={i} style={{
                fontSize: 11, fontFamily: 'var(--font-mono)',
                padding: '4px 8px', borderRadius: 4,
                background: h.startsWith('THOUGHT') ? 'rgba(59,130,246,0.06)' :
                           h.startsWith('ACTION') ? 'rgba(16,185,129,0.06)' :
                           h.startsWith('OBSERVATION') ? 'rgba(245,158,11,0.06)' :
                           h.startsWith('##') ? 'rgba(139,92,246,0.06)' :
                           'rgba(148,163,184,0.04)',
                borderLeft: `3px solid ${
                  h.startsWith('THOUGHT') ? '#3b82f6' :
                  h.startsWith('ACTION') ? '#10b981' :
                  h.startsWith('OBSERVATION') ? '#f59e0b' :
                  h.startsWith('##') ? '#8b5cf6' : '#94a3b8'
                }`,
                color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              }}>
                {h.length > 300 ? h.substring(0, 300) + '...' : h}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Reflexion: 批判→重做轮次 ── */}
      {reflections.length > 0 && (
        <Section title={`Reflexion 反思轮次 (${reflections.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {reflections.map((ref, i) => {
              const score = ref.score as number || 0;
              const verdict = ref.verdict as string || '';
              const issues = (ref.issues as Array<Record<string, unknown>>) || [];
              return (
                <div key={i} style={{
                  padding: '6px 10px', borderRadius: 6,
                  background: verdict === 'pass' ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)',
                  border: `1px solid ${verdict === 'pass' ? '#10b98133' : '#f59e0b33'}`,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: 'var(--text-secondary)' }}>
                    第 {i+1} 轮 · 评分 {score}/100 · {verdict === 'pass' ? '✅ 通过' : '🔄 需改进'}
                  </div>
                  {issues.map((issue, j) => (
                    <div key={j} style={{
                      fontSize: 10, color: 'var(--text-muted)', marginTop: 2,
                      padding: '2px 6px', borderLeft: '2px solid #f59e0b',
                    }}>
                      [{issue.severity || '?'}] {String(issue.problem || issue.issue || '')}
                      {issue.suggestion && <div style={{ color: '#10b981' }}>→ {String(issue.suggestion)}</div>}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* ── Self-Consistency: 采样结果 ── */}
      {samples.length > 0 && (
        <Section title={`采样结果 (${samples.length} 次)`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {samples.map((s, i) => (
              <div key={i} style={{
                fontSize: 11, padding: '4px 8px', borderRadius: 4,
                background: 'rgba(6,182,212,0.04)', border: '1px solid rgba(6,182,212,0.12)',
                color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 100, overflowY: 'auto',
              }}>
                <span style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600 }}>#{i+1} </span>
                {s.length > 200 ? s.substring(0, 200) + '...' : s}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── ReWOO: 计划 + 工具结果 ── */}
      {plan && (
        <Section title="ReWOO 执行计划">
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
            {String(plan.analysis || '')}
          </div>
          {(plan.steps as Array<Record<string,unknown>> || []).map((step, i) => (
            <div key={i} style={{
              fontSize: 10, padding: '3px 8px', marginBottom: 2, borderRadius: 3,
              background: 'rgba(52,211,153,0.06)', border: '1px solid rgba(52,211,153,0.12)',
              color: 'var(--text-muted)',
            }}>
              {step.step}. {String(step.description || '')} → {String(step.tool || '?')}
            </div>
          ))}
        </Section>
      )}
      {rewooResults.length > 0 && (
        <Section title={`工具执行结果 (${rewooResults.length})`}>
          {rewooResults.map((tr, i) => (
            <div key={i} style={{
              fontSize: 10, padding: '3px 8px', marginBottom: 2, borderRadius: 3,
              background: tr.error ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)',
              border: `1px solid ${tr.error ? '#ef444433' : '#10b98133'}`,
              color: 'var(--text-muted)',
            }}>
              {tr.error ? '❌' : '✅'} 步骤{tr.step}: {String(tr.tool || '')}
              {tr.error ? ` — 错误: ${String(tr.error)}` : ''}
            </div>
          ))}
        </Section>
      )}

      {/* ── 通用段 ── */}
      {supervisorAnalysis && (
        <Section title="主管分析">
          <pre style={preStyle}>{supervisorAnalysis}</pre>
        </Section>
      )}

      {thinkingSteps && (
        <Section title="思考过程">
          <pre style={preStyle}>{thinkingSteps}</pre>
        </Section>
      )}

      {decisionSummary && !supervisorAnalysis && (
        <Section title="决策摘要">
          <pre style={preStyle}>{decisionSummary}</pre>
        </Section>
      )}

      {modelRouting?.selectedModel && (
        <Section title="模型路由">
          <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
            <span style={{ color: 'var(--cyan-400)' }}>{String(modelRouting.selectedModel)}</span>
            {modelRouting.complexity && <span style={{ color: 'var(--text-muted)' }}> · 复杂度 {String(modelRouting.complexity)}</span>}
            {modelRouting.fallbackUsed && <span style={{ color: 'var(--gold-400)' }}> · fallback ({String(modelRouting.fallbackReason || '?')})</span>}
          </div>
        </Section>
      )}

      {toolCalls.length > 0 && (
        <Section title={`工具调用 (${toolCalls.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {toolCalls.map((tc, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                <span style={{ color: tc.status === 'done' ? 'var(--green-400)' : tc.status === 'error' ? 'var(--red-400)' : 'var(--blue-400)' }}>
                  {tc.status === 'done' ? '✓' : tc.status === 'error' ? '✗' : '⏳'}
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>{tc.tool as string}</span>
                {tc.detail && <span style={{ color: 'var(--text-muted)', fontSize: 10, marginLeft: 'auto', maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tc.detail as string}</span>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {artifacts.length > 0 && (
        <Section title={`产物 (${artifacts.length})`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {artifacts.map(a => <ArtifactChip key={a.id} artifact={a} />)}
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{title}</div>
      {children}
    </div>
  );
}

function ArtifactChip({ artifact }: { artifact: ArtifactFile }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, background: 'rgba(34,211,238,0.06)', border: '1px solid var(--cyan-border)', color: 'var(--cyan-400)', fontSize: 10, fontFamily: 'var(--font-mono)' }} title={artifact.path}>
      📎 {artifact.name}{artifact.sizeBytes > 0 && <span style={{ color: 'var(--text-muted)', marginLeft: 2 }}>({formatSize(artifact.sizeBytes)})</span>}
    </span>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

const preStyle: React.CSSProperties = {
  fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
  background: 'rgba(148,163,184,0.04)', border: '1px solid var(--border-subtle)',
  borderRadius: 4, padding: '6px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  margin: 0, lineHeight: 1.6,
};
