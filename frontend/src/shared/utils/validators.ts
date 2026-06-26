import type { SOPNode, SOPEdge } from '../types/sop';

export interface ValidationError {
  level: 'error' | 'warning';
  message: string;
}

/** 校验 SOP 定义完整性 */
export function validateSop(nodes: SOPNode[], edges: SOPEdge[]): ValidationError[] {
  const errors: ValidationError[] = [];

  // 必须有 start 和 end
  const types = new Set(nodes.map((n) => n.type));
  if (!types.has('start')) errors.push({ level: 'error', message: 'Missing start node' });
  if (!types.has('end')) errors.push({ level: 'error', message: 'Missing end node' });

  // 孤立节点
  const connected = new Set<string>();
  for (const e of edges) {
    connected.add(e.from);
    connected.add(e.to);
  }
  for (const n of nodes) {
    if (nodes.length > 1 && !connected.has(n.id) && n.type !== 'start') {
      errors.push({ level: 'warning', message: `Orphan node: ${n.id} (${n.type})` });
    }
  }

  // agent_action 必须有 role_type（模板模式）或 agent_id（团队专属模式）
  for (const n of nodes) {
    if (n.type === 'agent_action' && !n.role_type && !n.agent_id) {
      errors.push({ level: 'error', message: `Agent node ${n.id} missing role_type or agent_id` });
    }
  }

  // validation 节点也必须有 role_type 或 agent_id
  for (const n of nodes) {
    if (n.type === 'validation' && !n.role_type && !n.agent_id) {
      errors.push({ level: 'error', message: `Validation node ${n.id} missing role_type or agent_id` });
    }
  }

  // 引用不存在的节点
  const nodeIds = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    if (!nodeIds.has(e.from)) errors.push({ level: 'error', message: `Edge from unknown node: ${e.from}` });
    if (!nodeIds.has(e.to)) errors.push({ level: 'error', message: `Edge to unknown node: ${e.to}` });
  }

  return errors;
}
