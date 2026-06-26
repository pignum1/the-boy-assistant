/** WebSocket 消息类型定义 */

export type WSMessageType =
  | 'node_update'
  | 'agent_message'
  | 'hitl_notification'
  | 'task_complete'
  | 'thinking_update'      // Session: Agent 思考步骤
  | 'reasoning_complete'    // Session: Agent 推理完成
  | 'message_complete'      // Session: 消息处理完成
  | 'error'
  | 'pong';

export interface WSMessage {
  type: WSMessageType;
  source?: string;
  timestamp?: string;
  payload: Record<string, unknown>;
}

export interface NodeUpdatePayload {
  task_id: string;
  node: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'paused';
  output?: string;
}

export interface AgentMessagePayload {
  task_id: string;
  agent_name: string;
  role_slot: string;
  content: string;
}

export interface HitlNotificationPayload {
  task_id: string;
  node: string;
  hitl_data: {
    node: string;
    message: string;
    timeout: number;
  };
}

export interface TaskCompletePayload {
  task_id: string;
  status: string;
  artifacts?: number;
  duration_ms?: number;
}
