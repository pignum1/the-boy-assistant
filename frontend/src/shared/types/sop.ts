/** SOP 数据类型定义 */

export type EdgeType = 'forward' | 'reject' | 'escalate' | 'conditional';

/** Workflow 设计模式 */
export type WorkflowMode = 'team_specific' | 'template';

export type NodeType =
  // 基础节点
  | 'start' | 'end' | 'function' | 'llm_call' | 'tool'
  // Agent节点
  | 'agent' | 'agent_action' | 'router' | 'supervisor' | 'hitl' | 'hitl_confirm' | 'hitl_input' | 'hitl_choice' | 'validation'
  // 控制节点
  | 'condition' | 'switch' | 'parallel' | 'merge';

/** 角色类型（用于模板模式） */
export const ROLE_TYPES = [
  { type: 'pm',           label: '产品经理',       icon: '📋', color: 'var(--gold-400)' },
  { type: 'ui_designer',  label: 'UI 设计师',      icon: '🎨', color: 'var(--purple-400)' },
  { type: 'architect',    label: '架构师',         icon: '🏗', color: 'var(--blue-400)' },
  { type: 'backend_dev',  label: '后端工程师',      icon: '⚙', color: 'var(--green-400)' },
  { type: 'frontend_dev', label: '前端工程师',      icon: '💻', color: 'var(--cyan-400)' },
  { type: 'tester',       label: '测试员',         icon: '🧪', color: 'var(--amber-400)' },
  { type: 'devops',       label: '运维工程师',      icon: '🚀', color: 'var(--red-400)' },
  { type: 'code_reviewer', label: '代码审查员',     icon: '🔍', color: 'var(--indigo-400)' },
  { type: 'custom',       label: '自定义角色',      icon: '⭐', color: 'var(--text-muted)' },
] as const;

export interface SOPNode {
  id: string;
  type: NodeType;
  label?: string;
  role_type?: string;        // 模板模式：角色类型
  agent_id?: string;         // 团队专属模式：绑定的 Agent ID
  message?: string;
  config?: {
    require_human?: boolean;
    timeout?: number;
    auto_action?: string;
    maxRetries?: number;
    condition?: {
      field: string;
      operator: string;
      value: number;
      auto_action: string;
    };
    // HITL 特定配置
    hitl_type?: 'confirm' | 'input' | 'choice';
    context_vars?: string[];
    choices?: Array<{
      value: string;
      label: string;
      description?: string;
    }>;
    // Router 特定配置
    route_schema?: string;
    default_route?: string;
    // Parallel 特定配置
    join_mode?: 'all' | 'any' | 'n';
    join_count?: number;
    default?: any;
  };
  checks?: string[];
  pass_threshold?: number;
  prompt_template?: string;  // 任务描述/提示词模板
}

export interface SOPEdge {
  from: string;
  to: string;
  condition?: string;
  edgeType?: EdgeType;     // forward / reject / escalate
  label?: string;          // 边上显示的文字
}

/** SOP定义 / Workflow定义 */
export interface SOPDefinition {
  id?: string;
  name: string;
  description?: string;
  nodes: SOPNode[];
  edges: SOPEdge[];
  format?: string;
  version?: string;
  team_id?: string;
  /** 设计模式：团队专属 or 模板 */
  workflow_mode?: WorkflowMode;
  /** 团队专属模式的团队 ID */
  owner_team_id?: string;
}

export interface SOPSummary {
  id: string;
  name: string;
  description?: string;
  format: string;
  version: string;
  team_id: string;
  created_at: string;
}

/** 节点在画布上的位置数据 */
export interface NodePosition {
  id: string;
  position: { x: number; y: number };
}

