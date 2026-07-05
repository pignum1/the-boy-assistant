/**
 * MetricsBar — 聊天顶栏实时指标条 + 监控入口
 *
 * 四项指标：⏱ 耗时 · 🔤 Token · 💰 成本 · 🤖 活跃 Agent
 * 末尾整合 📊 监控 → 跳转到 LangFuse 查看当前会话 trace
 */

import React, { useEffect, useState } from 'react';
import type { ThinkingAgent } from '../../types/state';

interface Props {
  thinkingAgents: ThinkingAgent[];
  teamCount: number;
  sessionId: string;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.floor(s % 60);
  return `${m}m ${rs}s`;
}

function computeElapsed(agents: ThinkingAgent[]): number {
  const starts = agents.filter(a => a.startedAt > 0).map(a => a.startedAt);
  if (starts.length === 0) return 0;
  return Date.now() - Math.min(...starts);
}

export const MetricsBar: React.FC<Props> = ({ thinkingAgents, teamCount, sessionId }) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const tick = () => setElapsed(computeElapsed(thinkingAgents));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [thinkingAgents]);

  const activeCount = thinkingAgents.filter(a => a.status === 'thinking').length;
  const isRunning = activeCount > 0;

  const smallText: React.CSSProperties = { fontSize: 12, color: 'var(--text-secondary)' };
  const dimSep: React.CSSProperties = { color: 'var(--text-tertiary)' };

  const langfuseUrl = (import.meta as any).env?.VITE_LANGFUSE_URL || 'http://localhost:3000';

  return (
    <div
      style={{
        height: 28,
        padding: '0 18px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-soft)',
        fontSize: 12,
        flexShrink: 0,
        overflowX: 'auto',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={smallText}>
        ⏱ 耗时{' '}
        <span style={{ color: isRunning ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: 600 }}>
          {formatDuration(elapsed)}
        </span>
      </span>
      <span style={dimSep}>·</span>
      <span style={smallText}>
        🔤 Token{' '}
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
          {isRunning ? '—' : '—'}
        </span>
      </span>
      <span style={dimSep}>·</span>
      <span style={smallText}>
        💰 成本{' '}
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
          {isRunning ? '—' : '—'}
        </span>
      </span>
      <span style={dimSep}>·</span>
      <span style={smallText}>
        🤖 活跃{' '}
        <span style={{ color: activeCount > 0 ? 'var(--success, #22c55e)' : 'var(--text-primary)', fontWeight: 600 }}>
          {activeCount}
        </span>
        {' '}/ {teamCount} 工作中
      </span>
      <span style={{ flex: 1 }} />
      <a
        href={`${langfuseUrl}`}
        target="_blank"
        rel="noopener noreferrer"
        title="在 LangFuse 中查看当前会话完整调用链"
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          fontSize: 11, color: 'var(--text-muted)', textDecoration: 'none',
          fontFamily: 'var(--font-mono)',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--cyan-400)'; }}
        onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; }}
      >
        📊 监控 →
      </a>
    </div>
  );
};
