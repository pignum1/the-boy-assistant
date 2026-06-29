/** Cherry Studio 风格消息气泡 — 思考过程内联展示，Markdown 渲染 */
import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentMsg } from './hooks/useTaskEvents';
import type { ReasoningTrace } from '../../shared/types/session';
import { TaskCard } from './TaskCard';

interface MessageBubbleProps {
  msg: AgentMsg & {
    isThinking?: boolean;
    isStreaming?: boolean;
    avatarColor?: string;
    roleSlot?: string;
    reasoning?: ReasoningTrace;
  };
  reasoning?: ReasoningTrace;
  defaultThinkingOpen?: boolean;
  questions?: Array<{ text: string; type: string }>;
  isThinking?: boolean;
}

function agentInitial(name: string): string {
  const match = name.match(/^[一-龥]/);
  return match ? match[0] : name.charAt(0).toUpperCase();
}

/** Strip tool call JSON from displayed content */
function stripToolCallJson(content: string): string {
  if (!content) return '';
  let cleaned = content;
  cleaned = cleaned.replace(/TOOL_CALL:\s*\{[^}]*?"name"\s*:\s*".*?"[^}]*?"params"\s*:\s*\{[^}]*?\}\s*\}\s*\}?/g, '');
  cleaned = cleaned.replace(/\{"tool_call"\s*:\s*\{[^}]*?\}\s*\}/g, '');
  cleaned = cleaned.replace(/```json\s*\n?\s*\{[^`]*"tool_call"[^`]*\}\s*```/g, '');
  const tcIdx = cleaned.indexOf('{"tool_call"');
  if (tcIdx >= 0) {
    let depth = 0;
    let end = tcIdx;
    for (let i = tcIdx; i < cleaned.length; i++) {
      if (cleaned[i] === '{') depth++;
      else if (cleaned[i] === '}') {
        depth--;
        if (depth === 0) { end = i + 1; break; }
      }
    }
    if (end > tcIdx) cleaned = cleaned.slice(0, tcIdx) + cleaned.slice(end);
  }
  return cleaned.trim();
}

// ── 代码块组件（独立组件以使用 hooks）──

function CodeBlock({ className, children, ...props }: {
  className?: string; children?: React.ReactNode;
  node?: { position?: { start: { line: number }; end: { line: number } } };
  [key: string]: unknown;
}) {
  const codeStr = String(children).replace(/\n$/, '');
  const hasLang = /language-/.test(className || '');
  const isMultiline = codeStr.includes('\n');
  const node = props.node as { position?: { start: { line: number }; end: { line: number } } } | undefined;
  const nodeSpansMultipleLines = node?.position && (node.position.end.line - node.position.start.line > 0);
  const isBlock = hasLang || isMultiline || nodeSpansMultipleLines;
  const lang = (className || '').replace('language-', '');

  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(codeStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [codeStr]);

  if (isBlock) {
    return (
      <div style={codeBlockContainerStyle}>
        <div style={codeBlockHeaderStyle}>
          <span style={codeLangStyle}>{lang || 'code'}</span>
          <button onClick={handleCopy} style={copyBtnStyle}>
            {copied ? '✓ 已复制' : '📋 复制'}
          </button>
        </div>
        <pre style={codePreStyle}>
          <code className={className}>{codeStr}</code>
        </pre>
      </div>
    );
  }
  return (
    <code style={inlineCodeStyle}>{children}</code>
  );
}

// ── Cherry Studio 风格 Markdown 组件 ──

function markdownComponents() {
  return {
    code: CodeBlock,
    table({ children }: { children?: React.ReactNode }) {
      return (
        <div style={{ overflowX: 'auto', margin: '10px 0' }}>
          <table style={tableStyle}>{children}</table>
        </div>
      );
    },
    thead({ children }: { children?: React.ReactNode }) {
      return <thead style={{ background: 'rgba(148,163,184,0.06)' }}>{children}</thead>;
    },
    th({ children }: { children?: React.ReactNode }) {
      return <th style={thStyle}>{children}</th>;
    },
    td({ children }: { children?: React.ReactNode }) {
      return <td style={tdStyle}>{children}</td>;
    },
    a({ href, children }: { href?: string; children?: React.ReactNode }) {
      return <a href={href} target="_blank" rel="noopener" style={{ color: 'var(--blue-400)' }}>{children}</a>;
    },
    ul({ children }: { children?: React.ReactNode }) {
      return <ul style={{ paddingLeft: 20, margin: '6px 0' }}>{children}</ul>;
    },
    ol({ children }: { children?: React.ReactNode }) {
      return <ol style={{ paddingLeft: 20, margin: '6px 0' }}>{children}</ol>;
    },
    h1({ children }: { children?: React.ReactNode }) {
      return <h1 style={h1Style}>{children}</h1>;
    },
    h2({ children }: { children?: React.ReactNode }) {
      return <h2 style={h2Style}>{children}</h2>;
    },
    h3({ children }: { children?: React.ReactNode }) {
      return <h3 style={h3Style}>{children}</h3>;
    },
    blockquote({ children }: { children?: React.ReactNode }) {
      return <blockquote style={blockquoteStyle}>{children}</blockquote>;
    },
    hr() {
      return <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '12px 0' }} />;
    },
    p({ children }: { children?: React.ReactNode }) {
      return <p style={{ margin: '4px 0', lineHeight: 1.7 }}>{children}</p>;
    },
  };
}

