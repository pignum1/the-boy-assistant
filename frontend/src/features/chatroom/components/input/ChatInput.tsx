/** 聊天输入框：永不禁用，按钮文案随状态变
 *
 * Enter 行为派遣给 onSubmit，调用方根据状态决定走哪条路径：
 *   - idle → sendChat
 *   - answering HITL → sendHitlResume
 *   - thinking/executing/interrupting → sendInterrupt('soft')
 *   - paused → sendResume
 *   - hitl_pending(无 answering) → sendHitlResume（视为用户主动用文本作答）
 *
 * Esc 三档：
 *   - 有文本 → 清空
 *   - 空文本 + answering → onCancelAnswering
 *   - 空文本 + thinking/executing/interrupting → onHardInterrupt
 */
import { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import type { ExecutionState } from '../../types/state';

interface Props {
  /** 当前执行状态（决定按钮文案 + 颜色） */
  executionState: ExecutionState;
  /** 是否处于 HITL answering 状态 */
  isAnsweringHitl: boolean;
  /** 用户点击发送/Enter */
  onSubmit: (text: string) => void;
  /** Esc 在 answering 时调用 */
  onCancelAnswering: () => void;
  /** Esc 在执行中调用 */
  onHardInterrupt: () => void;
}

export interface ChatInputHandle {
  focus: () => void;
}

export const ChatInput = forwardRef<ChatInputHandle, Props>(function ChatInput(
  { executionState, isAnsweringHitl, onSubmit, onCancelAnswering, onHardInterrupt }: Props,
  ref,
) {
  const [text, setText] = useState('');
  const taRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => taRef.current?.focus(),
  }), []);

  // answering 切换时自动 focus
  useEffect(() => {
    if (isAnsweringHitl) {
      taRef.current?.focus();
    }
  }, [isAnsweringHitl]);

  const { label, color } = computeButtonStyle(executionState, isAnsweringHitl);
  const placeholder = computePlaceholder(executionState, isAnsweringHitl);

  function handleSubmit() {
    const t = text.trim();
    if (!t) return;
    onSubmit(t);
    setText('');
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSubmit();
      return;
    }
    if (e.key === 'Escape') {
      if (text.length > 0) {
        e.preventDefault();
        setText('');
        return;
      }
      if (isAnsweringHitl) {
        e.preventDefault();
        onCancelAnswering();
        return;
      }
      if (executionState === 'thinking' || executionState === 'executing' || executionState === 'interrupting') {
        e.preventDefault();
        onHardInterrupt();
        return;
      }
    }
  }

  // 自适应高度
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const next = Math.min(140, ta.scrollHeight);
    ta.style.height = `${next}px`;
  }, [text]);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-end',
      gap: 8,
      padding: '12px 18px',
      borderTop: '1px solid var(--border)',
      background: 'var(--bg)',
    }}>
      <textarea
        ref={taRef}
        value={text}
        placeholder={placeholder}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        style={{
          flex: 1,
          padding: '10px 14px',
          background: 'var(--bg)',
          color: 'var(--text)',
          border: '1px solid var(--border-strong)',
          borderRadius: 10,
          fontSize: 13,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          lineHeight: 1.5,
          resize: 'none',
          outline: 'none',
          minHeight: 40,
          maxHeight: 140,
        }}
      />
      <button
        onClick={handleSubmit}
        disabled={text.trim().length === 0}
        style={{
          padding: '8px 16px',
          borderRadius: 8,
          border: 'none',
          background: text.trim().length === 0 ? 'var(--bg-bubble)' : 'var(--primary)',
          color: text.trim().length === 0 ? 'var(--text-mute)' : '#fff',
          fontSize: 12.5,
          fontWeight: 600,
          cursor: text.trim().length === 0 ? 'not-allowed' : 'pointer',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
          minWidth: 64,
          height: 40,
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </button>
    </div>
  );
});

function computeButtonStyle(
  state: ExecutionState,
  isAnsweringHitl: boolean,
): { label: string; color: 'blue' | 'orange' } {
  if (isAnsweringHitl) return { label: '回复', color: 'orange' };
  switch (state) {
    case 'thinking':
    case 'executing':
    case 'interrupting':
      return { label: '💡 介入', color: 'orange' };
    case 'paused':
      return { label: '继续', color: 'blue' };
    case 'hitl_pending':
      return { label: '回复', color: 'orange' };
    case 'idle':
    default:
      return { label: '发送', color: 'blue' };
  }
}

function computePlaceholder(state: ExecutionState, isAnsweringHitl: boolean): string {
  if (isAnsweringHitl) return '回答 Supervisor 的问题... (Enter 发送, Esc 取消)';
  switch (state) {
    case 'thinking':
    case 'executing':
      return '需要调整？输入修改建议... (软介入)';
    case 'interrupting':
      return '正在处理介入，请稍候，或继续补充...';
    case 'paused':
      return '已暂停。输入修改或发送 "继续" 恢复...';
    case 'hitl_pending':
      return '回复 / 输入回答...';
    case 'idle':
    default:
      return '输入消息... (Enter 发送, Shift+Enter 换行)';
  }
}