/** 预设角色插槽（对应 7 个 Persona） */
export const ROLE_SLOTS = [
  { slot: 'pm',           label: '产品经理',       icon: '📋', color: 'var(--gold-400)' },
  { slot: 'ui_designer',  label: 'UI 设计师',      icon: '🎨', color: 'var(--purple-400)' },
  { slot: 'architect',    label: '架构师',         icon: '🏗', color: 'var(--blue-400)' },
  { slot: 'backend_dev',  label: '后端工程师',      icon: '⚙', color: 'var(--green-400)' },
  { slot: 'frontend_dev', label: '前端工程师',      icon: '💻', color: 'var(--cyan-400)' },
  { slot: 'tester',       label: '测试员',         icon: '🧪', color: 'var(--amber-400)' },
  { slot: 'devops',       label: '运维工程师',      icon: '🚀', color: 'var(--red-400)' },
] as const;

/** 根据 role_slot 获取角色信息 */
export function getRoleInfo(slot: string) {
  return ROLE_SLOTS.find(r => r.slot === slot) || { slot, label: slot, icon: '🤖', color: 'var(--text-muted)' };
}

/** 根据 condition 自动推断边类型 */
export function inferEdgeType(condition?: string): EdgeType {
  if (!condition) return 'forward';
  const c = condition.toLowerCase();
  if (c.includes('escalate')) return 'escalate';
  if (c.includes('reject') || c.includes('not ') || c.includes('fail') || c.includes('!')) return 'reject';
  return 'forward';
}

/** 多Agent工作流节点配置 */
export interface AgentNodeConfig {
  /** 绑定的Agent ID（可选，用于Team中的Agent绑定） */
  agent_id?: string;
  /** Agent角色提示 */
  role_hint?: string;
  /** 系统提示覆盖 */
  system_prompt?: string;
  /** 可用工具列表 */
  tools?: string[];
  /** 超时时间（秒） */
  timeout?: number;
}

/** 路由Agent配置 */
export interface RouterAgentConfig extends AgentNodeConfig {
  /** 路由Schema（结构化输出） */
  route_schema?: RouteSchema;
  /** 默认路由 */
  default_route?: string;
}

/** LLM路由配置 */
export interface LLMRouteConfig {
  model: string;
  schema: Record<string, unknown>;
  default_route: string;
}

/** 条件边配置 */
export interface ConditionEdgeConfig {
  type: 'expression' | 'function' | 'llm';
  expression?: string;
  function_name?: string;
  llm_config?: LLMRouteConfig;
  routes: Record<string, string>;
}

/** Workflow Agent绑定（Team到Workflow的关联） */
export interface WorkflowAgentBinding {
  node_key: string;
  agent_id: string;
  agent_name?: string;
  config?: {
    role_override?: string;
    system_prompt?: string;
    tools?: string[];
  };
}

/** Workflow定义（扩展SOP支持多Agent） */
export interface WorkflowDefinition extends SOPDefinition {
  /** 绑定的Team ID */
  team_id?: string;
  /** Agent绑定列表 */
  agent_bindings?: WorkflowAgentBinding[];
}

/** 路由Schema定义 */
export interface RouteSchema {
  type: 'object';
  properties: Record<string, { type: string; enum?: string[]; description?: string }>;
  required?: string[];
}

/** 节点颜色映射 */
export const NODE_COLORS: Record<string, string> = {
  start: '#22c55e',
  agent_action: '#3b82f6',
  hitl: '#f59e0b',
  hitl_confirm: '#f59e0b',
  hitl_input: '#8b5cf6',
  hitl_choice: '#06b6d4',
  validation: '#8b5cf6',
  condition: '#f97316',
  end: '#ef4444',
  router_agent: '#6366f1',
  supervisor_agent: '#ec4899',
};

/** 节点图标映射 */
export const NODE_ICONS: Record<string, string> = {
  start: '▶',
  agent_action: '🤖',
  hitl: '👤',
  hitl_confirm: '👤',
  hitl_input: '✏️',
  hitl_choice: '🔘',
  validation: '✓',
  condition: '◇',
  end: '■',
  router_agent: '🔀',
  supervisor_agent: '👑',
};
