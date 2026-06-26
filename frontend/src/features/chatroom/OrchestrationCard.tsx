/** OrchestrationCard — 编排流水线可视化卡片

嵌入消息流中，实时展示 M0-M7 协作流水线进度。
- 顶部：流水线进度条（圆点 + 连线）
- 中部：当前阶段名称 + Agent 分配
- 底部：实时思考详情（可折叠）
*/
import { useState, useEffect } from 'react';
import type { OrchestrationState, OrchestrationStage, OrchestrationThinking } from '../../shared/types/session';

interface Props {
  state: OrchestrationState;
}

// ── 颜色常量 ──

const STATUS_COLORS: Record<string, { dot: string; bg: string; border: string; text: string }> = {
  pending:  { dot: '#334155', bg: 'transparent',          border: '#334155', text: '#64748b' },
  thinking: { dot: '#f59e0b', bg: 'rgba(245,158,11,0.08)', border: '#f59e0b', text: '#f59e0b' },
  done:     { dot: '#10b981', bg: 'rgba(16,185,129,0.08)', border: '#10b981', text: '#10b981' },
  skipped:  { dot: '#475569', bg: 'transparent',          border: '#475569', text: '#475569' },
};

export function OrchestrationCard({ state }: Props) {
  const [thinkingOpen, setThinkingOpen] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  // 计时器：当前阶段 thinking 时每秒更新
  useEffect(() => {
    if (state.completed || !state.currentStageId) {
      setElapsed(0);
      return;
    }
    const current = state.stages.find(s => s.id === state.currentStageId);
    if (!current || current.status !== 'thinking') {
      setElapsed(0);
      return;
    }
    setElapsed(0);
    const timer = setInterval(() => setElapsed(prev => prev + 1), 1000);
    return () => clearInterval(timer);
  }, [state.currentStageId, state.completed, state.stages]);

  // 自动展开思考区
  useEffect(() => {
    if (state.thinking) setThinkingOpen(true);
  }, [state.thinking?.agentName]);

  const { stages, currentStageId, thinking, completed, completionSummary } = state;

  // ── 完成状态：单行摘要 ──
  if (completed) {
    const doneCount = stages.filter(s => s.status === 'done').length;
    const skippedCount = stages.filter(s => s.status === 'skipped').length;
    return (
      <div style={completedContainerStyle}>
        <span style={{ color: 'var(--green-400)', fontSize: 12 }}>✅</span>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
          协作流程完成 · {doneCount} 个阶段{skippedCount > 0 ? ` · ${skippedCount} 个跳过` : ''}
          {completionSummary && ` · ${completionSummary}`}
        </span>
      </div>
    );
  }

  const currentStage = stages.find(s => s.id === currentStageId);
  const currentIdx = stages.findIndex(s => s.id === currentStageId);

  return (
    <div style={containerStyle}>
      {/* ── 标题栏 ── */}
      <div style={headerStyle}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--gold-400)' }}>
          🔄 协作流程
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
          {currentStage ? currentStage.label : '准备中...'}
        </span>
      </div>

      {/* ── 流水线进度条 ── */}
      <div style={pipelineStyle}>
        {stages.map((stage, i) => {
          const colors = STATUS_COLORS[stage.status];
          const isCurrent = stage.id === currentStageId;
          return (
            <div key={stage.id} style={{ display: 'flex', alignItems: 'center' }}>
              {/* 圆点 */}
              <div
                style={dotStyle(colors, isCurrent)}
                title={stage.label}
              >
                {stage.status === 'done' ? '✓' :
                 stage.status === 'skipped' ? '⏭' :
                 stage.status === 'thinking' ? (
                   <span style={{ animation: 'blink 1s step-end infinite', fontSize: 7 }}>●</span>
                 ) : (
                   <span style={{ fontSize: 7, opacity: 0.5 }}>{i}</span>
                 )}
              </div>
              {/* 标签 */}
              <span style={{
                fontSize: 9,
                color: colors.text,
                marginLeft: 3,
                fontWeight: isCurrent ? 600 : 400,
                whiteSpace: 'nowrap',
              }}>
                {stage.shortLabel}
              </span>
              {/* 连线 */}
              {i < stages.length - 1 && (
                <div style={{
                  width: 12,
                  height: 1,
                  margin: '0 2px',
                  background: stage.status === 'done' ? 'rgba(16,185,129,0.3)' : '#1e293b',
                  flexShrink: 0,
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* ── 当前阶段详情 ── */}
      {currentStage && (
        <div style={detailStyle}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            {currentStage.status === 'thinking' ? '🔄' : currentStage.status === 'done' ? '✅' : '⏳'}
            {' '}{currentStage.label}
          </div>

          {/* Agent 分配 */}
          {currentStage.agents.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
              {currentStage.agents.map((a, i) => (
                <span key={i} style={agentTagStyle}>
                  🤖 {a.name}
                  {a.role && <span style={{ color: 'var(--text-dim)', marginLeft: 4 }}>{a.role}</span>}
                </span>
              ))}
            </div>
          )}

          {/* 思考中提示 */}
          {currentStage.status === 'thinking' && thinking && (
            <div style={thinkingLineStyle}>
              <span style={{ color: thinking.agentName.includes('Supervisor') ? 'var(--gold-400)' : 'var(--blue-400)', fontSize: 11 }}>
                {thinking.agentName}
              </span>
              <span style={{ color: 'var(--text-dim)', fontSize: 10 }}> 正在工作</span>
              {thinking.model && (
                <span style={{ color: 'var(--text-dim)', fontSize: 9, marginLeft: 8 }}>
                  🧠 {thinking.model}
                </span>
              )}
              {elapsed > 0 && (
                <span style={{ color: 'var(--text-dim)', fontSize: 9, marginLeft: 8 }}>
                  ⏱️ {elapsed}s
                </span>
              )}
            </div>
          )}

          {/* 阶段完成摘要 */}
          {currentStage.status === 'done' && currentStage.summary && (
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {currentStage.summary}
            </div>
          )}
        </div>
      )}

      {/* ── 思考详情折叠区 ── */}
      {thinking && (thinking.summary || thinking.toolCalls.length > 0) && (
        <div style={thinkFoldStyle}>
          <div
            onClick={() => setThinkingOpen(!thinkingOpen)}
            style={thinkFoldHeaderStyle}
          >
            <span style={{
              display: 'inline-block',
              transform: thinkingOpen ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease',
              fontSize: 9,
              color: 'var(--text-dim)',
            }}>▶</span>
            <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--gold-400)' }}>
              思考过程
            </span>
            {thinking.toolCalls.length > 0 && (
              <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 4 }}>
                🔧 {thinking.toolCalls.length} 次工具调用
              </span>
            )}
          </div>

          {thinkingOpen && (
            <div style={thinkFoldBodyStyle}>
              {thinking.summary && (
                <div style={thinkBlockStyle('var(--gold-400)')}>
                  <div style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {thinking.summary}
                  </div>
                </div>
              )}
              {thinking.toolCalls.map((tc, i) => (
                <div key={i} style={thinkBlockStyle(tc.status === 'done' ? 'var(--green-400)' : tc.status === 'error' ? 'var(--red-400)' : 'var(--blue-400)')}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)' }}>
                    🔧 {tc.tool} {tc.status === 'done' ? '✅' : tc.status === 'running' ? '🔄' : '❌'}
                  </div>
                  {tc.detail && (
                    <div style={{
                      fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-dim)',
                      marginTop: 3, maxHeight: 60, overflow: 'hidden',
                    }}>
                      {tc.detail.length > 120 ? tc.detail.slice(0, 120) + '...' : tc.detail}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ── 样式 ──

const containerStyle: React.CSSProperties = {
  borderRadius: 10,
  border: '1px solid var(--border-subtle)',
  background: 'var(--bg-card)',
  margin: '8px 0',
  overflow: 'hidden',
  animation: 'slideIn 0.3s ease',
};

const completedContainerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 14px',
  borderRadius: 8,
  background: 'rgba(16,185,129,0.06)',
  border: '1px solid rgba(16,185,129,0.15)',
  margin: '6px 0',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '8px 14px',
  borderBottom: '1px solid rgba(148,163,184,0.06)',
  background: 'rgba(0,0,0,0.15)',
};

const pipelineStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  padding: '8px 14px 6px',
  overflowX: 'auto',
  gap: 0,
};

const dotStyle = (colors: typeof STATUS_COLORS['pending'], isCurrent: boolean): React.CSSProperties => ({
  width: isCurrent ? 20 : 16,
  height: isCurrent ? 20 : 16,
  borderRadius: '50%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 8,
  fontWeight: 700,
  border: `1.5px solid ${colors.border}`,
  background: colors.bg,
  color: colors.text,
  flexShrink: 0,
  transition: 'all 0.3s ease',
});

const detailStyle: React.CSSProperties = {
  padding: '8px 14px',
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const agentTagStyle: React.CSSProperties = {
  fontSize: 10,
  padding: '2px 8px',
  borderRadius: 4,
  background: 'rgba(0,0,0,0.2)',
  border: '1px solid var(--border-subtle)',
  color: 'var(--text-secondary)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 2,
};

const thinkingLineStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  marginTop: 4,
  animation: 'blink 2s step-end infinite',
};

const thinkFoldStyle: React.CSSProperties = {
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const thinkFoldHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 14px',
  cursor: 'pointer',
  userSelect: 'none',
};

const thinkFoldBodyStyle: React.CSSProperties = {
  padding: '4px 14px 8px',
};

const thinkBlockStyle = (borderColor: string): React.CSSProperties => ({
  padding: '5px 8px',
  borderRadius: 4,
  background: 'rgba(0,0,0,0.15)',
  borderLeft: `2px solid ${borderColor}`,
  marginBottom: 4,
});
