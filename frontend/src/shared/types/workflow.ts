/** Workflow 类型定义：统一工作流架构的数据类型 */

// 节点类型
export type NodeType =
  | 'Start'
  | 'End'
  | 'Agent'
  | 'Router'
  | 'Parallel'
  | 'Condition'
  | 'HITL'
  | 'Validation';

// 边类型
export type EdgeType =
  | 'Forward'
  | 'Reject'
  | 'Escalate'
  | 'Timeout'
  | 'Fallback';

// 节点配置
export interface AgentNodeConfig {
  agent_id?: string;
  agent_role?: string;
  prompt_template?: string;
  tools?: string[];
  model_config?: {
    model?: string;
    temperature?: number;
    max_tokens?: number;
  };
}

export interface RouterNodeConfig {
  strategy: 'round_robin' | 'priority' | 'semantic' | 'workload';
  candidates: string[];  // agent IDs or node IDs
  fallback_agent_id?: string;
}

export interface ParallelNodeConfig {
  branches: Array<{
    nodes: WorkflowNodeDef[];
  }>;
  merge_strategy: 'all' | 'first' | 'majority';
  timeout?: number;
}

export interface ConditionNodeConfig {
  expression: string;
  branches: Record<string, string>;  // value -> target node ID
}

export interface HITLNodeConfig {
  action_type: 'approve' | 'input' | 'modify';
  timeout: number;  // seconds
  escalation_target?: string;
}

export interface ValidationNodeConfig {
  validator: 'LLM' | 'Agent' | 'Rule';
  validator_agent_id?: string;
  criteria: string[];
  on_fail: 'reject' | 'retry' | 'escalate';
}

export type NodeConfig =
  | AgentNodeConfig
  | RouterNodeConfig
  | ParallelNodeConfig
  | ConditionNodeConfig
  | HITLNodeConfig
  | ValidationNodeConfig
  | Record<string, unknown>;

// 节点位置
export interface NodePosition {
  x: number;
  y: number;
}

// 工作流节点定义
export interface WorkflowNodeDef {
  id: string;
  type: NodeType;
  label: string;
  config?: NodeConfig;
  position?: NodePosition;
}

// 工作流边定义
export interface WorkflowEdgeDef {
  source: string;
  target: string;
  type: EdgeType;
  condition?: Record<string, unknown>;
}

// 完整工作流定义
export interface WorkflowDef {
  nodes: WorkflowNodeDef[];
  edges: WorkflowEdgeDef[];
}

// 工作流模板
export interface WorkflowTemplate {
  template_type: string;
  name: string;
  description: string;
  definition: WorkflowDef;
  default_config?: Record<string, unknown>;
}

// 工作流
export interface Workflow {
  id: string;
  name: string;
  description?: string;
  template_type?: string;
  definition: WorkflowDef;
  version: number;
  created_by?: string;
  is_template: boolean;
  status: 'draft' | 'active' | 'archived';
  created_at: string;
  updated_at: string;
}

// 工作流节点（带 ID）
export interface WorkflowNode extends WorkflowNodeDef {
  workflow_id: string;
  created_at: string;
}

// 工作流边（带 ID）
export interface WorkflowEdge extends WorkflowEdgeDef {
  workflow_id: string;
  id: string;
  created_at: string;
}

// 工作流实例
export interface WorkflowInstance {
  id: string;
  workflow_id: string;
  session_id?: string;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
  state?: Record<string, unknown>;
  current_node_id?: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  retry_count: number;
  hitl_pending: boolean;
  hitl_node_id?: string;
  hitl_action_type?: string;
  hitl_timeout_at?: string;
  created_at: string;
  updated_at: string;
}

// 节点执行记录
export interface NodeExecution {
  id: string;
  instance_id: string;
  node_id?: string;
  node_type: string;
  node_label?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  retry_count: number;
  agent_id?: string;
  agent_name?: string;
  model_used?: string;
  provider_used?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  created_at: string;
}

// LLM 分析结果
export interface WorkflowAnalysis {
  task_type: string;
  complexity: 'low' | 'medium' | 'high';
  participants: string[];
  need_human: boolean;
  suggested_name: string;
  summary: string;
  suggested_template: string;
  suggestions: string[];
}

// 工作流验证结果
export interface WorkflowValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  node_count: number;
  edge_count: number;
}

// 工作流详情（包含节点和边）
export interface WorkflowDetail extends Workflow {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

// 工作流实例详情（包含执行记录）
export interface WorkflowInstanceDetail extends WorkflowInstance {
  workflow?: Workflow;
  node_executions: NodeExecution[];
}

// 创建请求
export interface CreateWorkflowRequest {
  name: string;
  description?: string;
  template_type?: string;
  definition?: WorkflowDef;
}

export interface UpdateWorkflowRequest {
  name?: string;
  description?: string;
  template_type?: string;
  definition?: WorkflowDef;
  status?: 'draft' | 'active' | 'archived';
  version?: number;
}

// 生成工作流请求
export interface GenerateWorkflowRequest {
  requirement: string;
  team_id: string;
  name?: string;
}

// LLM 生成工作流响应
export interface GenerateWorkflowResponse {
  name: string;
  description: string;
  template_type: string;
  definition: WorkflowDef;
  analysis: WorkflowAnalysis;
  validation: WorkflowValidation;
  suggestions: string[];
}

// 节点类型参考
export interface NodeTypeReference {
  description: string;
  config: Record<string, unknown>;
  examples: string[];
}

// 边类型参考
export interface EdgeTypeReference {
  description: string;
}

// 案例
export interface WorkflowExample {
  id: string;
  name: string;
  scenario: string;
  requirement_analysis: {
    task_type: string;
    participants: string[];
    complexity: string;
    need_human: boolean;
  };
  workflow_template: {
    nodes: WorkflowNodeDef[];
    edges: WorkflowEdgeDef[];
  };
  expected_outcome: string;
}

// React Flow 节点类型
export interface ReactFlowNode extends WorkflowNodeDef {
  // React Flow 特有属性
  data?: Record<string, unknown>;
}

// React Flow 边类型
export interface ReactFlowEdge extends WorkflowEdgeDef {
  // React Flow 特有属性
  id?: string;
  data?: Record<string, unknown>;
}
