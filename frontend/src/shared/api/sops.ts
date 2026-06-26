import { api } from './client';
import type { SOPDefinition, SOPSummary } from '../types/sop';

export const sopsApi = {
  list: () => api.get<SOPSummary[]>('/api/v1/sops'),

  get: (sopId: string) => api.get<SOPDefinition>(`/api/v1/sops/${sopId}`),

  create: (sop: SOPDefinition) => api.post<SOPDefinition>('/api/v1/sops', sop),

  update: (sopId: string, sop: Partial<SOPDefinition>) =>
    api.put<SOPDefinition>(`/api/v1/sops/${sopId}`, sop),

  delete: (sopId: string) => api.del<void>(`/api/v1/sops/${sopId}`),

  validate: (sop: SOPDefinition) =>
    api.post<{ valid: boolean; errors: string[] }>('/api/v1/sops/validate', sop),
};
