/** 状态点：● 实心，颜色随状态；可带 pulse 动画
 *
 * - pending / waiting → 空心灰
 * - thinking / running → 实心蓝（呼吸）
 * - done → 实心灰（已完成）
 * - paused → 实心橙
 * - failed → 实心红
 */
import type { CSSProperties } from 'react';

export type DotStatus = 'pending' | 'thinking' | 'done' | 'waiting' | 'failed' | 'paused';

interface Props {
  status: DotStatus;
  size?: number;
}

const COLOR: Record<DotStatus, string> = {
  pending: 'transparent',
  thinking: 'var(--blue-400)',
  done: 'var(--text-dim)',
  waiting: 'var(--gold-400)',
  failed: 'var(--red-400)',
  paused: 'var(--gold-400)',
};

const BORDER: Record<DotStatus, string> = {
  pending: 'var(--text-dim)',
  thinking: 'var(--blue-400)',
  done: 'var(--text-dim)',
  waiting: 'var(--gold-400)',
  failed: 'var(--red-400)',
  paused: 'var(--gold-400)',
};

export function StatusDot({ status, size = 10 }: Props) {
  const style: CSSProperties = {
    width: size,
    height: size,
    borderRadius: '50%',
    background: COLOR[status],
    border: `1px solid ${BORDER[status]}`,
    display: 'inline-block',
    flexShrink: 0,
    animation: status === 'thinking' ? 'chatroom-pulse 1.5s ease-in-out infinite' : undefined,
  };
  return <span style={style} aria-label={status} />;
}

/** 全局动画注入（只注入一次） */
let injected = false;
export function injectStatusDotAnimation() {
  if (injected || typeof document === 'undefined') return;
  injected = true;
  const style = document.createElement('style');
  style.textContent = `
    @keyframes chatroom-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.55; transform: scale(0.85); }
    }
  `;
  document.head.appendChild(style);
}
