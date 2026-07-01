/** 右侧抽屉切换按钮：📋 📁 👥
 *
 * 点击同一图标会关闭。互斥逻辑在 DrawerHost / reducer 中。
 */
import type { CSSProperties } from 'react';
import type { DrawerKind } from '../../types/state';

interface Props {
  openDrawers: import('../../types/state').DrawerState[];
  onToggle: (drawer: DrawerKind) => void;
  /** 业务任务计数（显示徽标） */
  taskCount?: { done: number; total: number };
  /** 产物数 */
  artifactCount?: number;
  /** 团队 agent 数 */
  teamCount?: number;
  /** 工作空间完整路径 */
  workspacePath?: string;
}

export function DrawerToggleButtons({
  openDrawers,
  onToggle,
  taskCount,
  artifactCount,
  teamCount,
  workspacePath,
}: Props) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      <ToggleBtn
        active={openDrawers.some(d => d.kind === 'plan')}
        emoji="📋"
        label="任务"
        badge={taskCount && taskCount.total > 0 ? `${taskCount.done}/${taskCount.total}` : undefined}
        onClick={() => onToggle('plan')}
      />
      <ToggleBtn
        active={openDrawers.some(d => d.kind === 'artifacts')}
        emoji="📁"
        label="产物"
        badge={artifactCount ? String(artifactCount) : undefined}
        title={workspacePath || '工作空间产物'}
        onClick={() => onToggle('artifacts')}
      />
      <ToggleBtn
        active={openDrawers.some(d => d.kind === 'team')}
        emoji="👥"
        label="团队"
        badge={teamCount ? String(teamCount) : undefined}
        onClick={() => onToggle('team')}
      />
      <ToggleBtn
        active={openDrawers.some(d => d.kind === 'workflow')}
        emoji="🔀"
        label="流程"
        badge={taskCount && taskCount.total > 0 ? `${taskCount.done}/${taskCount.total}` : undefined}
        onClick={() => onToggle('workflow')}
      />
      <LangfuseLinkBtn />
    </div>
  );
}

function LangfuseLinkBtn() {
  const url = (import.meta as any).env?.VITE_LANGFUSE_URL || 'http://localhost:3000';
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="LangFuse 可观测性 Dashboard"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '4px 10px', fontSize: 11,
        background: 'transparent',
        border: '1px solid var(--border-subtle)',
        color: 'var(--text-secondary)',
        borderRadius: 4, cursor: 'pointer',
        fontFamily: 'var(--font-mono)', height: 28,
        textDecoration: 'none',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--cyan-bg)'; e.currentTarget.style.color = 'var(--cyan-400)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
    >
      <span style={{ fontSize: 12 }}>📊</span>
      <span>监控</span>
    </a>
  );
}

function ToggleBtn({
  active, emoji, label, badge, title, onClick,
}: {
  active: boolean;
  emoji: string;
  label: string;
  badge?: string;
  title?: string;
  onClick: () => void;
}) {
  const style: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '4px 10px',
    fontSize: 11,
    background: active ? 'var(--cyan-bg)' : 'transparent',
    border: `1px solid ${active ? 'var(--cyan-border)' : 'var(--border-subtle)'}`,
    color: active ? 'var(--cyan-400)' : 'var(--text-secondary)',
    borderRadius: 4,
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    height: 28,
  };
  return (
    <button onClick={onClick} style={style} title={title || label}>
      <span style={{ fontSize: 12 }}>{emoji}</span>
      <span>{label}</span>
      {badge && (
        <span style={{
          fontSize: 9,
          padding: '0 5px',
          borderRadius: 2,
          background: active ? 'var(--cyan-400)' : 'rgba(148,163,184,0.15)',
          color: active ? '#0a0f1e' : 'var(--text-secondary)',
          marginLeft: 2,
        }}>
          {badge}
        </span>
      )}
    </button>
  );
}
