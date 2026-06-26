/** Cherry Studio 风格思考过程展示 — 可独立使用或内联到消息气泡中 */
import { useState, useEffect } from 'react';
import type { ReasoningTrace } from '../../shared/types/session';

interface ThinkingSectionProps {
  reasoning: ReasoningTrace;
  defaultOpen?: boolean;  // 最新消息默认展开
}

export function ThinkingSection({ reasoning, defaultOpen = false }: ThinkingSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  // 同步 defaultOpen prop
  useEffect(() => { setOpen(defaultOpen); }, [defaultOpen]);

  const hasToolCalls = reasoning.tool_calls && reasoning.tool_calls.length > 0;
  const hasThinking = !!reasoning.thinking_steps;
  const hasSupervisor = !!(reasoning as any).supervisor_analysis;
  const hasGuidance = !!(reasoning as any).dispatch_guidance;
  const hasDecision = !!reasoning.decision_summary && !hasThinking;

  // 摘要标签
  const tags: string[] = [];
  if (reasoning.model_routing?.selected_model) tags.push(reasoning.model_routing.selected_model);
  if (hasToolCalls) tags.push(`${reasoning.tool_calls!.length} 次工具调用`);
  if ((reasoning as any).latency) tags.push(`${(reasoning as any).latency}s`);

  // 无内容则不渲染
  if (!hasThinking && !hasToolCalls && !hasSupervisor && !hasGuidance && !hasDecision) return null;

  return (
    <div style={containerStyle}>
      {/* 可点击折叠头 */}
      <div onClick={() => setOpen(!open)} style={headerStyle}>
        <span style={{
          display: 'inline-block',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s ease',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          ▶
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--gold-400)' }}>
          深度思考
        </span>
        {tags.length > 0 && (
          <span style={tagsStyle}>
            {tags.join(' · ')}
          </span>
        )}
      </div>

      {/* 展开内容 */}
      {open && (
        <div style={bodyStyle}>
          {/* 主管分析 */}
          {hasSupervisor && (
            <StepBlock color="var(--gold-400)" icon="👑">
              <div style={stepTitleStyle}>主管分析</div>
              <div style={stepContentStyle}>{(reasoning as any).supervisor_analysis}</div>
            </StepBlock>
          )}

          {/* 执行指导 */}
          {hasGuidance && (
            <StepBlock color="var(--cyan-400)" icon="📋">
              <div style={stepTitleStyle}>执行指导</div>
              <div style={stepContentStyle}>{(reasoning as any).dispatch_guidance}</div>
            </StepBlock>
          )}

          {/* 思考过程 */}
          {hasThinking && (
            <StepBlock color="var(--purple-400)" icon="💭">
              <div style={stepTitleStyle}>思考过程</div>
              <div style={{ ...stepContentStyle, maxHeight: 320, overflowY: 'auto' }}>
                {reasoning.thinking_steps}
              </div>
            </StepBlock>
          )}

          {/* 决策摘要 */}
          {hasDecision && (
            <StepBlock color="var(--green-400)" icon="✅">
              <div style={stepTitleStyle}>处理决策</div>
              <div style={stepContentStyle}>{reasoning.decision_summary}</div>
            </StepBlock>
          )}

          {/* 工具调用 */}
          {hasToolCalls && reasoning.tool_calls!.map((tc, i) => (
            <StepBlock key={i} color={tc.success ? 'var(--green-400)' : 'var(--red-400)'} icon="🔧">
              <div style={stepTitleStyle}>
                {tc.tool} {tc.success ? '✅' : '❌'}
              </div>
              {tc.params && Object.keys(tc.params).length > 0 && (
                <pre style={preStyle}>{JSON.stringify(tc.params, null, 2)}</pre>
              )}
              {tc.output && (
                <pre style={preStyle}>
                  {tc.output.length > 500 ? tc.output.slice(0, 500) + '...' : tc.output}
                </pre>
              )}
              {tc.error && (
                <div style={{ fontSize: 10, color: 'var(--red-400)', marginTop: 2 }}>错误: {tc.error}</div>
              )}
            </StepBlock>
          ))}

          {/* 上下文注入 */}
          {reasoning.context_used && (
            (reasoning.context_used.memories_injected ?? 0) > 0 ||
            (reasoning.context_used.rag_chunks ?? 0) > 0
          ) && (
            <StepBlock color="var(--purple-400)" icon="📚">
              <div style={stepTitleStyle}>上下文注入</div>
              <div style={stepDetailStyle}>
                记忆片段: {reasoning.context_used.memories_injected}
                {' · '}RAG 片段: {reasoning.context_used.rag_chunks}
                {' · '}总 Token: {reasoning.context_used.total_tokens}
              </div>
            </StepBlock>
          )}

          {/* 模型信息（底部小字） */}
          {(reasoning.model_routing?.selected_model || (reasoning as any).latency) && (
            <div style={modelInfoStyle}>
              {reasoning.model_routing?.selected_model && (
                <span>🧠 {reasoning.model_routing.selected_model}</span>
              )}
              {reasoning.model_routing?.provider && (
                <span> · {reasoning.model_routing.provider}</span>
              )}
              {(reasoning as any).latency && (
                <span> · ⏱️ {(reasoning as any).latency}s</span>
              )}
              {reasoning.context_used?.total_tokens > 0 && (
                <span> · 📊 {reasoning.context_used.total_tokens} tokens</span>
              )}
            </div>
          )}

          {/* 输入内容 */}
          {reasoning.input_content && (
            <StepBlock color="var(--text-muted)" icon="📝">
              <div style={stepTitleStyle}>输入内容</div>
              <div style={{
                ...preStyle,
                maxHeight: 200,
                color: 'var(--text-secondary)',
              }}>
                {reasoning.input_content}
              </div>
            </StepBlock>
          )}
        </div>
      )}
    </div>
  );
}

// ── 子组件 ──

function StepBlock({ color, icon, children }: { color: string; icon: string; children: React.ReactNode }) {
  return (
    <div style={{
      padding: '8px 10px',
      borderRadius: 6,
      background: 'rgba(0,0,0,0.15)',
      borderLeft: `3px solid ${color}`,
      marginBottom: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
        <span style={{ fontSize: 12, flexShrink: 0, marginTop: 1 }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      </div>
    </div>
  );
}

// ── 样式常量 ──

const containerStyle: React.CSSProperties = {
  marginBottom: 8,
  borderRadius: 8,
  border: '1px solid var(--border-subtle)',
  overflow: 'hidden',
  background: 'rgba(148,163,184,0.02)',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '7px 10px',
  cursor: 'pointer',
  userSelect: 'none',
  transition: 'background 0.15s',
};

const tagsStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  marginLeft: 4,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const bodyStyle: React.CSSProperties = {
  padding: '6px 10px 8px',
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const stepTitleStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  marginBottom: 4,
};

const stepContentStyle: React.CSSProperties = {
  fontSize: 11,
  lineHeight: 1.6,
  color: 'var(--text-secondary)',
  whiteSpace: 'pre-wrap',
};

const stepDetailStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-muted)',
  lineHeight: 1.5,
};

const preStyle: React.CSSProperties = {
  fontSize: 10,
  fontFamily: 'var(--font-mono)',
  color: 'var(--text-dim)',
  background: 'rgba(0,0,0,0.2)',
  padding: '6px 8px',
  borderRadius: 4,
  marginTop: 4,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  maxHeight: 120,
  overflowY: 'auto',
};

const modelInfoStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  padding: '4px 0 0',
  borderTop: '1px solid rgba(148,163,184,0.06)',
  marginTop: 2,
};
