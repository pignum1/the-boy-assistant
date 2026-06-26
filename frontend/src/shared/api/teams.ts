import { api } from './client';
import type { Team } from '../types/agent';

export interface CreateTeamRequest {
  name: string;
  description?: string;
  members: Array<{
    agent_id: string;
    role_slot: string;
  }>;
}

export const teamsApi = {
  list: () => api.get<Team[]>('/api/v1/teams'),

  get: (teamId: string) => api.get<Team>(`/api/v1/teams/${teamId}`),

  create: (req: CreateTeamRequest) => api.post<Team>('/api/v1/teams', req),

  delete: (teamId: string) => api.del<void>(`/api/v1/teams/${teamId}`),

  addMember: (teamId: string, agentId: string, roleSlot: string) =>
    api.post<Team>(`/api/v1/teams/${teamId}/members`, { agent_id: agentId, role_slot: roleSlot }),

  removeMember: (teamId: string, agentId: string) =>
    api.del<void>(`/api/v1/teams/${teamId}/members/${agentId}`),
};
