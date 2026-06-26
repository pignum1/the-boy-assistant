/** 执行控制条：⏸ 暂停 / ⏹ 停止
 *
 * 仅在 thinking/executing/interrupting 态显示。
 * PR2 暂时只显示按钮，PR5 才真正接通后端 interrupt 协议。
 */
import type { ExecutionState } from '../../types/state';

interface Props {
  executionState: ExecutionState;
  onHardInterrupt: () => void;
}

export function ExecutionControlBar({ executionState, onHardInterrupt }: Props) {
  const active = executionState === 'thinking' || executionState === 'executing' || executionState === 'interrupting';
  if (!active) return null;
  return (
    <div style={{
      display: 'flex',
      gap: 4,
      alignItems: 'center',
    }}>
      <button
        onClick={onHardInterrupt}
        title="硬中断 (Esc)"
        style={{
          padding: '4px 10px',
          fontSize: 11,
          background: 'transparent',
          border: '1px solid var(--red-border)',
          color: 'var(--red-400)',
          borderRadius: 4,
          cursor: 'pointer',
          fontFamily: 'var(--font-mono)',
        }}
      >
        ⏹ 停止
      </button>
    </div>
  );
}
