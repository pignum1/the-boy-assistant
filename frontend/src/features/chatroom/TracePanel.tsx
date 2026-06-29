/** 上下文详情面板：实时 trace + 持久化上下文数据 */
import { useRef, useEffect, useState } from 'react';
import type { TraceEntry } from '../../shared/types/session';

interface TracePanelProps {
  traceEntries: TraceEntry[];
  sessionId: string;
}

const TYPES: Record<string, string> = {
  thinking: '思考', reasoning: '推理', tool_call: '工具调用', agent_status: '状态',
  message_complete: '完成', storage: '存储', dispatch: '消息',
};

const TRACE_COLORS: Record<string, string> = {
  thinking: '#f59e0b', reasoning: '#3b82f6', tool_call: '#10b981',
  agent_status: '#8b5cf6', message_complete: '#64748b', storage: '#06b6d4', dispatch: '#14b8a6',
};
const TRACE_ICONS: Record<string, string> = {
  thinking: '💭', reasoning: '🧠', tool_call: '🔧',
  agent_status: '🟡', message_complete: '✅', storage: '💾', dispatch: '📨',
};

interface ContextData {
  session?: { id: string; title: string; mode: string; status: string };
  stats?: {
    message_count: number; memory_count: number;
    total_tokens_estimate: number; total_memories_injected: number;
    total_rag_chunks: number; total_tool_calls: number;
  };
  system_prompts?: Array<{ agent_name: string; role_name: string }>;
  messages?: Array<{
    id: string; role: string; content: string;
    agent_name?: string; timestamp: string;
    metadata?: Record<string, unknown>;
  }>;
}

const API_BASE = (import.meta as unknown as { env: Record<string, string> }).env?.VITE_API_URL || '';

function msgToTraceEntry(msg: ContextData['messages'] extends Array<infer T> ? T : never): TraceEntry | null {
  const meta = (msg as { metadata?: Record<string, unknown> }).metadata || {};
  const agent = (msg as { agent_name?: string }).agent_name || 'System';
  const ts = (msg as { timestamp: string }).timestamp || '';

  if ((msg as { role: string }).role === 'user') {
    const content = String((msg as { content: string }).content || '').slice(0, 80);
    return {
      id: `hist_${(msg as { id: string }).id}`,
      type: 'dispatch', agent: '我', timestamp: ts,
      summary: content, icon: '📨', color: TRACE_COLORS.dispatch,
    };
  }

  // Check for tool calls in metadata
  const toolCalls = meta.tool_calls as Array<Record<string, unknown>> | undefined;
  if (toolCalls && toolCalls.length > 0) {
    const tc = toolCalls[0];
    return {
      id: `hist_tc_${(msg as { id: string }).id}`,
      type: 'tool_call', agent, timestamp: ts,
      summary: `🔧 ${tc.tool || 'tool'} → ${tc.success ? '✅' : '❌'}`,
      icon: '🔧', color: TRACE_COLORS.tool_call,
      data: { tool: tc.tool, success: tc.success, output: tc.output },
    };
  }

  // Default: reasoning entry
  const content = String((msg as { content: string }).content || '').slice(0, 100);
  return {
    id: `hist_${(msg as { id: string }).id}`,
    type: 'reasoning', agent, timestamp: ts,
    summary: content, icon: '🧠', color: TRACE_COLORS.reasoning,
    data: meta,
  };
}