// ── Cherry Studio 风格思考过程组件（内联版）──

function CherryThinkingSection({
  reasoning,
  defaultOpen,
  avatarColor,
}: {
  reasoning: ReasoningTrace;
  defaultOpen: boolean;
  avatarColor: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const hasToolCalls = reasoning.tool_calls && reasoning.tool_calls.length > 0;
  const hasThinking = !!reasoning.thinking_steps;
  const hasSupervisor = !!(reasoning as any).supervisor_analysis;
  const hasDecision = !!reasoning.decision_summary && !hasThinking;

  // 无内容则不渲染
  if (!hasThinking && !hasToolCalls && !hasSupervisor && !hasDecision) return null;

  // 摘要标签
  const tags: string[] = [];
  if (reasoning.model_routing?.selected_model) tags.push(reasoning.model_routing.selected_model);
  if (hasToolCalls) tags.push(`${reasoning.tool_calls!.length} 次工具调用`);
  if ((reasoning as any).latency) tags.push(`${(reasoning as any).latency}s`);

  return (
    <div style={cherryThinkContainerStyle(avatarColor)}>
      {/* 可点击折叠头 */}
      <div onClick={() => setOpen(!open)} style={cherryThinkHeaderStyle}>
        <span style={{
          display: 'inline-block',
          transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s ease',
          fontSize: 10,
          color: 'var(--text-dim)',
        }}>
          ▶
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: avatarColor }}>
          深度思考
        </span>
        {tags.length > 0 && (
          <span style={cherryThinkTagsStyle}>
            {tags.join(' · ')}
          </span>
        )}
      </div>

      {/* 展开内容 */}
      {open && (
        <div style={cherryThinkBodyStyle}>
          {/* 主管分析 */}
          {hasSupervisor && (
            <div style={thinkBlockStyle('var(--gold-400)')}>
              <div style={thinkBlockTitleStyle}>👑 主管分析</div>
              <div style={thinkBlockContentStyle}>
                {(reasoning as any).supervisor_analysis}
              </div>
            </div>
          )}

          {/* 模型思考 */}
          {hasThinking && (
            <div style={thinkBlockStyle('var(--purple-400)')}>
              <div style={thinkBlockTitleStyle}>💭 思考过程</div>
              <div style={{
                ...thinkBlockContentStyle,
                maxHeight: 320,
                overflowY: 'auto',
              }}>
                {reasoning.thinking_steps}
              </div>
            </div>
          )}

          {/* 决策摘要（无思考步骤时显示） */}
          {hasDecision && (
            <div style={thinkBlockStyle('var(--green-400)')}>
              <div style={thinkBlockTitleStyle}>✅ 处理决策</div>
              <div style={thinkBlockContentStyle}>{reasoning.decision_summary}</div>
            </div>
          )}

          {/* 工具调用 */}
          {hasToolCalls && reasoning.tool_calls!.map((tc, i) => (
            <div key={i} style={thinkBlockStyle(tc.success ? 'var(--green-400)' : 'var(--red-400)')}>
              <div style={thinkBlockTitleStyle}>
                🔧 {tc.tool} {tc.success ? '✅' : '❌'}
              </div>
              {tc.params && Object.keys(tc.params).length > 0 && (
                <pre style={thinkPreStyle}>
                  {JSON.stringify(tc.params, null, 2)}
                </pre>
              )}
              {tc.output && (
                <pre style={thinkPreStyle}>
                  {tc.output.length > 500 ? tc.output.slice(0, 500) + '...' : tc.output}
                </pre>
              )}
            </div>
          ))}

          {/* 模型信息（底部小字） */}
          {(reasoning.model_routing?.selected_model || (reasoning as any).latency) && (
            <div style={thinkModelInfoStyle}>
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
        </div>
      )}
    </div>
  );
}

// ── 主消息气泡组件 ──

export function MessageBubble({ msg, reasoning, defaultThinkingOpen = false, questions }: MessageBubbleProps) {
  const isUser = msg.agent === '我';
  const isError = msg.type === 'error';
  const isSystem = msg.type === 'system' && !isError;
  const isStreaming = (msg as { isStreaming?: boolean }).isStreaming || false;
  const avatarColor = (msg as { avatarColor?: string }).avatarColor || '#64748b';
  const isStreamMsg = msg.id.startsWith('stream_');

  // 合并 reasoning：优先用 msg.reasoning，其次用 props.reasoning
  const mergedReasoning = (msg as { reasoning?: ReasoningTrace }).reasoning || reasoning;

  // ── 系统消息 ──
  if (isSystem) {
    return (
      <div style={{ textAlign: 'center', padding: '4px 0', marginBottom: 8 }}>
        <span style={systemMsgStyle}>
          {msg.content}
        </span>
      </div>
    );
  }

  // ── 任务卡片 ──
  const taskData = (msg as {
    taskData?: {
      tasks: Array<{ id: string; seq: number; title: string; status: string; assigned_agent_name?: string }>;
      stats: { total: number; done: number; inProgress: number };
    };
  }).taskData;
  if (msg.type === 'task_card' && taskData) {
    return <TaskCardBubble msg={msg} taskData={taskData} />;
  }

  // ── 错误消息 ──
  if (isError) {
    return (
      <div style={{ textAlign: 'center', padding: '4px 0', marginBottom: 8 }}>
        <span style={errorMsgStyle}>{msg.content}</span>
      </div>
    );
  }

  // ── Agent 消息（流式 + 最终，Cherry Studio 风格）──
  const hasContent = !!msg.content;
  // 判断内容是否是状态文字（非 LLM 实际输出，而是系统设置的动作提示）
  const isStatusContent = hasContent && (
    msg.content.startsWith('🔍') ||
    msg.content.startsWith('📋') ||
    msg.content.startsWith('✅') ||
    msg.content.startsWith('🐝') ||
    msg.content.startsWith('📢')
  );

  const timeStr = new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

  return (
    <div style={{
      display: 'flex',
      gap: 10,
      flexDirection: isUser ? 'row-reverse' : 'row',
      alignItems: 'flex-start',
      marginBottom: 16,
    }}>
      {/* 头像 */}
      <div style={avatarStyle(avatarColor)}>
        {agentInitial(msg.agent)}
      </div>

      {/* 消息体 */}
      <div style={{ maxWidth: '78%', minWidth: 280 }}>
        {/* 名称 + 时间 + 状态 */}
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          color: isUser ? 'var(--text-dim)' : avatarColor,
          marginBottom: 4,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          flexDirection: isUser ? 'row-reverse' : 'row',
        }}>
          <span>{msg.agent}</span>
          {isStreaming && (
            <span style={streamingBadgeStyle(avatarColor)}>输入中...</span>
          )}
          {!isStreaming && isStreamMsg && (
            <span style={doneBadgeStyle}>已完成</span>
          )}
          <span style={{ fontWeight: 400, fontSize: 10, color: 'var(--text-dim)', opacity: 0.6 }}>
            {timeStr}
          </span>
        </div>

        {/* 问题确认区 */}
        {questions && questions.length > 0 && !isUser && (
          <div style={questionsContainerStyle(avatarColor)}>
            <div style={{ fontSize: 11, fontWeight: 600, color: avatarColor, marginBottom: 6 }}>
              🤔 请确认
            </div>
            {questions.map((q, i) => (
              <div
                key={i}
                style={questionItemStyle(i, questions.length)}
                onClick={() => {
                  const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
                  if (textarea) {
                    textarea.value = q.text;
                    textarea.focus();
                  }
                }}
              >
                ❓ {q.text}
                <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2 }}>点击回复</div>
              </div>
            ))}
          </div>
        )}

        {/* Cherry Studio 风格：思考过程（内联，消息内容上方），流式时自动展开 */}
        {!isUser && mergedReasoning && (
          <CherryThinkingSection
            reasoning={mergedReasoning}
            defaultOpen={isStreaming || (defaultThinkingOpen && !isStreamMsg)}
            avatarColor={avatarColor}
          />
        )}

        {/* 内容气泡 */}
        {hasContent && (
          <div style={contentBubbleStyle(isUser, avatarColor)}>
            {isStreaming && (
              <span style={blinkingCursorStyle(avatarColor)}> </span>
            )}
            {/* 状态文字：不用 Markdown 渲染，直接展示 */}
            {isStatusContent ? (
              <div style={statusContentStyle(avatarColor)}>{msg.content}</div>
            ) : (
              <div className="markdown-body" style={{ lineHeight: 1.7, wordBreak: 'break-word' }}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={markdownComponents()}
                >
                  {stripToolCallJson(msg.content)}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {/* 无内容时：有 reasoning 则已展示思考过程，否则显示占位 */}
        {!hasContent && isStreaming && !mergedReasoning && (
          <div style={contentBubbleStyle(false, avatarColor)}>
            <span style={thinkingDotsStyle}>思考中...</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 任务卡片子组件 ──

function TaskCardBubble({ msg, taskData }: {
  msg: AgentMsg & { avatarColor?: string };
  taskData: {
    tasks: Array<{ id: string; seq: number; title: string; status: string; assigned_agent_name?: string }>;
    stats: { total: number; done: number; inProgress: number };
  };
}) {
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'flex-start' }}>
      <div style={avatarStyle('#f59e0b')}>📋</div>
      <div style={{ maxWidth: '78%', minWidth: 280 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b', marginBottom: 3 }}>
          System
          <span style={{ fontWeight: 400, fontSize: 10, color: 'var(--text-dim)', opacity: 0.6, marginLeft: 6 }}>
            {new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <TaskCard
          tasks={taskData.tasks.map(t => ({
            id: t.id,
            seq: t.seq,
            title: t.title,
            status: t.status as 'pending' | 'claimed' | 'in_progress' | 'done' | 'blocked',
            assigned_agent_name: t.assigned_agent_name,
          }))}
          stats={taskData.stats}
          onTaskToggle={async (taskId) => {
            const task = taskData.tasks.find(t => t.id === taskId);
            if (!task) return;
            const newStatus = task.status === 'done' ? 'pending' : 'done';
            const API = (import.meta as any).env?.VITE_API_URL || '';
            const sessionId = new URLSearchParams(window.location.search).get('session') || '';
            if (!sessionId) return;
            try {
              await fetch(`${API}/api/v1/sessions/${sessionId}/tasks/${taskId}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
              });
              task.status = newStatus;
              const done = taskData.tasks.filter(t => t.status === 'done').length;
              taskData.stats.done = done;
              window.dispatchEvent(new CustomEvent('task-updated', { detail: { taskId, status: newStatus } }));
            } catch { /* ignore */ }
          }}
        />
      </div>
    </div>
  );
}

// ── 样式常量 ──

const avatarStyle = (color: string): React.CSSProperties => ({
  width: 36,
  height: 36,
  borderRadius: 8,
  background: `${color}18`,
  border: `1.5px solid ${color}44`,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 15,
  fontWeight: 700,
  color,
  flexShrink: 0,
  fontFamily: 'var(--font-body)',
});

const systemMsgStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-dim)',
  background: 'rgba(148,163,184,0.06)',
  padding: '3px 12px',
  borderRadius: 10,
};

const errorMsgStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--red-400)',
  background: 'rgba(248,113,113,0.08)',
  padding: '4px 14px',
  borderRadius: 10,
};

// ── Cherry Studio 风格样式 ──

const contentBubbleStyle = (isUser: boolean, _avatarColor: string): React.CSSProperties => ({
  borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
  padding: '12px 16px',
  fontSize: 13,
  background: isUser ? 'rgba(245,158,11,0.1)' : 'var(--bg-card)',
  border: isUser ? '1px solid rgba(245,158,11,0.25)' : '1px solid var(--border-subtle)',
  color: 'var(--text-primary)',
  lineHeight: 1.7,
  maxWidth: '100%',
  overflow: 'hidden',
  position: 'relative',
});

const blinkingCursorStyle = (color: string): React.CSSProperties => ({
  display: 'inline-block',
  width: 1,
  height: 14,
  background: color,
  marginLeft: 1,
  animation: 'blink 1s step-end infinite',
  verticalAlign: 'text-bottom',
  float: 'right',
});

const thinkingDotsStyle: React.CSSProperties = {
  color: 'var(--text-dim)',
  fontSize: 12,
  fontStyle: 'italic',
};

const streamingBadgeStyle = (color: string): React.CSSProperties => ({
  fontSize: 10,
  color: color,
  fontWeight: 400,
  animation: 'blink 1.5s step-end infinite',
});

const doneBadgeStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  fontWeight: 400,
  opacity: 0.6,
};

const statusContentStyle = (color: string): React.CSSProperties => ({
  fontSize: 12,
  color: 'var(--text-secondary)',
  lineHeight: 1.6,
  borderLeft: `3px solid ${color}55`,
  paddingLeft: 10,
});

// ── Cherry Studio 思考过程内联样式 ──

const cherryThinkContainerStyle = (color: string): React.CSSProperties => ({
  marginBottom: 8,
  borderRadius: 8,
  border: `1px solid ${color}22`,
  overflow: 'hidden',
  background: `${color}06`,
});

const cherryThinkHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '7px 10px',
  cursor: 'pointer',
  userSelect: 'none',
  transition: 'background 0.15s',
};

const cherryThinkTagsStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  marginLeft: 4,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const cherryThinkBodyStyle: React.CSSProperties = {
  padding: '6px 10px 8px',
  borderTop: '1px solid rgba(148,163,184,0.06)',
};

const thinkBlockStyle = (borderColor: string): React.CSSProperties => ({
  padding: '8px 10px',
  borderRadius: 6,
  background: 'rgba(0,0,0,0.15)',
  borderLeft: `3px solid ${borderColor}`,
  marginBottom: 6,
});

const thinkBlockTitleStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  marginBottom: 4,
};

const thinkBlockContentStyle: React.CSSProperties = {
  fontSize: 11,
  lineHeight: 1.6,
  color: 'var(--text-secondary)',
  whiteSpace: 'pre-wrap',
};

const thinkPreStyle: React.CSSProperties = {
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

const thinkModelInfoStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  padding: '4px 0 0',
  borderTop: '1px solid rgba(148,163,184,0.06)',
  marginTop: 2,
};

// ── Markdown 代码块样式 ──

const codeBlockContainerStyle: React.CSSProperties = {
  background: '#0d1117',
  borderRadius: 8,
  margin: '10px 0',
  border: '1px solid var(--border-subtle)',
  overflow: 'hidden',
};

const codeBlockHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '6px 12px',
  background: 'rgba(255,255,255,0.04)',
  borderBottom: '1px solid var(--border-subtle)',
};

const codeLangStyle: React.CSSProperties = {
  fontSize: 10,
  color: 'var(--text-dim)',
  fontFamily: 'var(--font-mono)',
  textTransform: 'uppercase',
};

const copyBtnStyle: React.CSSProperties = {
  background: 'none',
  border: '1px solid var(--border-subtle)',
  color: 'var(--text-dim)',
  borderRadius: 4,
  padding: '2px 8px',
  fontSize: 10,
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
};

const codePreStyle: React.CSSProperties = {
  margin: 0,
  padding: '12px 16px',
  overflow: 'auto',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  lineHeight: 1.5,
  color: '#e6edf3',
};

const inlineCodeStyle: React.CSSProperties = {
  background: 'rgba(148,163,184,0.12)',
  padding: '2px 6px',
  borderRadius: 4,
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
  color: 'var(--cyan-400)',
};

const tableStyle: React.CSSProperties = {
  borderCollapse: 'collapse',
  width: '100%',
  fontSize: 12,
  border: '1px solid var(--border-subtle)',
};

const thStyle: React.CSSProperties = {
  padding: '8px 12px',
  textAlign: 'left',
  fontWeight: 600,
  border: '1px solid var(--border-subtle)',
  color: 'var(--text-primary)',
};

const tdStyle: React.CSSProperties = {
  padding: '6px 12px',
  border: '1px solid var(--border-subtle)',
};

const h1Style: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  margin: '12px 0 6px',
  borderBottom: '1px solid var(--border-subtle)',
  paddingBottom: 4,
};

const h2Style: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  margin: '10px 0 6px',
};

const h3Style: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  margin: '8px 0 4px',
};

const blockquoteStyle: React.CSSProperties = {
  borderLeft: '3px solid var(--gold-400)',
  paddingLeft: 12,
  margin: '8px 0',
  color: 'var(--text-muted)',
  fontStyle: 'italic',
};

const questionsContainerStyle = (color: string): React.CSSProperties => ({
  marginBottom: 8,
  padding: '10px 12px',
  borderRadius: 8,
  background: `${color}15`,
  border: `1px solid ${color}33`,
});

const questionItemStyle = (i: number, total: number): React.CSSProperties => ({
  padding: '6px 10px',
  marginBottom: i < total - 1 ? 4 : 0,
  borderRadius: 6,
  background: 'rgba(0,0,0,0.15)',
  fontSize: 12,
  color: 'var(--text-primary)',
  cursor: 'pointer',
  border: '1px solid var(--border-subtle)',
  transition: 'all 0.15s',
});
