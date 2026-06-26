/** CollabWorkspace — 多层委托协作工作区

三栏布局：左侧聊天 + 中间委托树（xyflow）+ 右侧详情面板
支持实时状态更新、HITL 确认、mock 数据调试
*/
import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';

import { AgentNode } from './AgentNode';
import { DelegationEdge } from './DelegationEdge';
import { AgentDetailPanel } from './AgentDetailPanel';
import { CompletionSummary } from './CompletionSummary';
import { useWorkspaceEvents } from './hooks/useWorkspaceEvents';
import type {
  DelegationNode,
  WorkspaceState,
  AgentNodeData,
  DelegationEdgeData,
} from '../../shared/types/session';

// ── xyflow node/edge types ──

const NODE_TYPES: NodeTypes = { agent: AgentNode };
const EDGE_TYPES: EdgeTypes = { delegation: DelegationEdge };

// ── dagre layout for delegation tree ──

const NODE_SIZE = { w: 260, h: 160 };

function layoutTree(
  wsNodes: Record<string, DelegationNode>,
  rootId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const nodeList = Object.values(wsNodes);
  const activeNodes = nodeList.filter(n => n.status !== 'idle');
  if (activeNodes.length === 0) return { nodes: [], edges: [] };

  // Build dagre graph
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: 'TB',
    nodesep: 80,
    ranksep: 100,
    marginx: 80,
    marginy: 80,
    align: 'UL',
  });

  // Add active nodes to dagre
  for (const dn of activeNodes) {
    g.setNode(dn.id, { width: NODE_SIZE.w, height: NODE_SIZE.h });
  }

  // Add edges (parent → child)
  const edges: Edge[] = [];
  for (const dn of activeNodes) {
    for (const cid of dn.childIds) {
      if (!wsNodes[cid] || wsNodes[cid].status === 'idle') continue;
      g.setEdge(dn.id, cid, { weight: 1 });
      edges.push({
        id: `edge-${dn.id}-${cid}`,
        source: dn.id,
        target: cid,
        type: 'delegation',
        data: {
          task: wsNodes[cid].task,
          isPending: wsNodes[cid].status === 'waiting',
          isSubSupervisor: wsNodes[cid].role === 'sub_supervisor',
        } as DelegationEdgeData,
      });
    }
  }

  dagre.layout(g);

  // Map to xyflow nodes
  const nodes: Node[] = activeNodes.map(dn => {
    const pos = g.node(dn.id);
    return {
      id: dn.id,
      type: 'agent',
      position: pos ? { x: pos.x - NODE_SIZE.w / 2, y: pos.y - NODE_SIZE.h / 2 } : { x: 0, y: 0 },
      data: { node: dn } as AgentNodeData,
    };
  });

  return { nodes, edges };
}

// ── Main Component ──

interface CollabWorkspaceProps {
  /** 是否启用 mock 数据模式（独立调试） */
  mockMode?: boolean;
  /** 外部传入的 sessionId，用于真实事件 */
  sessionId?: string;
}

export function CollabWorkspace({ mockMode = false, sessionId }: CollabWorkspaceProps) {
  const { workspace, selectNode, loadMockData } = useWorkspaceEvents();
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);

  // On mount, if mock mode, load mock data
  useEffect(() => {
    if (mockMode) loadMockData();
  }, [mockMode, loadMockData]);

  // Compute xyflow nodes/edges from workspace state
  const { flowNodes, flowEdges } = useMemo(() => {
    const { nodes, edges } = layoutTree(workspace.nodes, workspace.rootId);
    return { flowNodes: nodes, flowEdges: edges };
  }, [workspace.nodes, workspace.rootId]);

  // Re-inject onSelect + isSelected (needs to be reactive to internalSelectedId)
  const reactiveNodes = useMemo(() => {
    const onSelect = (id: string) => {
      setInternalSelectedId(id);
      selectNode(id);
    };
    return flowNodes.map(n => ({
      ...n,
      data: {
        ...(n.data as AgentNodeData),
        node: (n.data as AgentNodeData).node,
        isSelected: internalSelectedId === n.id,
        onSelect,
      },
    }));
  }, [flowNodes, internalSelectedId, selectNode]);

  // Selected node for detail panel
  const selectedNode = internalSelectedId ? workspace.nodes[internalSelectedId] : null;

  // No workspace active → show placeholder
  if (!workspace.active) {
    return (
      <div style={emptyStyle}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🌳</div>
        <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 8 }}>
          多 Agent 协作工作区
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
          发送消息后，委托树将在此展示
        </div>
        {mockMode && (
          <button onClick={loadMockData} style={mockBtnStyle}>
            🧪 加载 Mock 数据
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      {/* Center: xyflow delegation tree */}
      <div style={flowContainerStyle}>
        <ReactFlow
          nodes={reactiveNodes}
          edges={flowEdges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={1.5}
          defaultEdgeOptions={{ animated: false }}
        >
          <Background color="#1e293b" gap={24} size={1} />
          <Controls
            showInteractive={false}
            style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8 }}
          />
        </ReactFlow>

        {/* Completion summary overlay */}
        {workspace.completed && (
          <div style={completionOverlayStyle}>
            <CompletionSummary
              nodes={workspace.nodes}
              rootId={workspace.rootId}
              completionSummary={workspace.completionSummary}
            />
          </div>
        )}
      </div>

      {/* Right: Detail panel */}
      {selectedNode && (
        <AgentDetailPanel
          node={selectedNode}
          onClose={() => { setInternalSelectedId(null); selectNode(null); }}
        />
      )}
    </div>
  );
}

// ── Styles ──

const containerStyle: React.CSSProperties = {
  display: 'flex',
  width: '100%',
  height: '100%',
  overflow: 'hidden',
};

const flowContainerStyle: React.CSSProperties = {
  flex: 1,
  position: 'relative',
  background: '#060b18',
};

const emptyStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  height: '100%',
  color: 'var(--text-dim)',
};

const mockBtnStyle: React.CSSProperties = {
  marginTop: 16,
  padding: '8px 16px',
  borderRadius: 6,
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 12,
};

const completionOverlayStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: 16,
  left: '50%',
  transform: 'translateX(-50%)',
  zIndex: 10,
  maxWidth: 500,
  width: '90%',
};