export function TracePanel({ traceEntries, sessionId }: TracePanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showModal, setShowModal] = useState(false);
  const [contextData, setContextData] = useState<ContextData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const fetchContext = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/context?limit=200`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          setContextData(data);
        }
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    };
    fetchContext();
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [traceEntries.length]);
  const tm = (ts: string) => { try { return new Date(ts).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' }); } catch { return ts?.slice(11,19) || ''; } };

  const stats = contextData?.stats;
  const prompts = contextData?.system_prompts || [];

  // Build history trace entries from persisted messages
  const historyEntries: TraceEntry[] = (contextData?.messages || [])
    .map(msgToTraceEntry)
    .filter(Boolean) as TraceEntry[];

  // Merge: live entries override history entries with same "id" prefix
  const liveIds = new Set(traceEntries.map(e => e.id));
  const mergedEntries = [
    ...historyEntries.filter(e => !liveIds.has(e.id)),
    ...traceEntries,
  ];

  const allEntries = mergedEntries.length > 0 ? mergedEntries : traceEntries;

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>📋 上下文详情</span>
        <button onClick={() => setShowModal(true)} style={{ fontSize: 10, padding: '3px 12px', borderRadius: 4, border: '1px solid var(--gold-400)', background: 'var(--gold-bg)', color: 'var(--gold-400)', cursor: 'pointer', fontWeight: 500 }}>
          查看全部 ({allEntries.length} 条)
        </button>
      </div>

      {/* ── Persisted context stats ── */}
      {stats && (
        <div style={{ marginBottom: 12, padding: '8px 10px', borderRadius: 6, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 6 }}>📊 会话统计</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: 10 }}>
            <Row label="消息数" value={String(stats.message_count)} />
            <Row label="记忆数" value={String(stats.memory_count)} />
            <Row label="Token 估算" value={stats.total_tokens_estimate > 0 ? `${stats.total_tokens_estimate}` : '-'} />
            <Row label="记忆注入" value={String(stats.total_memories_injected)} />
            <Row label="RAG 块" value={String(stats.total_rag_chunks)} />
            <Row label="工具调用" value={String(stats.total_tool_calls)} />
          </div>
        </div>
      )}

      {/* ── System prompts ── */}
      {prompts.length > 0 && (
        <div style={{ marginBottom: 12, padding: '8px 10px', borderRadius: 6, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 6 }}>🤖 系统提示词 ({prompts.length})</div>
          {prompts.map((p, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 2 }}>
              <span style={{ color: 'var(--gold-400)', fontWeight: 500 }}>{p.role_name}</span>
              <span style={{ marginLeft: 4 }}>{p.agent_name}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Trace entries (live + history) ── */}
      {allEntries.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
          {loading ? (
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>加载中...</span>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>等待会话开始...</span>
          )}
        </div>
      ) : (
        <div style={{ position: 'relative', paddingLeft: 16 }}>
          <div style={{ position: 'absolute', left: 5, top: 4, bottom: 4, width: 2, background: 'var(--border-subtle)', borderRadius: 1 }} />
          {allEntries.map((entry) => (
            <div key={entry.id} style={{ marginBottom: 5, position: 'relative' }}>
              <div style={{ position: 'absolute', left: -13, top: 5, width: 10, height: 10, borderRadius: '50%', background: entry.color, border: '2px solid var(--bg-base)', fontSize: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}>{entry.icon}</div>
              <div style={{ padding: '4px 8px', borderRadius: 4, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: entry.color }}>{entry.agent}</span>
                <span style={{ fontSize: 8.5, color: 'var(--text-dim)', marginLeft: 6 }}>{tm(entry.timestamp)}</span>
                <span style={{ fontSize: 8, padding: '1px 4px', borderRadius: 2, background: `${entry.color}22`, color: entry.color, marginLeft: 6 }}>{TYPES[entry.type] || entry.type}</span>
                <span style={{ fontSize: 9.5, color: 'var(--text-secondary)', marginLeft: 6 }}>{entry.summary}</span>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {showModal && <AllModal entries={allEntries} contextData={contextData} onClose={() => setShowModal(false)} />}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-dim)' }}>{label}</span>
      <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function AllModal({ entries, contextData, onClose }: { entries: TraceEntry[]; contextData: ContextData | null; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 12, width: '94%', maxWidth: 860, height: '90vh', display: 'flex', flexDirection: 'column', boxShadow: '0 16px 64px rgba(0,0,0,0.6)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)', flexShrink: 0 }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>📋 上下文详情 ({entries.length} 条记录)</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 22, padding: '2px 6px' }}>✕</button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
          {contextData?.stats && (
            <div style={{ marginBottom: 16, padding: '12px 14px', borderRadius: 8, background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderLeft: '3px solid var(--gold-400)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>📊 会话统计</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', fontSize: 10 }}>
                <span style={{ color: 'var(--text-dim)' }}>消息数: {contextData.stats.message_count}</span>
                <span style={{ color: 'var(--text-dim)' }}>记忆数: {contextData.stats.memory_count}</span>
                <span style={{ color: 'var(--text-dim)' }}>Token 估算: {contextData.stats.total_tokens_estimate || '-'}</span>
                <span style={{ color: 'var(--text-dim)' }}>工具调用: {contextData.stats.total_tool_calls}</span>
              </div>
            </div>
          )}
          {entries.map((entry) => {
            const d = (entry.data || {}) as Record<string, unknown>;
            const tFull = (ts: string) => { try { return new Date(ts).toLocaleString('zh-CN'); } catch { return ts || ''; } };
            return (
              <div key={entry.id} style={{ marginBottom: 16, padding: '12px 14px', borderRadius: 8, background: 'var(--bg-elevated)', border: `1px solid var(--border-subtle)`, borderLeft: `3px solid ${entry.color}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: entry.color }}>{entry.icon} {entry.agent}</span>
                  <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 3, background: `${entry.color}22`, color: entry.color }}>{TYPES[entry.type] || entry.type}</span>
                  <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 'auto' }}>{tFull(entry.timestamp)}</span>
                </div>
                <table style={{ width: '100%', fontSize: 10, borderCollapse: 'collapse', marginBottom: 4 }}>
                  <tbody>
                    {d.model && <R label="模型" value={`${d.model}${d.provider ? ' (' + d.provider + ')' : ''}`} />}
                    {d.latency != null && <R label="耗时" value={`${d.latency}s`} />}
                    {d.status && <R label="状态" value={String(d.status)} />}
                    {entry.type === 'tool_call' && <R label="工具" value={String(d.tool || '')} />}
                    {entry.type === 'tool_call' && <R label="结果" value={d.success ? '✅ 成功' : '❌ 失败'} />}
                    {d.memory_id && <R label="存储" value={`${String(d.memory_id).slice(0, 16)}...`} />}
                    <R label="摘要" value={entry.summary} />
                  </tbody>
                </table>
                {d.output && <S label="回复内容" text={String(d.output)} />}
                {entry.detail && !d.output && entry.type !== 'tool_call' && <S label="内容" text={entry.detail} />}
                {d.thinking_steps && <S label="思考过程" text={String(d.thinking_steps)} />}
                {d.input && <S label="输入" text={String(d.input)} />}
                {entry.type === 'tool_call' && d.params && <S label="参数" text={typeof d.params === 'string' ? d.params : JSON.stringify(d.params, null, 2)} />}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function R({ label, value }: { label: string; value: string }) {
  return <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}><td style={{ padding: '3px 8px 3px 0', color: 'var(--text-dim)', whiteSpace: 'nowrap', verticalAlign: 'top', width: 60 }}>{label}</td><td style={{ padding: '3px 0', color: 'var(--text-primary)', wordBreak: 'break-all' }}>{value}</td></tr>;
}

function S({ label, text }: { label: string; text: string }) {
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 9.5, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 3 }}>{label}</div>
      <pre style={{ fontSize: 9.5, fontFamily: 'var(--font-mono)', margin: 0, padding: '8px 10px', background: 'rgba(0,0,0,0.2)', borderRadius: 5, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.6, maxHeight: 300, overflow: 'auto' }}>{text}</pre>
    </div>
  );
}
