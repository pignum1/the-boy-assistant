/** Agent / Team 相关类型 */

export interface Agent {
  id: string;
  name: string;
  persona_id: string;
  default_model_id: string;
  status: 'idle' | 'busy' | 'error';
}

export interface Team {
  id: string;
  name: string;
  description?: string;
  collaboration_mode?: string;
  mode?: string;  // backward compat
  icon?: string;
  status: 'active' | 'inactive';
  members?: TeamMember[];
  allow_agent_to_agent?: boolean;
  capabilities?: string[];

  /** langgraph模式配置 */
  langgraph_config?: TeamLangGraphConfig;
}

/** Team的langgraph配置 */
export interface TeamLangGraphConfig {
  /** 绑定的Workflow ID */
  workflow_id?: string;
  /** Agent节点绑定 */
  bindings: TeamAgentBinding[];
}

/** Team Agent绑定 */
export interface TeamAgentBinding {
  /** Workflow中的节点ID */
  node_key: string;
  /** Agent ID */
  agent_id: string;
  /** Agent名称（冗余） */
  agent_name?: string;
  /** 配置覆盖 */
  config?: {
    role_override?: string;
    system_prompt?: string;
    tools?: string[];
  };
}

export interface TeamMember {
  agent_id: string;
  agent_name?: string;
  role_slot: string;
}
