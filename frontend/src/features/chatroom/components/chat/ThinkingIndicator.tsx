/** 思考指示器容器：多行 ThinkingAgent，按时间顺序，支持折叠 */
import { useState, useCallback } from 'react';
import type { ThinkingAgent } from '../../types/state';
import { ThinkingRow } from './ThinkingRow';
import { ThinkingTickProvider } from './ThinkingTickProvider';

interface Props {
  agents: ThinkingAgent[];
}

/** 超过此数量自动折叠（首次渲染时折叠，用户可展开） */
const AUTO_COLLAPSE_THRESHOLD = 3;

export function ThinkingIndicator({ agents }: Props) {
  if (agents.length === 0) return null;

  const [collapsed, setCollapsed] = useState(agents.length > AUTO_COLLAPSE_THRESHOLD);
  const toggle = useCallback(() => setCollapsed(c => !c), []);

  // 按 startedAt 升序，placeholder（最先发起）置顶
  const sorted = [...agents].sort((a, b) => a.startedAt - b.startedAt);
  const activeCount = sorted.filter(a => a.status !== 'idle').length;

  return (
    <ThinkingTickProvider>
      <div style={{
        borderTop: '1px solid var(--border-subtle)',
        background: 'rgba(34, 211, 238, 0.03)',
      }}>
        {/* 折叠时显示摘要条 */}
        {collapsed ? (
          <button
            onClick={toggle}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              width: '100%', padding: '6px 12px',
              background: 'none', border: 'none',
              cursor: 'pointer', fontSize: 12,
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-body)',
            }}
          >
            <PulseDot />
            <span style={{ color: 'var(--cyan-400)', fontWeight: 500 }}>
              {activeCount} 个 Agent 工作中
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
              ({sorted.length} 个活跃)
            </span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              ▸ 展开
            </span>
          </button>
        ) : (
          <>
            {sorted.map(a => (
              <ThinkingRow key={a.agentId} agent={a} />
            ))}
            {/* 折叠按钮：多于阈值时显示 */}
            {sorted.length > AUTO_COLLAPSE_THRESHOLD && (
              <div style={{ textAlign: 'center', padding: '2px 0 4px' }}>
                <button
                  onClick={toggle}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    fontSize: 10, color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  ▾ 收起
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </ThinkingTickProvider>
  );
}

function PulseDot() {
  return (
    <span style={{
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: 'var(--cyan-400)',
      display: 'inline-block',
      animation: 'chatroom-pulse 1.4s ease-in-out infinite',
      flexShrink: 0,
    }} />
  );
}
