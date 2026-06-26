/** Meta phase row · 系统阶段进度（M0~M7 圆点 + 连线）
 *
 * 状态可视：
 *   - pending：空心灰
 *   - thinking：实心蓝（呼吸光）
 *   - waiting：实心橙（HITL）
 *   - done：实心灰
 *   - skipped：极淡灰（单 Agent 路径会跳过 M1~M7）
 *   - failed：实心红
 *
 * 交互：圆点点击 → onJumpToPhase(phaseId)，调用方滚动到对应消息。
 * hover 显示 tooltip（阶段名 + summary + 当前 agent）。
 */
import { useState } from 'react';
import type { CSSProperties } from 'react';
import type { MetaPhaseId, MetaPhaseState } from '../../types/state';

interface Props {
  phases: MetaPhaseState[];
  currentPhaseId: MetaPhaseId | null;
  onJumpToPhase: (phaseId: MetaPhaseId) => void;
}

export function MetaPhaseRow({ phases, currentPhaseId, onJumpToPhase }: Props) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      padding: '4px 0',
    }}>
      <span style={labelStyle}>系统</span>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        flex: 1,
      }}>
        {phases.map((p, i) => (
          <PhaseNode
            key={p.id}
            phase={p}
            isFirst={i === 0}
            isCurrent={p.id === currentPhaseId}
            onJump={() => onJumpToPhase(p.id)}
          />
        ))}
      </div>
    </div>
  );
}

function PhaseNode({
  phase, isFirst, isCurrent, onJump,
}: {
  phase: MetaPhaseState;
  isFirst: boolean;
  isCurrent: boolean;
  onJump: () => void;
}) {
  const [hover, setHover] = useState(false);

  const { dot, line } = colorOf(phase.status, isCurrent);

  const tooltipText = formatTooltip(phase);

  return (
    <div style={{ display: 'flex', alignItems: 'center', flex: isFirst ? 0 : 1 }}>
      {!isFirst && (
        <span style={{
          flex: 1,
          height: 1,
          background: line,
          minWidth: 12,
        }} />
      )}
      <div
        style={{ position: 'relative' }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        <button
          onClick={onJump}
          aria-label={tooltipText}
          style={{
            width: 14,
            height: 14,
            padding: 0,
            border: `1.5px solid ${dot.border}`,
            background: dot.fill,
            borderRadius: '50%',
            cursor: 'pointer',
            display: 'block',
            animation: phase.status === 'thinking'
              ? 'chatroom-pulse 1.4s ease-in-out infinite'
              : undefined,
            transition: 'transform 0.15s',
            transform: hover ? 'scale(1.2)' : 'scale(1)',
          }}
        />
        {hover && (
          <Tooltip text={tooltipText} />
        )}
      </div>
      <span style={{
        fontSize: 9,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        marginLeft: 4,
        whiteSpace: 'nowrap',
      }}>
        {phase.shortLabel}
      </span>
    </div>
  );
}

function Tooltip({ text }: { text: string }) {
  return (
    <div style={{
      position: 'absolute',
      top: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      marginTop: 8,
      padding: '4px 8px',
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border-medium)',
      borderRadius: 4,
      fontSize: 10,
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-mono)',
      whiteSpace: 'nowrap',
      zIndex: 50,
      boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
      pointerEvents: 'none',
    }}>
      {text}
    </div>
  );
}

function colorOf(status: MetaPhaseState['status'], isCurrent: boolean): {
  dot: { fill: string; border: string };
  line: string;
} {
  switch (status) {
    case 'thinking':
      return {
        dot: { fill: 'var(--blue-400)', border: 'var(--blue-400)' },
        line: 'var(--border-medium)',
      };
    case 'waiting':
      return {
        dot: { fill: 'var(--gold-400)', border: 'var(--gold-400)' },
        line: 'var(--border-medium)',
      };
    case 'done':
      return {
        dot: { fill: 'var(--text-dim)', border: 'var(--text-dim)' },
        line: 'var(--text-dim)',
      };
    case 'failed':
      return {
        dot: { fill: 'var(--red-400)', border: 'var(--red-400)' },
        line: 'var(--border-medium)',
      };
    case 'skipped':
      return {
        dot: { fill: 'transparent', border: 'rgba(148,163,184,0.15)' },
        line: 'rgba(148,163,184,0.08)',
      };
    case 'pending':
    default:
      return {
        dot: { fill: 'transparent', border: isCurrent ? 'var(--blue-400)' : 'var(--text-dim)' },
        line: 'var(--border-subtle)',
      };
  }
}

function formatTooltip(p: MetaPhaseState): string {
  const status = STATUS_TEXT[p.status];
  const summary = p.summary ? ` · ${p.summary}` : '';
  const agent = p.currentAgent ? ` · ${p.currentAgent}` : '';
  return `${p.label} (${status})${summary}${agent}`;
}

const STATUS_TEXT: Record<MetaPhaseState['status'], string> = {
  pending: '未开始',
  thinking: '进行中',
  waiting: '等用户',
  done: '已完成',
  skipped: '跳过',
  failed: '失败',
};

const labelStyle: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-muted)',
  fontFamily: 'var(--font-mono)',
  marginRight: 10,
  minWidth: 30,
};
