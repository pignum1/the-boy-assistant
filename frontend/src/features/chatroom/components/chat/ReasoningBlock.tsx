/**
 * ReasoningBlock — 消息气泡内嵌的折叠推理块
 *
 * 替代 AgentCardHeader 上方独立的「思考过程」面板。
 * 渲染位置：AgentCardHeader 之下、消息正文之上。
 *
 * 支持四种执行模式的差异化展示：
 *   plan_execute / react / reflexion / self_consistency
 */
import { useState } from 'react';
import type { AgentMessageItem } from '../../types/state';

interface Props {
  item: AgentMessageItem;
}

// ── 模式标签 ──
const MODE_BADGE: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  plan_execute:      { icon: '📋', label: 'Plan & Execute',  color: '#3b82f6', bg: 'rgba(59,130,246,0.10)' },
  react:             { icon: '🧠', label: 'ReAct',           color: '#f59e0b', bg: 'rgba(245,158,11,0.10)' },
  reflexion:         { icon: '🔁', label: 'Reflexion',       color: '#8b5cf6', bg: 'rgba(139,92,246,0.10)' },
  self_consistency:  { icon: '🎲', label: 'Self-Consistency',color: '#10b981', bg: 'rgba(16,185,129,0.10)' },
  rewoo:             { icon: '📦', label: 'ReWOO',           color: '#06b6d4', bg: 'rgba(6,182,212,0.10)' },
  chain_of_thought:  { icon: '🔗', label: '思维链',          color: '#6366f1', bg: 'rgba(99,102,241,0.10)' },
  single_pass:       { icon: '⚡', label: '单次执行',         color: '#64748b', bg: 'rgba(100,116,139,0.08)' },
};

