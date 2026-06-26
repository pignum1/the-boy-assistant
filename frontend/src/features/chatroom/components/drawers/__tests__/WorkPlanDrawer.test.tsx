/** WorkPlanDrawer 测试：阶段树渲染 + delta 摘要 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkPlanDrawer } from '../WorkPlanDrawer';
import type { WorkPlan, DeltaPlan } from '../../../types/state';

function makePlan(): WorkPlan {
  return {
    phases: [
      { id: 'p1', name: 'PRD', status: 'done', taskIds: ['T1.1', 'T1.2'] },
      { id: 'p2', name: '架构设计', status: 'running', taskIds: ['T2.1'] },
    ],
    tasks: {
      'T1.1': {
        id: 'T1.1', phaseId: 'p1', name: '故事梳理',
        agentId: 'pm', agentName: 'PM', agentEmoji: '📋',
        dependsOn: [], status: 'done', version: 1, artifactIds: [],
        startedAt: 1000, endedAt: 2000,
      },
      'T1.2': {
        id: 'T1.2', phaseId: 'p1', name: '验收标准',
        agentId: 'pm', agentName: 'PM', agentEmoji: '📋',
        dependsOn: [], status: 'done', version: 1, artifactIds: [],
      },
      'T2.1': {
        id: 'T2.1', phaseId: 'p2', name: '架构图',
        agentId: 'arch', agentName: '架构师', agentEmoji: '🏗',
        dependsOn: [], status: 'running', version: 1, artifactIds: [],
      },
    },
    totalTasks: 3,
    doneTasks: 2,
  };
}

describe('WorkPlanDrawer', () => {
  it('null workPlan → empty state', () => {
    render(<WorkPlanDrawer workPlan={null} workPlanDelta={null} />);
    expect(screen.getByText(/等待 Supervisor 分析/)).toBeInTheDocument();
  });

  it('renders phases + tasks + progress', () => {
    render(<WorkPlanDrawer workPlan={makePlan()} workPlanDelta={null} />);
    // 阶段名
    expect(screen.getByText('PRD')).toBeInTheDocument();
    expect(screen.getByText('架构设计')).toBeInTheDocument();
    // 任务名
    expect(screen.getByText('故事梳理')).toBeInTheDocument();
    expect(screen.getByText('架构图')).toBeInTheDocument();
    // 任务 id
    expect(screen.getByText('T1.1')).toBeInTheDocument();
    // 进度（文本被拆成多个 span）
    expect(screen.getByText(/\/3 任务/)).toBeInTheDocument();
    expect(screen.getByText(/1\/2 阶段/)).toBeInTheDocument();
  });

  it('renders DeltaSummaryBar when delta present', () => {
    const delta: DeltaPlan = {
      summary: 'PG→MySQL',
      keep: ['T1.1', 'T1.2'],
      modify: [{ taskId: 'T2.1', reason: 'change', newVersion: 2 }],
      add: [],
      cancel: [],
    };
    render(<WorkPlanDrawer workPlan={makePlan()} workPlanDelta={delta} />);
    expect(screen.getByText(/⚠️ 介入修改：PG→MySQL/)).toBeInTheDocument();
    expect(screen.getByText(/✓ 保留 2/)).toBeInTheDocument();
    expect(screen.getByText(/🔄 重做 1/)).toBeInTheDocument();
  });

  it('shows elapsed time for completed tasks', () => {
    render(<WorkPlanDrawer workPlan={makePlan()} workPlanDelta={null} />);
    // T1.1 startedAt=1000 endedAt=2000 → 1s
    expect(screen.getByText('1s')).toBeInTheDocument();
  });
});
