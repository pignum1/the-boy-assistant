import { useCallback, useEffect, useState } from 'react';
import { useWebSocket } from '../../../shared/hooks/useWebSocket';
import type { WSMessage } from '../../../shared/types/websocket';

export interface NodeState {
  nodeId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_approval';
  agent?: string;
  output?: string;
}

export interface AgentMsg {
  id: string;
  agent: string;
  content: string;
  timestamp: number;
  type: 'message' | 'system' | 'error';
}

export interface HitlRequest {
  nodeId: string;
  agent: string;
  question: string;
  options?: string[];
}

export function useTaskEvents(taskId: string, teamId?: string) {
  const [nodeStates, setNodeStates] = useState<Record<string, NodeState>>({});
  const [messages, setMessages] = useState<AgentMsg[]>([]);
  const [hitlRequest, setHitlRequest] = useState<HitlRequest | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('pending');

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'node_update': {
        const payload = msg.payload as { node_id: string; status: string; label?: string; agent?: string; output?: string };
        setNodeStates((prev) => ({
          ...prev,
          [payload.node_id]: {
            nodeId: payload.node_id,
            status: payload.status as NodeState['status'],
            agent: payload.agent,
            output: payload.output,
          },
        }));
        break;
      }
      case 'task_update': {
        const payload = msg.payload as { status: string; node_id?: string; label?: string };
        setTaskStatus(payload.status);
        // 如果 task_update 包含节点信息，也更新节点状态
        if (payload.node_id) {
          setNodeStates((prev) => ({
            ...prev,
            [payload.node_id]: {
              nodeId: payload.node_id,
              status: payload.status as NodeState['status'],
              label: payload.label || payload.node_id,
            },
          }));
        }
        break;
      }
      case 'agent_message': {
        const payload = msg.payload as { agent: string; content: string };
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
            agent: payload.agent,
            content: payload.content,
            timestamp: Date.now(),
            type: 'message',
          },
        ]);
        break;
      }
      case 'hitl_notification': {
        const payload = msg.payload as { node_id: string; agent: string; question: string; options?: string[] };
        setHitlRequest({
          nodeId: payload.node_id,
          agent: payload.agent,
          question: payload.question,
          options: payload.options,
        });
        break;
      }
      case 'task_complete': {
        const payload = msg.payload as { status: string };
        setTaskStatus(payload.status);
        break;
      }
      case 'error': {
        const payload = msg.payload as { message: string };
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}_error`,
            agent: 'System',
            content: payload.message,
            timestamp: Date.now(),
            type: 'error',
          },
        ]);
        break;
      }
    }
  }, []);

  const { connected } = useWebSocket({
    taskId,
    teamId,
    onMessage: handleMessage,
  });

  useEffect(() => {
    setNodeStates({});
    setMessages([]);
    setHitlRequest(null);
    setTaskStatus('pending');
  }, [taskId]);

  const dismissHitl = useCallback(() => setHitlRequest(null), []);

  return { nodeStates, messages, hitlRequest, taskStatus, connected, dismissHitl };
}
