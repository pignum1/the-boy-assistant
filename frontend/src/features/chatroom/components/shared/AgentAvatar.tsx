/** Agent 头像：emoji + 角色色背景 */
import type { CSSProperties } from 'react';

interface Props {
  emoji: string;
  name: string;
  size?: number;
}

/** 角色名 → 颜色（hash） */
const PALETTE = [
  '#fbbf24', '#38bdf8', '#a78bfa', '#34d399',
  '#f87171', '#22d3ee', '#ec4899', '#f97316',
];

function colorOf(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) {
    h = name.charCodeAt(i) + ((h << 5) - h);
  }
  return PALETTE[Math.abs(h) % PALETTE.length];
}

export function AgentAvatar({ emoji, name, size = 28 }: Props) {
  const color = colorOf(name);
  const style: CSSProperties = {
    width: size,
    height: size,
    borderRadius: '50%',
    background: `${color}22`,
    border: `1px solid ${color}44`,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: Math.floor(size * 0.55),
    flexShrink: 0,
  };
  return (
    <span style={style} title={name}>
      {emoji}
    </span>
  );
}
