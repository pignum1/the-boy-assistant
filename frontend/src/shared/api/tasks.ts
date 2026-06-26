import { api } from './client';

export interface TaskStartRequest {
  sop_id: string;
  team_id?: string;
  input?: Record<string, unknown>;
  priority?: 'critical' | 'high' | 'normal' | 'low';
}

export interface TaskResponse {
  task_id: string;
  status: string;
  current_node?: string;
  result?: unknown;
  error?: string;
  created_at: string;
  updated_at: string;
}

export const tasksApi = {
  start: (req: TaskStartRequest) => api.post<TaskResponse>('/api/v1/tasks/start', req),

  get: (taskId: string) => api.get<TaskResponse>(`/api/v1/tasks/${taskId}`),

  list: (params?: { status?: string; team_id?: string; limit?: number }) =>
    api.get<TaskResponse[]>('/api/v1/tasks', params as Record<string, string>),

  cancel: (taskId: string) => api.post<TaskResponse>(`/api/v1/tasks/${taskId}/cancel`),

  approve: (taskId: string, approved: boolean, feedback?: string) =>
    api.post<TaskResponse>(`/api/v1/tasks/${taskId}/approve`, { approved, feedback }),
};
