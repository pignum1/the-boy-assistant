/** ChatInput 测试：按钮文案随状态变 + Esc 三档行为 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInput } from '../ChatInput';

describe('ChatInput · 按钮文案', () => {
  it('idle → "发送"', () => {
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    expect(screen.getByRole('button')).toHaveTextContent('发送');
  });

  it('thinking → "💡 介入"', () => {
    render(
      <ChatInput
        executionState="thinking"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    expect(screen.getByRole('button')).toHaveTextContent('💡 介入');
  });

  it('answeringHitl=true → "回复"', () => {
    render(
      <ChatInput
        executionState="hitl_pending"
        isAnsweringHitl={true}
        onSubmit={() => {}}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    expect(screen.getByRole('button')).toHaveTextContent('回复');
  });

  it('paused → "继续"', () => {
    render(
      <ChatInput
        executionState="paused"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    expect(screen.getByRole('button')).toHaveTextContent('继续');
  });
});

describe('ChatInput · Esc 三档行为', () => {
  it('有文本 → Esc 清空', () => {
    const onSubmit = vi.fn();
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={onSubmit}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    const ta = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: '一些文字' } });
    expect(ta.value).toBe('一些文字');
    fireEvent.keyDown(ta, { key: 'Escape' });
    expect(ta.value).toBe('');
  });

  it('空文本 + answering → Esc onCancelAnswering', () => {
    const onCancel = vi.fn();
    const onHard = vi.fn();
    render(
      <ChatInput
        executionState="hitl_pending"
        isAnsweringHitl={true}
        onSubmit={() => {}}
        onCancelAnswering={onCancel}
        onHardInterrupt={onHard}
      />
    );
    const ta = screen.getByRole('textbox');
    fireEvent.keyDown(ta, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onHard).not.toHaveBeenCalled();
  });

  it('空文本 + thinking → Esc onHardInterrupt', () => {
    const onCancel = vi.fn();
    const onHard = vi.fn();
    render(
      <ChatInput
        executionState="thinking"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={onCancel}
        onHardInterrupt={onHard}
      />
    );
    const ta = screen.getByRole('textbox');
    fireEvent.keyDown(ta, { key: 'Escape' });
    expect(onHard).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('空文本 + idle → Esc 无效', () => {
    const onCancel = vi.fn();
    const onHard = vi.fn();
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={onCancel}
        onHardInterrupt={onHard}
      />
    );
    const ta = screen.getByRole('textbox');
    fireEvent.keyDown(ta, { key: 'Escape' });
    expect(onCancel).not.toHaveBeenCalled();
    expect(onHard).not.toHaveBeenCalled();
  });
});

describe('ChatInput · Enter 提交', () => {
  it('Enter 发送并清空', () => {
    const onSubmit = vi.fn();
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={onSubmit}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    const ta = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'hello' } });
    fireEvent.keyDown(ta, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledWith('hello');
    expect(ta.value).toBe('');
  });

  it('Shift+Enter 不提交', () => {
    const onSubmit = vi.fn();
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={onSubmit}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    const ta = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: 'line1' } });
    fireEvent.keyDown(ta, { key: 'Enter', shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('空文本时按钮禁用', () => {
    render(
      <ChatInput
        executionState="idle"
        isAnsweringHitl={false}
        onSubmit={() => {}}
        onCancelAnswering={() => {}}
        onHardInterrupt={() => {}}
      />
    );
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
  });
});
