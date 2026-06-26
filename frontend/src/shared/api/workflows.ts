import { api } from './client';
import type {
  Workflow,
  WorkflowDetail,
  WorkflowInstance,
  WorkflowInstanceDetail,
  CreateWorkflowRequest,
  UpdateWorkflowRequest,
  GenerateWorkflowRequest,
  GenerateWorkflowResponse,
  WorkflowValidation,
  WorkflowExample,
  NodeTypeReference,
  EdgeTypeReference,
} from '../types/workflow';

export const workflowApi = {
  // 工作流 CRUD
  list: (params?: { status?: string; is_template?: boolean; skip?: number; limit?: number }) =>
    api.get<{ items: Workflow[]; total: number }>('/api/v1/workflows', params as Record<string, string | number | boolean | undefined>),

  getDetail: (id: string) =>
    api.get<WorkflowDetail>(`/api/v1/workflows/${id}`),

  create: (data: CreateWorkflowRequest) =>
    api.post<Workflow>('/api/v1/workflows', data),

  update: (id: string, data: UpdateWorkflowRequest) =>
    api.put<Workflow>(`/api/v1/workflows/${id}`, data),

  delete: (id: string) =>
    api.del<{ message: string }>(`/api/v1/workflows/${id}`),

  // 节点管理
  addNode: (workflowId: string, node: {
    type: string;
    label: string;
    config?: Record<string, unknown>;
    position?: { x: number; y: number };
  }) =>
    api.post(`/api/v1/workflows/${workflowId}/nodes`, node),

  updateNode: (workflowId: string, nodeId: string, data: {
    label?: string;
    config?: Record<string, unknown>;
    position?: { x: number; y: number };
  }) =>
    api.put(`/api/v1/workflows/${workflowId}/nodes/${nodeId}`, data),

  deleteNode: (workflowId: string, nodeId: string) =>
    api.del<{ message: string }>(`/api/v1/workflows/${workflowId}/nodes/${nodeId}`),

  // 边管理
  addEdge: (workflowId: string, edge: {
    source: string;
    target: string;
    type: string;
    condition?: Record<string, unknown>;
  }) =>
    api.post(`/api/v1/workflows/${workflowId}/edges`, edge),

  updateEdge: (workflowId: string, edgeId: string, data: {
    type?: string;
    condition?: Record<string, unknown>;
  }) =>
    api.put(`/api/v1/workflows/${workflowId}/edges/${edgeId}`, data),

  deleteEdge: (workflowId: string, edgeId: string) =>
    api.del<{ message: string }>(`/api/v1/workflows/${workflowId}/edges/${edgeId}`),

  // 工作流验证
  validate: (id: string) =>
    api.post<WorkflowValidation>(`/api/v1/workflows/${id}/validate`, {}),

  // 工作流实例
  listInstances: (workflowId?: string) =>
    api.get<WorkflowInstance[]>('/api/v1/workflow-executions', { workflow_id: workflowId }),

  getInstanceDetail: (instanceId: string) =>
    api.get<WorkflowInstanceDetail>(`/api/v1/workflow-executions/${instanceId}`),

  startExecution: (workflowId: string, data?: {
    session_id?: string;
    user_input?: string;
  }) =>
    api.post<WorkflowInstance>('/api/v1/workflow-executions/start', {
      workflow_id: workflowId,
      ...data,
    }),

  pauseExecution: (instanceId: string) =>
    api.post<WorkflowInstance>(`/api/v1/workflow-executions/${instanceId}/pause`, {}),

  resumeExecution: (instanceId: string) =>
    api.post<WorkflowInstance>(`/api/v1/workflow-executions/${instanceId}/resume`, {}),

  cancelExecution: (instanceId: string) =>
    api.post<WorkflowInstance>(`/api/v1/workflow-executions/${instanceId}/cancel`, {}),

  // LLM 生成
  generateFromRequirement: (data: GenerateWorkflowRequest) =>
    api.post<GenerateWorkflowResponse>('/api/v1/workflow-generator/generate', data),

  // 获取案例和类型参考
  getExamples: () =>
    api.get<WorkflowExample[]>('/api/v1/workflow-generator/examples'),

  getNodeTypes: () =>
    api.get<Record<string, NodeTypeReference>>('/api/v1/workflow-generator/node-types'),

  getEdgeTypes: () =>
    api.get<Record<string, EdgeTypeReference>>('/api/v1/workflow-generator/edge-types'),

  // WebSocket 连接（需要在客户端单独实现）
  // ws://localhost:8000/api/v1/workflow-events/ws/instances/{instance_id}
};
