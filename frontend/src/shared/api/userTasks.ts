/** 用户任务 API */
import type { UserTask, TaskIssue } from '../types/task';

export interface CreateUserTaskParams {
  team_id?: string;
  session_id?: string;
  title: string;
  requirement: string;
  priority?: 'low' | 'medium' | 'high';
}

export interface PlanTaskParams {
  available_agents: Array<{ id: string; name: string; role?: string }>;
  team_context?: Record<string, unknown>;
}

export interface TaskPlan {
  task_name: string;
  task_description: string;
  estimated_steps: number;
  estimated_duration_minutes?: number;
  workflow: { nodes: unknown[]; edges: unknown[] };
  suggestions: string[];
  risks: string[];
}

export const userTasksApi = {
  async create(params: CreateUserTaskParams): Promise<UserTask> {
    const res = await fetch('/api/v1/user-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`创建任务失败: ${res.status}`);
    return res.json();
  },

  async list(teamId?: string, sessionId?: string, status?: string): Promise<UserTask[]> {
    const params = new URLSearchParams();
    if (teamId) params.set('team_id', teamId);
    if (sessionId) params.set('session_id', sessionId);
    if (status) params.set('status', status);

    const res = await fetch(`/api/v1/user-tasks?${params}`);
    if (!res.ok) throw new Error(`获取任务列表失败: ${res.status}`);
    return res.json();
  },

  async get(taskId: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}`);
    if (!res.ok) throw new Error(`获取任务失败: ${res.status}`);
    return res.json();
  },

  async update(taskId: string, params: Partial<UserTask>): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`更新任务失败: ${res.status}`);
    return res.json();
  },

  async delete(taskId: string): Promise<void> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`删除任务失败: ${res.status}`);
  },

  // AI 规划
  async plan(taskId: string, params: PlanTaskParams): Promise<TaskPlan> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) throw new Error(`AI 规划失败: ${res.status}`);
    return res.json();
  },

  // 启动任务
  async start(taskId: string, userInput?: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: userInput }),
    });
    if (!res.ok) throw new Error(`启动任务失败: ${res.status}`);
    return res.json();
  },

  // 暂停/恢复/取消
  async pause(taskId: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/pause`, { method: 'POST' });
    if (!res.ok) throw new Error(`暂停任务失败: ${res.status}`);
    return res.json();
  },

  async resume(taskId: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/resume`, { method: 'POST' });
    if (!res.ok) throw new Error(`恢复任务失败: ${res.status}`);
    return res.json();
  },

  async cancel(taskId: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error(`取消任务失败: ${res.status}`);
    return res.json();
  },

  // 进度查询
  async getProgress(taskId: string): Promise<any> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/progress`);
    if (!res.ok) throw new Error(`获取进度失败: ${res.status}`);
    return res.json();
  },

  // 问题管理
  async listIssues(taskId: string, status?: string, severity?: string): Promise<TaskIssue[]> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (severity) params.set('severity', severity);

    const res = await fetch(`/api/v1/user-tasks/${taskId}/issues?${params}`);
    if (!res.ok) throw new Error(`获取问题列表失败: ${res.status}`);
    return res.json();
  },

  async recordIssue(taskId: string, issue: Omit<TaskIssue, 'id' | 'created_at' | 'updated_at'>): Promise<TaskIssue> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/issues`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(issue),
    });
    if (!res.ok) throw new Error(`记录问题失败: ${res.status}`);
    return res.json();
  },

  // 任务迭代
  async iterate(taskId: string, feedback: string): Promise<UserTask> {
    const res = await fetch(`/api/v1/user-tasks/${taskId}/iterate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    });
    if (!res.ok) throw new Error(`创建迭代失败: ${res.status}`);
    return res.json();
  },
};
