/** Agent绑定面板 - 用于Team创建时配置Agent到Workflow节点的绑定 */
import { useState, useEffect } from 'react';
import type { Agent, WorkflowAgentBinding } from '../../shared/types';

interface AgentBindingPanelProps {
  /** 可用的Agent列表 */
  availableAgents: Agent[];
  /** 已选择的Agent ID集合 */
  selectedAgentIds: Set<string>;
  /** 当前绑定的配置 */
  bindings: WorkflowAgentBinding[];
  /** 绑定变更回调 */
  onBindingsChange: (bindings: WorkflowAgentBinding[]) => void;
  /** Workflow中的节点列表（从Workflow解析） */
  workflowNodes?: Array<{ id: string; label: string; type: string }>;
  disabled?: boolean;
}

export function AgentBindingPanel({
  availableAgents,
  selectedAgentIds,
  bindings,
  onBindingsChange,
  workflowNodes = [],
  disabled = false,
}: AgentBindingPanelProps) {
  // 为每个已选Agent创建或更新绑定
  useEffect(() => {
    const newBindings: WorkflowAgentBinding[] = [];

    for (const agentId of selectedAgentIds) {
      const existing = bindings.find((b) => b.agent_id === agentId);
      const agent = availableAgents.find((a) => a.id === agentId);

      if (existing) {
        newBindings.push(existing);
      } else if (agent) {
        // 尝试智能匹配节点
        const matchedNode = findBestMatchNode(agent, workflowNodes, newBindings);
        newBindings.push({
          node_key: matchedNode?.id || '',
          agent_id: agentId,
          agent_name: agent.name,
        });
      }
    }

    // 只在有变化时更新
    if (JSON.stringify(newBindings) !== JSON.stringify(bindings)) {
      onBindingsChange(newBindings);
    }
  }, [selectedAgentIds, availableAgents, workflowNodes]);

  const updateBinding = (agentId: string, nodeKey: string) => {
    const updated = bindings.map((b) =>
      b.agent_id === agentId ? { ...b, node_key: nodeKey } : b
    );
    onBindingsChange(updated);
  };

  const getAvailableNodes = (currentAgentId: string) => {
    // 返回未被其他Agent绑定的节点
    const usedKeys = bindings
      .filter((b) => b.agent_id !== currentAgentId)
      .map((b) => b.node_key);
    return workflowNodes.filter((n) => !usedKeys.includes(n.id));
  };

  if (selectedAgentIds.size === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
        请先在「基本信息+成员」步骤中选择团队成员
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
        节点绑定配置
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12 }}>
        将团队成员绑定到Workflow的执行节点上
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {Array.from(selectedAgentIds).map((agentId) => {
          const agent = availableAgents.find((a) => a.id === agentId);
          const binding = bindings.find((b) => b.agent_id === agentId);
          const availableNodes = getAvailableNodes(agentId);

          if (!agent) return null;

          return (
            <div
              key={agentId}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 12px',
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--text-primary)' }}>
                  {agent.name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1 }}>
                  {agent.persona_id || 'Agent'}
                </div>
              </div>

              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>→</span>

              <select
                value={binding?.node_key || ''}
                onChange={(e) => updateBinding(agentId, e.target.value)}
                disabled={disabled}
                style={nodeSelectStyle}
              >
                <option value="">— 选择节点 —</option>
                {availableNodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.label} ({node.type})
                  </option>
                ))}
                {availableNodes.length === 0 && (
                  <option value="" disabled>
                    无可用节点
                  </option>
                )}
              </select>

              {binding?.node_key && (
                <span style={{ fontSize: 16, color: 'var(--green-400)' }}>✓</span>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 12, padding: 10, background: 'var(--bg-elevated)', borderRadius: 6, fontSize: 11, color: 'var(--text-muted)' }}>
        💡 提示：每个Agent应绑定到不同的Workflow节点。节点类型为 agent、router_agent、supervisor_agent 的节点需要绑定Agent。
      </div>

      {/* HITL 节点列表 */}
      {workflowNodes.filter(n => isHITLNode(n.type)).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
            人机协同节点（HITL）
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>
            以下节点需要人工介入，将在执行时暂停等待用户确认
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {workflowNodes.filter(n => isHITLNode(n.type)).map((node) => (
              <div
                key={node.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 10px',
                  background: 'var(--orange-bg)',
                  border: '1px solid var(--orange-border)',
                  borderRadius: 6,
                }}
              >
                <span style={{ fontSize: 14 }}>{getHITLIcon(node.type)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--text-primary)' }}>
                    {node.label}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)' }}>
                    {node.type === 'hitl_confirm' && '需要确认'}
                    {node.type === 'hitl_input' && '需要输入'}
                    {node.type === 'hitl_choice' && '需要选择'}
                    {node.type === 'hitl' && '需要审批'}
                  </div>
                </div>
                <span style={{ fontSize: 10, color: 'var(--orange-400)', fontWeight: 500 }}>
                  等待人工介入
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 智能匹配最佳节点 */
function findBestMatchNode(
  agent: Agent,
  nodes: Array<{ id: string; label: string; type: string }>,
  existingBindings: WorkflowAgentBinding[]
): { id: string; label: string; type: string } | undefined {
  // 获取已使用的节点
  const usedKeys = new Set(existingBindings.map((b) => b.node_key));

  // 筛选出可用且需要Agent的节点（排除 HITL 节点）
  const agentNodes = nodes.filter(
    (n) => !usedKeys.has(n.id) &&
          ['agent', 'agent_action', 'router_agent', 'supervisor_agent'].includes(n.type)
  );

  if (agentNodes.length === 0) return undefined;

  // 尝试通过名称匹配
  const nameMatch = agentNodes.find((n) =>
    n.label.toLowerCase().includes(agent.name.toLowerCase()) ||
    agent.name.toLowerCase().includes(n.label.toLowerCase())
  );
  if (nameMatch) return nameMatch;

  // 返回第一个可用的agent节点
  return agentNodes.find((n) => n.type === 'agent') || agentNodes[0];
}

/** 检查节点是否为 HITL 类型 */
function isHITLNode(nodeType: string): boolean {
  return ['hitl', 'hitl_input', 'hitl_confirm', 'hitl_choice'].includes(nodeType);
}

/** 获取 HITL 节点图标 */
function getHITLIcon(nodeType: string): string {
  switch (nodeType) {
    case 'hitl_input': return '✏️';
    case 'hitl_confirm': return '👤';
    case 'hitl_choice': return '🔘';
    default: return '👤';
  }
}

const nodeSelectStyle: React.CSSProperties = {
  minWidth: 160,
  padding: '6px 8px',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-medium)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  fontSize: 11,
  fontFamily: 'var(--font-body)',
  outline: 'none',
  cursor: 'pointer',
};
