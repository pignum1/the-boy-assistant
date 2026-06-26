/** 输入框上方提示条：告诉用户 Enter 会做什么
 *
 * 显示规则：仅在非 idle 态显示
 * 颜色：橙色（介入/HITL）或蓝色（暂停恢复）
 */
import type { ExecutionState } from '../../types/state';

interface Props {
  executionState: ExecutionState;
  isAnsweringHitl: boolean;
  onCancelAnswering?: () => void;
  onJumpToHitl?: () => void;
}

export function InputModeBanner({
  executionState,
  isAnsweringHitl,
  onCancelAnswering,
  onJumpToHitl,
}: Props) {
  // 优先级：HITL answering > HITL pending > paused > thinking/executing/interrupting > idle
  if (isAnsweringHitl) {
    return (
      <Banner color="gold">
        <span>✍️ 正在回答 Supervisor 的澄清问题</span>
        {onJumpToHitl && (
          <BannerAction onClick={onJumpToHitl}>查看 ↑</BannerAction>
        )}
        {onCancelAnswering && (
          <BannerAction onClick={onCancelAnswering}>取消</BannerAction>
        )}
      </Banner>
    );
  }

  switch (executionState) {
    case 'hitl_pending':
      return (
        <Banner color="gold">
          <span>⏸ 等你回复 — 在卡片上点按钮，或直接在下方作答</span>
        </Banner>
      );
    case 'paused':
      return (
        <Banner color="blue">
          <span>⏸ 已暂停。输入修改 + 发送，或直接 "继续" 恢复</span>
        </Banner>
      );
    case 'thinking':
    case 'executing':
    case 'interrupting':
      return (
        <Banner color="gold">
          <span>💡 执行中，你的消息将作为修改建议（软介入）</span>
        </Banner>
      );
    case 'idle':
    default:
      return null;
  }
}

function Banner({
  color, children,
}: {
  color: 'gold' | 'blue';
  children: React.ReactNode;
}) {
  const bg = color === 'gold' ? 'var(--gold-bg)' : 'var(--blue-bg)';
  const border = color === 'gold' ? 'var(--gold-border)' : 'var(--blue-border)';
  const text = color === 'gold' ? 'var(--gold-400)' : 'var(--blue-400)';
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '6px 14px',
      background: bg,
      borderTop: `1px solid ${border}`,
      color: text,
      fontSize: 11,
      fontFamily: 'var(--font-mono)',
    }}>
      {children}
    </div>
  );
}

function BannerAction({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        marginLeft: 'auto',
        background: 'transparent',
        border: '1px solid currentColor',
        color: 'inherit',
        padding: '2px 8px',
        borderRadius: 3,
        fontSize: 10,
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {children}
    </button>
  );
}
