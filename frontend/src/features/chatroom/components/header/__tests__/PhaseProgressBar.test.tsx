/** PhaseProgressBar 测试：双行渲染逻辑 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PhaseProgressBar } from '../PhaseProgressBar';
import { makeInitialMetaPhases } from '../../../types/state';
import type { WorkPlan } from '../../../types/state';

const SID = '12345678-abcd-ef01-2345-6789abcdef01';

function setup(overrides: Partial<Parameters<typeof PhaseProgressBar>[0]> = {}) {
  const onJumpToPhase = vi.fn();
  const onToggleDrawer = vi.fn();
  const onHardInterrupt = vi.fn();
  const props = {
    sessionId: SID,
    wsConnected: true,
    executionState: 'idle' as const,
    routing: null,
    phases: makeInitialMetaPhases(),
    currentPhaseId: null,
    workPlan: null,
    artifactsCount: 0,
    teamCount: 0,
    openDrawer: null,
    onJumpToPhase,
    onToggleDrawer,
    onHardInterrupt,
    ...overrides,
  };
  return { ...props, render: () => render(<PhaseProgressBar {...props} />) };
}

describe('PhaseProgressBar', () => {
  it('idle + no routing → 只显示顶行（session info + drawer buttons）', () => {
    setup().render();
    expect(screen.getByText('🟢 12345678')).toBeInTheDocument();
    expect(screen.getByText('空闲')).toBeInTheDocument();
    // 系统行不应出现
    expect(screen.queryByText('系统')).not.toBeInTheDocument();
  });

  it('routing=multi_agent → 显示系统阶段行', () => {
    const phases = makeInitialMetaPhases();
    phases[0] = { ...phases[0], status: 'done' };
    phases[1] = { ...phases[1], status: 'thinking' };
    setup({ routing: 'multi_agent', phases }).render();
    expect(screen.getByText('系统')).toBeInTheDocument();
    // 短名出现
    expect(screen.getByText('意图')).toBeInTheDocument();
    expect(screen.getByText('分析')).toBeInTheDocument();
  });

  it('workPlan 出现 → 显示业务任务行', () => {
    const workPlan: WorkPlan = {
      phases: [
        { id: 'p1', name: 'PRD', status: 'done', taskIds: ['T1.1'] },
        { id: 'p2', name: '架构', status: 'pending', taskIds: [] },
      ],
      tasks: {
        'T1.1': {
          id: 'T1.1', phaseId: 'p1', name: '故事',
          agentId: 'pm', agentName: 'PM', agentEmoji: '📋',
          dependsOn: [], status: 'done', version: 1, artifactIds: [],
        },
      },
      totalTasks: 4,
      doneTasks: 1,
    };
    setup({ routing: 'multi_agent', workPlan }).render();
    // "任务" 出现两次（drawer 按钮 + workPlanRow label），用 getAllByText
    expect(screen.getAllByText('任务').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('/4 任务')).toBeInTheDocument();
    expect(screen.getByText('1/2 阶段')).toBeInTheDocument();
  });

  it('点击系统阶段圆点 → 调用 onJumpToPhase', () => {
    const phases = makeInitialMetaPhases();
    const { onJumpToPhase } = setup({ routing: 'multi_agent', phases });
    setup({ routing: 'multi_agent', phases, onJumpToPhase }).render();
    // 找到"意图"的圆点按钮（带 aria-label）
    const btn = screen.getAllByRole('button').find(b =>
      b.getAttribute('aria-label')?.includes('M0')
    );
    if (btn) fireEvent.click(btn);
    expect(onJumpToPhase).toHaveBeenCalledWith('m0_intent');
  });

  it('点击 drawer 按钮 → 调用 onToggleDrawer', () => {
    const onToggleDrawer = vi.fn();
    setup({ onToggleDrawer }).render();
    fireEvent.click(screen.getByText('任务')); // 📋 按钮
    expect(onToggleDrawer).toHaveBeenCalledWith('plan');
  });

  it('硬中断按钮只在执行态出现', () => {
    const onHardInterrupt = vi.fn();
    const { render: r1 } = setup({ executionState: 'thinking', onHardInterrupt });
    const { unmount } = r1();
    expect(screen.getByText('⏹ 停止')).toBeInTheDocument();
    unmount();
    setup({ executionState: 'idle' }).render();
    expect(screen.queryByText('⏹ 停止')).not.toBeInTheDocument();
  });
});
