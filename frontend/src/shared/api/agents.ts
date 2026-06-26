import { api } from './client';
import type { Agent } from '../types/agent';

export interface PoolStatus {
  agent_id: string;
  status: string;
  team_id?: string;
  current_task?: string;
}

export const agentsApi = {
  list: () => api.get<Agent[]>('/api/v1/agents'),

  get: (agentId: string) => api.get<Agent>(`/api/v1/agents/${agentId}`),

  poolStatus: () => api.get<PoolStatus[]>('/api/v1/agents/pool/status'),
};
