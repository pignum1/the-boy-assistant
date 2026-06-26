/** HITLCard 测试：确保状态机 + 按钮分流正确
 *
 * 关键回归：「我来回答」按钮不能 onPrimaryAction，否则会把 "answer" 当聊天发出去
 * （这是 PR2 之前的核心 bug）
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HITLCard } from '../HITLCard';
import type { HitlCardItem } from '../../../types/state';

function makeItem(overrides: Partial<HitlCardItem> = {}): HitlCardItem {
  return {
    id: 'item-1',
    kind: 'hitl_card',
    hitlId: 'hitl-1',
    cardState: 'pending',
    hitlKind: 'clarification',
    message: '需要确认目标用户',
    options: [
      { label: '我来回答', value: 'answer' },
      { label: '取消', value: 'skip' },
    ],
    timestamp: 1000,
    ...overrides,
  };
}

describe('HITLCard', () => {
  it('renders pending state with options', () => {
    render(
      <HITLCard
        item={makeItem()}
        onPrimaryAction={() => {}}
        onEnterAnswering={() => {}}
      />
    );
    expect(screen.getByText(/需要确认目标用户/)).toBeInTheDocument();
    expect(screen.getByText('我来回答')).toBeInTheDocument();
    expect(screen.getByText('取消')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('「我来回答」按钮 → onEnterAnswering（不发消息）', () => {
    const onPrimary = vi.fn();
    const onEnter = vi.fn();
    render(
      <HITLCard
        item={makeItem()}
        onPrimaryAction={onPrimary}
        onEnterAnswering={onEnter}
      />
    );
    fireEvent.click(screen.getByText('我来回答'));
    expect(onEnter).toHaveBeenCalledTimes(1);
    expect(onPrimary).not.toHaveBeenCalled();
  });

  it('「修改」按钮 → onEnterAnswering（同 answer 行为）', () => {
    const onPrimary = vi.fn();
    const onEnter = vi.fn();
    render(
      <HITLCard
        item={makeItem({ options: [{ label: '修改', value: 'modify' }] })}
        onPrimaryAction={onPrimary}
        onEnterAnswering={onEnter}
      />
    );
    fireEvent.click(screen.getByText('修改'));
    expect(onEnter).toHaveBeenCalledTimes(1);
    expect(onPrimary).not.toHaveBeenCalled();
  });

  it('「取消」按钮 → onPrimaryAction(skip)', () => {
    const onPrimary = vi.fn();
    const onEnter = vi.fn();
    render(
      <HITLCard
        item={makeItem()}
        onPrimaryAction={onPrimary}
        onEnterAnswering={onEnter}
      />
    );
    fireEvent.click(screen.getByText('取消'));
    expect(onPrimary).toHaveBeenCalledWith('skip');
    expect(onEnter).not.toHaveBeenCalled();
  });

  it('「approve」按钮 → onPrimaryAction(approve)', () => {
    const onPrimary = vi.fn();
    render(
      <HITLCard
        item={makeItem({ options: [{ label: '✅ 确认', value: 'approve' }] })}
        onPrimaryAction={onPrimary}
        onEnterAnswering={() => {}}
      />
    );
    fireEvent.click(screen.getByText('✅ 确认'));
    expect(onPrimary).toHaveBeenCalledWith('approve');
  });

  it('answering state: 隐藏按钮 + 显示提示', () => {
    render(
      <HITLCard
        item={makeItem({ cardState: 'answering' })}
        onPrimaryAction={() => {}}
        onEnterAnswering={() => {}}
      />
    );
    expect(screen.getByText('answering')).toBeInTheDocument();
    expect(screen.getByText(/请在下方输入框作答/)).toBeInTheDocument();
    expect(screen.queryByText('我来回答')).not.toBeInTheDocument();
  });

  it('answered state: 显示用户回答 + 不显示按钮', () => {
    render(
      <HITLCard
        item={makeItem({ cardState: 'answered', answer: '企业团队' })}
        onPrimaryAction={() => {}}
        onEnterAnswering={() => {}}
      />
    );
    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.getByText('企业团队')).toBeInTheDocument();
    expect(screen.queryByText('我来回答')).not.toBeInTheDocument();
  });

  it('delta_plan kind 显示 keep/modify/add/cancel 摘要', () => {
    render(
      <HITLCard
        item={makeItem({
          hitlKind: 'delta_plan',
          message: 'PG→MySQL',
          options: [
            { label: '✅ 应用修改', value: 'approve' },
            { label: '❌ 撤回介入', value: 'reject' },
          ],
          deltaPlan: {
            summary: 'PG→MySQL',
            keep: ['T1.1', 'T1.2'],
            modify: [{ taskId: 'T2.2', reason: 'change', newVersion: 2 }],
            add: [],
            cancel: [],
          },
        })}
        onPrimaryAction={() => {}}
        onEnterAnswering={() => {}}
      />
    );
    expect(screen.getByText(/✓ 保留 2/)).toBeInTheDocument();
    expect(screen.getByText(/🔄 重做 1/)).toBeInTheDocument();
  });
});