export function ReasoningBlock({ item }: Props) {
  const r = item.reasoning as Record<string, unknown> | undefined;
  if (!r) return null;

  const execMode = (item.execMode || r.execMode || r.exec_mode || '') as string;
  const badge = MODE_BADGE[execMode] || MODE_BADGE.single_pass;
  const iterations = (r.iterations as number) || 0;
  const summary = computeSummary(execMode, r, item);
  const [open, setOpen] = useState(false);

  return (
    <div style={{ margin: '6px 0' }}>
      {/* 折叠头：徽标 + 摘要 */}
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          cursor: 'pointer', userSelect: 'none',
          fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic',
          padding: '1px 0',
        }}
      >
        <span style={{
          fontSize: 9, transition: 'transform 0.2s',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          color: 'var(--text-muted)',
        }}>▶</span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 3,
          fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 5,
          background: badge.bg, color: badge.color, fontStyle: 'normal',
        }}>
          {badge.icon} {badge.label}
        </span>
        <span style={{ flex: 1 }}>
          {summary}
        </span>
        {iterations > 0 && (
          <span style={{ color: 'var(--text-muted)', fontSize: 10, fontStyle: 'normal' }}>
            {iterations} 次调用
          </span>
        )}
      </div>

      {/* 展开体 */}
      {open && (
        <div style={{
          marginTop: 6,
          padding: '8px 12px',
          paddingLeft: 16,
          borderLeft: '2px solid var(--border-subtle)',
          fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic',
          lineHeight: 1.65,
          maxHeight: 500, overflowY: 'auto',
        }}>
          {/* ReAct 迭代链 */}
          {renderReactHistory(r)}

          {/* Reflexion 反思轮次 */}
          {renderReflexions(r)}

          {/* Self-Consistency 采样 */}
          {renderSamples(r)}

          {/* Plan&Execute 审查 */}
          {renderReview(r)}

          {/* ReWOO 计划 + 工具结果 */}
          {renderReWOO(r)}

          {/* 通用：主管分析 / 决策 */}
          {renderGeneric(r)}

          {/* 结论行 */}
          <div style={{
            marginTop: 8, paddingTop: 8, borderTop: '1px dashed var(--border-subtle)',
            fontSize: 12, fontStyle: 'normal', color: 'var(--text-primary)',
          }}>
            <span style={{ color: 'var(--cyan-400)', fontWeight: 600 }}>判定：</span>
            {getConclusion(execMode, r)}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 辅助函数 ──

function computeSummary(mode: string, r: Record<string, unknown>, item: AgentMessageItem): string {
  if (mode === 'react') {
    const history = (r.history as string[]) || [];
    const iterCount = history.filter(h => h.startsWith('THOUGHT')).length;
    return iterCount > 0 ? `${iterCount} 轮推理完成` : '推理中…';
  }
  if (mode === 'reflexion') {
    const reflections = (r.reflections as Array<Record<string, unknown>>) || [];
    const scores = reflections.map(ref => ref.score as number || 0);
    return scores.length > 0
      ? `${scores.length} 轮迭代 · ${scores.join('→')} 分${scores[scores.length - 1] >= 80 ? ' → 通过' : ''}`
      : '反思中…';
  }
  if (mode === 'self_consistency') {
    const samples = (r.samples as string[]) || [];
    return samples.length > 0 ? `${samples.length} 路采样${r.merged ? ' → 已合并' : ''}` : '采样中…';
  }
  if (mode === 'plan_execute') {
    return '规划执行完成';
  }
  const thinkingSteps = (r.thinkingSteps || r.thinking_steps || '') as string;
  return thinkingSteps ? `思考完成 (${thinkingSteps.length} 字)` : '';
}

function getConclusion(mode: string, r: Record<string, unknown>): string {
  if (mode === 'reflexion') {
    const reflections = (r.reflections as Array<Record<string, unknown>>) || [];
    const last = reflections[reflections.length - 1];
    if (last) {
      const score = last.score as number || 0;
      return `置信度 ${score}/100 · ${score >= 80 ? '建议采纳' : score >= 60 ? '需人工复核' : '建议重新推理'}`;
    }
  }
  if (mode === 'self_consistency') {
    return r.merged ? '多路采样已合并，建议采纳' : '采样未合并，建议人工对比';
  }
  if (mode === 'react') {
    return 'ReAct 迭代完成，结论见上方正文';
  }
  return '推理完成';
}

// ── 渲染函数 ──

function renderReactHistory(r: Record<string, unknown>) {
  const history = (r.history as string[]) || [];
  if (history.length === 0) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
        🧠 ReAct 迭代链 ({history.length} 步)
      </div>
      {history.map((h, i) => {
        const isThought = h.startsWith('THOUGHT');
        const isAction = h.startsWith('ACTION');
        const isObs = h.startsWith('OBSERVATION');
        return (
          <div key={i} style={{
            fontSize: 11, fontFamily: 'var(--font-mono)', marginBottom: 2,
            padding: '3px 8px', borderRadius: 4,
            background: isThought ? 'rgba(59,130,246,0.06)' : isAction ? 'rgba(16,185,129,0.06)' : isObs ? 'rgba(245,158,11,0.06)' : 'transparent',
            borderLeft: `3px solid ${isThought ? '#3b82f6' : isAction ? '#10b981' : isObs ? '#f59e0b' : '#94a3b8'}`,
            color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {h.length > 300 ? h.substring(0, 300) + '...' : h}
          </div>
        );
      })}
    </div>
  );
}

function renderReflexions(r: Record<string, unknown>) {
  const reflections = (r.reflections as Array<Record<string, unknown>>) || [];
  if (reflections.length === 0) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
        🔁 Reflexion 反思 ({reflections.length} 轮)
      </div>
      {reflections.map((ref, i) => {
        const score = ref.score as number || 0;
        const verdict = ref.verdict as string || '';
        const issues = (ref.issues as Array<Record<string, unknown>>) || [];
        return (
          <div key={i} style={{
            padding: '5px 9px', borderRadius: 6, marginBottom: 4,
            background: verdict === 'pass' ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)',
            border: `1px solid ${verdict === 'pass' ? '#10b98133' : '#f59e0b33'}`,
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 3 }}>
              第 {i+1} 轮 · 评分 {score}/100 · {verdict === 'pass' ? '✅ 通过' : '🔄 需改进'}
            </div>
            {issues.map((issue, j) => (
              <div key={j} style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, padding: '1px 5px', borderLeft: '2px solid #f59e0b' }}>
                [{issue.severity || '?'}] {String(issue.problem || '')}
                {issue.suggestion && <span style={{ color: '#10b981' }}> → {String(issue.suggestion)}</span>}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function renderSamples(r: Record<string, unknown>) {
  const samples = (r.samples as string[]) || [];
  if (samples.length === 0) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
        🎲 Self-Consistency 采样 ({samples.length} 路)
      </div>
      {samples.map((s, i) => (
        <div key={i} style={{
          fontSize: 11, padding: '4px 8px', borderRadius: 4, marginBottom: 2,
          background: 'rgba(6,182,212,0.04)', border: '1px solid rgba(6,182,212,0.12)',
          color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          maxHeight: 100, overflowY: 'auto',
        }}>
          <span style={{ fontSize: 9, color: 'var(--text-muted)', fontWeight: 600 }}>#{i+1} </span>
          {s.length > 200 ? s.substring(0, 200) + '...' : s}
        </div>
      ))}
      {r.merged && (
        <div style={{ fontSize: 11, color: '#10b981', marginTop: 4, fontWeight: 500 }}>✅ 已合并采纳</div>
      )}
    </div>
  );
}

function renderReview(r: Record<string, unknown>) {
  const score = r.review_score as number | undefined;
  if (score == null) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
        📋 Plan & Execute
      </div>
      <div style={{ fontSize: 12, color: score >= 70 ? '#10b981' : '#f59e0b', fontWeight: 500 }}>
        📊 审查评分: {score}/100 {score >= 70 ? '✓ 通过' : '⚠ 需补全'}
      </div>
    </div>
  );
}

function renderReWOO(r: Record<string, unknown>) {
  const plan = r.plan as Record<string, unknown> | undefined;
  const toolResults = (r.tool_results as Array<Record<string, unknown>>) || [];
  if (!plan && toolResults.length === 0) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
        📦 ReWOO
      </div>
      {plan && (
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
          {String(plan.analysis || '')}
        </div>
      )}
      {(plan?.steps as Array<Record<string,unknown>> || []).map((step, i) => (
        <div key={i} style={{ fontSize: 10, padding: '3px 8px', marginBottom: 2, borderRadius: 3, background: 'rgba(52,211,153,0.06)', border: '1px solid rgba(52,211,153,0.12)', color: 'var(--text-muted)' }}>
          {step.step}. {String(step.description || '')} → {String(step.tool || '?')}
        </div>
      ))}
      {toolResults.map((tr, i) => (
        <div key={i} style={{ fontSize: 10, padding: '3px 8px', marginBottom: 2, borderRadius: 3, background: tr.error ? 'rgba(239,68,68,0.06)' : 'rgba(16,185,129,0.06)', border: `1px solid ${tr.error ? '#ef444433' : '#10b98133'}`, color: 'var(--text-muted)' }}>
          {tr.error ? '❌' : '✅'} {String(tr.tool || '')}{tr.error ? ` — ${String(tr.error)}` : ''}
        </div>
      ))}
    </div>
  );
}

function renderGeneric(r: Record<string, unknown>) {
  const supervisor = (r.supervisorAnalysis || '') as string;
  const thinking = (r.thinkingSteps || r.thinking_steps || '') as string;
  const decision = (r.decisionSummary || '') as string;
  if (!supervisor && !thinking && !decision) return null;
  return (
    <div style={{ marginBottom: 8 }}>
      {supervisor && (
        <div>
          <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>主管分析</div>
          <pre style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', whiteSpace: 'pre-wrap', margin: 0 }}>{supervisor}</pre>
        </div>
      )}
      {thinking && (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>思考过程</div>
          <pre style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', whiteSpace: 'pre-wrap', margin: 0 }}>{thinking}</pre>
        </div>
      )}
      {decision && (
        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-primary)', fontStyle: 'normal', fontWeight: 500 }}>
          💡 {decision}
        </div>
      )}
    </div>
  );
}
