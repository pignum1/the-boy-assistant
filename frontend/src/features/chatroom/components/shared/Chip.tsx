/** Chip：统一徽章组件。多种 variant 对应不同色调
 *
 * - phase（维度 A 系统阶段）→ 紫色，📊 前缀
 * - task（维度 B 业务任务）→ 青色，📋 前缀
 * - model → 灰色，🧠 前缀
 * - latency → 灰色，⏱ 前缀
 * - status → 颜色按状态
 */
import type { CSSProperties, ReactNode } from 'react';

export type ChipVariant = 'phase' | 'task' | 'model' | 'latency' | 'neutral' | 'warning' | 'success' | 'danger';

interface Props {
  variant: ChipVariant;
  icon?: string;
  children: ReactNode;
  /** 鼠标悬浮提示 */
  title?: string;
}

const VARIANT_STYLES: Record<ChipVariant, CSSProperties> = {
  phase: {
    background: 'var(--purple-bg)',
    color: 'var(--purple-400)',
    border: '1px solid var(--purple-border)',
  },
  task: {
    background: 'var(--cyan-bg)',
    color: 'var(--cyan-400)',
    border: '1px solid var(--cyan-border)',
  },
  model: {
    background: 'rgba(148,163,184,0.06)',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-medium)',
  },
  latency: {
    background: 'rgba(148,163,184,0.06)',
    color: 'var(--text-muted)',
    border: '1px solid var(--border-subtle)',
  },
  neutral: {
    background: 'rgba(148,163,184,0.06)',
    color: 'var(--text-muted)',
    border: '1px solid var(--border-subtle)',
  },
  warning: {
    background: 'var(--gold-bg)',
    color: 'var(--gold-400)',
    border: '1px solid var(--gold-border)',
  },
  success: {
    background: 'var(--green-bg)',
    color: 'var(--green-400)',
    border: '1px solid var(--green-border)',
  },
  danger: {
    background: 'var(--red-bg)',
    color: 'var(--red-400)',
    border: '1px solid var(--red-border)',
  },
};

export function Chip({ variant, icon, children, title }: Props) {
  const base: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '2px 8px',
    fontSize: 10,
    borderRadius: 4,
    fontFamily: 'var(--font-mono)',
    lineHeight: 1.4,
    whiteSpace: 'nowrap',
    ...VARIANT_STYLES[variant],
  };
  return (
    <span style={base} title={title}>
      {icon && <span>{icon}</span>}
      <span>{children}</span>
    </span>
  );
}
